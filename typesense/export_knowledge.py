"""
Address Hotels + Resorts — Export Knowledge Base

Exports all chunks from address_knowledge to data/knowledge_base.txt —
a structured plain-text file ready to upload to an AI assistant (e.g. Hamsa, GPT).

Grouped by property (each Address hotel), then by doc_type within each property:
  facts → rooms → dining → spa → offers → meetings → weddings → destination → general

Usage:
  python -X utf8 typesense/export_knowledge.py
"""
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
import typesense

load_dotenv()

TYPESENSE_NODES    = [os.getenv(f'TYPESENSE_NODE_{i}', '') for i in range(1, 4)]
TYPESENSE_PORT     = os.getenv('TYPESENSE_PORT', '443')
TYPESENSE_PROTOCOL = os.getenv('TYPESENSE_PROTOCOL', 'https')
TYPESENSE_API_KEY  = os.getenv('TYPESENSE_API_KEY', '')

COLLECTION  = 'address_knowledge'
OUTPUT_PATH = Path(__file__).resolve().parent.parent / 'data' / 'knowledge_base.txt'

DOC_TYPE_ORDER = [
    'fact',
    'room_page',
    'dining_page',
    'spa_page',
    'offer_page',
    'meetings_page',
    'wedding_page',
    'destination_page',
    'general_page',
]

DOC_TYPE_LABELS = {
    'fact':             'STATIC FACTS',
    'room_page':        'ROOMS, SUITES & RESIDENCES',
    'dining_page':      'RESTAURANTS & BARS',
    'spa_page':         'SPA & WELLNESS',
    'offer_page':       'SPECIAL OFFERS',
    'meetings_page':    'MEETINGS & EVENTS',
    'wedding_page':     'WEDDINGS',
    'destination_page': 'DESTINATION',
    'general_page':     'GENERAL PAGES',
}


def get_client() -> typesense.Client:
    nodes = [h for h in TYPESENSE_NODES if h]
    if not nodes or not TYPESENSE_API_KEY:
        raise ValueError('Missing Typesense credentials in .env')
    return typesense.Client({
        'nodes': [{'host': h, 'port': TYPESENSE_PORT, 'protocol': TYPESENSE_PROTOCOL}
                  for h in nodes],
        'api_key': TYPESENSE_API_KEY,
        'connection_timeout_seconds': 60,
    })


def fetch_all_chunks(client: typesense.Client) -> list[dict]:
    raw = client.collections[COLLECTION].documents.export()
    chunks = [json.loads(line) for line in raw.splitlines() if line.strip()]
    print(f"  Exported {len(chunks)} chunks from {COLLECTION}")
    return chunks


def main():
    print("=" * 60)
    print("Address Hotels + Resorts — Export Knowledge Base")
    print("=" * 60)

    client = get_client()
    chunks = fetch_all_chunks(client)

    # property → doc_type → [chunks]
    by_prop: dict[str, dict[str, list[dict]]] = {}
    for c in chunks:
        prop = c.get('property', 'brand')
        dt   = c.get('doc_type', 'general_page')
        by_prop.setdefault(prop, {}).setdefault(dt, []).append(c)

    lines = [
        "=" * 60,
        "ADDRESS HOTELS + RESORTS — KNOWLEDGE BASE",
        "=" * 60,
        f"Total chunks: {len(chunks)}",
        f"Properties: {len(by_prop)}",
        "",
    ]

    for prop in sorted(by_prop):
        prop_label = prop.replace('_', ' ').upper()
        lines.append(f"\n{'=' * 60}")
        lines.append(f"PROPERTY: {prop_label}")
        lines.append('=' * 60)

        for doc_type in DOC_TYPE_ORDER:
            group = by_prop[prop].get(doc_type, [])
            if not group:
                continue
            group.sort(key=lambda c: c.get('chunk_index', 0))

            label = DOC_TYPE_LABELS.get(doc_type, doc_type.upper())
            lines.append(f"\n{'─' * 60}")
            lines.append(f"{label} ({len(group)} chunks)")
            lines.append('─' * 60)

            for chunk in group:
                title = chunk.get('title_en') or chunk.get('title_ar') or '(untitled)'
                lang  = chunk.get('language', '?')
                url   = chunk.get('source_url', '')
                lines.append(f"\n[{lang}] {title}")
                if url:
                    lines.append(f"Source: {url}")
                lines.append(chunk.get('text', ''))
                lines.append('')

    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    size_kb = OUTPUT_PATH.stat().st_size / 1024
    print(f"\n  💾 Exported to {OUTPUT_PATH} ({size_kb:.1f} KB)")

    print("\n  By property:")
    for prop in sorted(by_prop):
        n = sum(len(g) for g in by_prop[prop].values())
        print(f"    {prop:<32}: {n}")


if __name__ == '__main__':
    main()
