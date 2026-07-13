"""
Address Hotels + Resorts — Fetch an Apify dataset to disk

Pulls a finished Apify crawl dataset straight into data/apify_pages.json (and
data/apify_pdf_urls.json) in the shape main.py / apify_index.py expect, without
routing the payload through anything else. Use this when the crawl was launched
outside scripts/apify_crawl.py (e.g. via the Apify console or an MCP connection).

Usage:
  python -X utf8 scripts/fetch_dataset.py <datasetId>

Requires APIFY_API_TOKEN in .env.
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DATA_DIR     = Path(__file__).resolve().parent.parent / 'data'
PAGES_PATH   = DATA_DIR / 'apify_pages.json'
PDF_URL_PATH = DATA_DIR / 'apify_pdf_urls.json'

_BLOCK_SIGNATURES = (
    'access denied', 'request blocked', 'attention required',
    'are you a human', 'verify you are human', '403 forbidden',
)


def _is_block_page(text: str) -> bool:
    t = (text or '').strip().lower()[:400]
    return any(sig in t for sig in _BLOCK_SIGNATURES)


def _is_error_page(text: str) -> bool:
    t = (text or '').strip().lower()
    return t.startswith('404') or t.startswith('500') or 'not found' in t[:80]


def fetch_items(token: str, dataset_id: str) -> list[dict]:
    """Page through the dataset via the Apify API and return clean items."""
    items, offset, limit = [], 0, 1000
    while True:
        url = (f'https://api.apify.com/v2/datasets/{dataset_id}/items'
               f'?token={token}&clean=true&offset={offset}&limit={limit}'
               f'&fields=url,text,markdown,metadata')
        with urllib.request.urlopen(url, timeout=120) as r:
            batch = json.load(r)
        if not batch:
            break
        items.extend(batch)
        print(f'  fetched {len(items)} items...')
        if len(batch) < limit:
            break
        offset += limit
    return items


def main():
    if len(sys.argv) < 2:
        print('Usage: python -X utf8 scripts/fetch_dataset.py <datasetId>')
        sys.exit(1)
    dataset_id = sys.argv[1]

    token = os.getenv('APIFY_API_TOKEN')
    if not token:
        print('❌  APIFY_API_TOKEN not set in .env')
        sys.exit(1)

    print(f'📥  Fetching dataset {dataset_id} ...')
    raw = fetch_items(token, dataset_id)
    print(f'    {len(raw)} raw items')

    pages, pdf_urls, blocked = [], set(), 0
    for item in raw:
        url  = item.get('url', '')
        text = (item.get('text') or item.get('markdown') or '').strip()
        if not url:
            continue
        if _is_block_page(text):
            blocked += 1
            continue
        if url.lower().endswith('.pdf'):
            if text and not _is_error_page(text):
                pages.append(item)
            else:
                pdf_urls.add(url)
            continue
        if text and not _is_error_page(text):
            pages.append(item)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(PAGES_PATH, 'w', encoding='utf-8') as f:
        json.dump(pages, f, ensure_ascii=False, indent=2)
    with open(PDF_URL_PATH, 'w', encoding='utf-8') as f:
        json.dump(sorted(pdf_urls), f, ensure_ascii=False, indent=2)

    size_kb = PAGES_PATH.stat().st_size / 1024
    print(f'💾  Pages   → {PAGES_PATH} ({len(pages)} pages, {size_kb:.1f} KB)')
    print(f'💾  PDF URLs → {PDF_URL_PATH} ({len(pdf_urls)} URLs)')
    if blocked:
        print(f'⚠️   {blocked} WAF/block pages skipped')
    print('\nNext: python -X utf8 main.py --fresh')


if __name__ == '__main__':
    main()
