"""
Address Hotels + Resorts — Backup Typesense Collections

Exports address_knowledge to data/backups/ as a JSONL file.

Usage:
  python -X utf8 scripts/backup_collections.py
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
import typesense

load_dotenv()

TYPESENSE_NODES    = [os.getenv(f'TYPESENSE_NODE_{i}', '') for i in range(1, 4)]
TYPESENSE_PORT     = os.getenv('TYPESENSE_PORT', '443')
TYPESENSE_PROTOCOL = os.getenv('TYPESENSE_PROTOCOL', 'https')
TYPESENSE_API_KEY  = os.getenv('TYPESENSE_API_KEY', '')

COLLECTION = 'address_knowledge'
BACKUP_DIR = Path(__file__).resolve().parent.parent / 'data' / 'backups'


def get_client() -> typesense.Client:
    nodes = [h for h in TYPESENSE_NODES if h]
    if not nodes or not TYPESENSE_API_KEY:
        raise ValueError('Missing Typesense credentials in .env')
    return typesense.Client({
        'nodes': [{'host': h, 'port': TYPESENSE_PORT, 'protocol': TYPESENSE_PROTOCOL}
                  for h in nodes],
        'api_key': TYPESENSE_API_KEY,
        'connection_timeout_seconds': 120,
    })


def main():
    print("=" * 60)
    print("Address Hotels + Resorts — Backup Collections")
    print("=" * 60)

    client = get_client()
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    print(f"\nExporting {COLLECTION}...")
    try:
        raw = client.collections[COLLECTION].documents.export()
        lines = [l for l in raw.splitlines() if l.strip()]

        backup_path = BACKUP_DIR / f"{COLLECTION}_{timestamp}.jsonl"
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

        size_kb = backup_path.stat().st_size / 1024
        print(f"  ✅ {len(lines)} documents → {backup_path} ({size_kb:.1f} KB)")

    except Exception as e:
        print(f"  ❌ Failed: {e}")

    print("\nBackup complete.")


if __name__ == '__main__':
    main()
