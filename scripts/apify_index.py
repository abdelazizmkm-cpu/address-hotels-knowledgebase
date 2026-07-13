"""
Address Hotels + Resorts — Apify Indexer

Re-indexes data/apify_pages.json into address_knowledge on Typesense without
touching static facts. Use this after re-running apify_crawl.py to refresh
crawled content while keeping existing static facts intact.

Usage:
  python -X utf8 scripts/apify_index.py
  python -X utf8 scripts/apify_index.py --dry-run    # preview only
  python -X utf8 scripts/apify_index.py --pages-only # skip PDFs
"""
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'typesense'))
from main import (
    load_typesense_client,
    page_to_chunks,
    COLLECTION,
)

PAGES_PATH   = Path(__file__).resolve().parent.parent / 'data' / 'apify_pages.json'
PDF_URL_PATH = Path(__file__).resolve().parent.parent / 'data' / 'apify_pdf_urls.json'
CHECKPOINT   = Path(__file__).resolve().parent.parent / 'data' / 'chunks_checkpoint.json'

BATCH_SIZE = 50


def upsert_batches(client, chunks: list[dict], dry_run: bool) -> int:
    if dry_run:
        print(f'  [dry-run] Would upsert {len(chunks)} chunks')
        return 0

    total_ok = 0
    n_batches = (len(chunks) + BATCH_SIZE - 1) // BATCH_SIZE

    for i in range(0, len(chunks), BATCH_SIZE):
        batch    = chunks[i:i + BATCH_SIZE]
        batch_no = i // BATCH_SIZE + 1
        jsonl    = '\n'.join(json.dumps(c, ensure_ascii=False) for c in batch)

        for attempt in range(1, 4):
            try:
                raw = client.collections[COLLECTION].documents.import_(
                    jsonl, {'action': 'upsert'}
                )
                break
            except Exception as e:
                if attempt == 3:
                    print(f'    ⚠️  Batch {batch_no} failed: {e}')
                    raw = None
                    break
                import time
                time.sleep(10 * attempt)

        if raw is None:
            continue

        results  = [json.loads(r) for r in raw.splitlines() if r.strip()]
        ok       = sum(1 for r in results if r.get('success'))
        total_ok += ok
        print(f'  Batch {batch_no}/{n_batches} — {ok}/{len(batch)} ok')

    return total_ok


def update_checkpoint(new_chunks: list[dict]):
    existing = []
    if CHECKPOINT.exists():
        with open(CHECKPOINT, encoding='utf-8') as f:
            existing = json.load(f)
    kept   = [c for c in existing if not c.get('id', '').startswith('apify_')]
    merged = kept + new_chunks
    for i, c in enumerate(merged):
        c['chunk_index'] = i
    with open(CHECKPOINT, 'w', encoding='utf-8') as f:
        json.dump(merged, f, ensure_ascii=False)
    print(f'💾  Checkpoint updated: {len(merged)} total chunks')


def main():
    dry_run    = '--dry-run'    in sys.argv
    pages_only = '--pages-only' in sys.argv

    print('=' * 60)
    print('Address Hotels + Resorts — Apify Indexer')
    print('=' * 60)

    all_chunks: list[dict] = []

    if not PAGES_PATH.exists():
        print(f'❌  {PAGES_PATH} not found. Run apify_crawl.py first.')
        sys.exit(1)

    print(f'\n[1] Loading HTML pages from {PAGES_PATH}...')
    with open(PAGES_PATH, encoding='utf-8') as f:
        pages = json.load(f)
    print(f'    {len(pages)} pages loaded')

    page_chunks = []
    skipped = 0
    for item in pages:
        chunks = page_to_chunks(item)
        if chunks:
            page_chunks.extend(chunks)
        else:
            skipped += 1

    by_lang = {}
    by_type = {}
    by_prop = {}
    for c in page_chunks:
        by_lang[c['language']] = by_lang.get(c['language'], 0) + 1
        by_type[c['doc_type']] = by_type.get(c['doc_type'], 0) + 1
        by_prop[c['property']] = by_prop.get(c['property'], 0) + 1

    print(f'    {len(page_chunks)} chunks from {len(pages) - skipped} pages '
          f'({skipped} skipped)')
    print(f'    Language: {dict(sorted(by_lang.items()))}')
    print(f'    Doc type: {dict(sorted(by_type.items()))}')
    print(f'    Property: {dict(sorted(by_prop.items()))}')
    all_chunks.extend(page_chunks)

    if not all_chunks:
        print('\nNo chunks to index.')
        return

    print(f'\n[2] Connecting to Typesense...')
    client = load_typesense_client()

    print(f'[2] Upserting {len(all_chunks)} chunks to {COLLECTION}...')
    ok = upsert_batches(client, all_chunks, dry_run)

    if not dry_run:
        print(f'\n[3] Updating checkpoint...')
        update_checkpoint(all_chunks)

        count = client.collections[COLLECTION].retrieve().get('num_documents', '?')
        print(f'    Collection now has {count} documents')
        print(f'\n✅  Done — {ok}/{len(all_chunks)} chunks upserted.')
    else:
        print(f'\n✅  Dry-run complete — {len(all_chunks)} chunks would be upserted.')


if __name__ == '__main__':
    main()
