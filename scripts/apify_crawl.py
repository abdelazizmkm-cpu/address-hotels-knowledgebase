"""
Address Hotels + Resorts — Apify Web Crawler

Triggers an Apify Website Content Crawler run against addresshotels.com using
Firefox for full JavaScript rendering, routed through Apify RESIDENTIAL proxies.

Why residential proxies: addresshotels.com sits behind a WAF that returns 403
to datacenter IPs (confirmed 2026-07-08). A plain datacenter crawl gets blocked;
residential proxies are required. If you still see 403s / block pages in the
output, raise the delay and/or confirm the proxy group with Apify.

Outputs:
  data/apify_pages.json    — HTML page content (text, title, url)
  data/apify_pdf_urls.json — PDF URLs discovered during the crawl

Usage:
  python -X utf8 scripts/apify_crawl.py           # run crawl
  python -X utf8 scripts/apify_crawl.py --load    # skip crawl, reload last saved run

Requires APIFY_API_TOKEN in .env.
"""
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from apify_client import ApifyClient

load_dotenv()

PAGES_PATH   = Path(__file__).resolve().parent.parent / 'data' / 'apify_pages.json'
PDF_URL_PATH = Path(__file__).resolve().parent.parent / 'data' / 'apify_pdf_urls.json'

APIFY_ACTOR_ID = 'apify/website-content-crawler'

# Whole-site crawl. Seed EN + AR homepages; BFS discovers everything linked.
# Add per-property section seeds here if the crawl misses hotels behind JS menus.
START_URLS = [
    'https://www.addresshotels.com/en/',
    'https://www.addresshotels.com/ar/',
]

CRAWLER_OPTIONS = {
    'crawlerType':          'playwright:firefox',
    'maxCrawlDepth':        6,
    # Whole-site cap. Start here to size the job; raise once the first run shows
    # how many real pages the site has and how many Apify credits it costs.
    'maxCrawlPages':        1500,
    'saveMarkdown':         False,
    'saveHtml':             False,
    'removeCookieWarnings': True,
    'expandIframes':        True,
    'ignoreSslErrors':      False,
    # Route through residential proxies to get past the WAF (see module docstring).
    'proxyConfiguration': {
        'useApifyProxy':    True,
        'apifyProxyGroups': ['RESIDENTIAL'],
    },
    # Politer pacing helps avoid tripping the WAF's rate limits.
    'maxConcurrency':       5,
    'requestTimeoutSecs':   60,
    # Stay on addresshotels.com only — exclude external booking engines.
    'includeUrlGlobs': [
        {'glob': 'https://www.addresshotels.com/'},
        {'glob': 'https://www.addresshotels.com/**'},
    ],
    'excludeUrlGlobs': [
        # Booking / reservation engines (external — refine after first crawl)
        {'glob': 'https://*.synxis.com/**'},
        {'glob': 'https://book.**'},
        {'glob': 'https://booking.**'},
        {'glob': 'https://reservations.**'},
        # Non EN/AR language variants (add real codes once seen in the crawl)
        {'glob': 'https://www.addresshotels.com/fr/**'},
        {'glob': 'https://www.addresshotels.com/de/**'},
        {'glob': 'https://www.addresshotels.com/es/**'},
        {'glob': 'https://www.addresshotels.com/zh/**'},
        {'glob': 'https://www.addresshotels.com/ru/**'},
        # Media / gallery (mostly images, minimal text)
        {'glob': 'https://www.addresshotels.com/**/gallery/**'},
        {'glob': 'https://www.addresshotels.com/**/media/**'},
        # Search / pagination / query noise
        {'glob': 'https://www.addresshotels.com/**?*'},
        {'glob': 'https://www.addresshotels.com/**/page/**'},
    ],
}

# Signatures that mean the WAF blocked a page — flag rather than index garbage.
_BLOCK_SIGNATURES = (
    'access denied',
    'request blocked',
    'attention required',
    'cloudflare',
    'are you a human',
    'verify you are human',
    '403 forbidden',
)


def _is_error_page(text: str) -> bool:
    t = text.strip().lower()
    return (
        t.startswith('404') or
        t.startswith('500') or
        'not found' in t[:80] or
        'internal server error' in t[:80]
    )


def _is_block_page(text: str) -> bool:
    t = text.strip().lower()[:400]
    return any(sig in t for sig in _BLOCK_SIGNATURES)


def _split_pages_and_pdfs(items: list[dict]) -> tuple[list[dict], list[str], int]:
    pages    = []
    pdf_urls = set()
    blocked  = 0

    for item in items:
        url = item.get('url', '')
        if not url:
            continue
        text = (item.get('text') or item.get('markdown') or '').strip()
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

    return pages, sorted(pdf_urls), blocked


def run_crawl() -> list[dict]:
    token = os.getenv('APIFY_API_TOKEN')
    if not token:
        print('❌  APIFY_API_TOKEN not set in .env')
        sys.exit(1)

    client = ApifyClient(token)

    run_input = {
        'startUrls': [{'url': u} for u in START_URLS],
        **CRAWLER_OPTIONS,
    }

    print(f'🚀  Starting Apify crawl ({len(START_URLS)} entry points, '
          f'max {CRAWLER_OPTIONS["maxCrawlPages"]} pages)...')
    print(f'    Actor: {APIFY_ACTOR_ID}')
    print(f'    Renderer: playwright:firefox (JavaScript enabled)')
    print(f'    Proxy: Apify RESIDENTIAL (WAF bypass)')

    run   = client.actor(APIFY_ACTOR_ID).call(run_input=run_input)
    run_id = run['id']               if isinstance(run, dict) else run.id
    ds_id  = run['defaultDatasetId'] if isinstance(run, dict) else run.default_dataset_id
    print(f'✅  Run finished — ID: {run_id}')

    print('📥  Fetching results from Apify dataset...')
    items = list(client.dataset(ds_id).iterate_items())
    print(f'    {len(items)} records returned')

    return items


def save(pages: list[dict], pdf_urls: list[str]):
    PAGES_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(PAGES_PATH, 'w', encoding='utf-8') as f:
        json.dump(pages, f, ensure_ascii=False, indent=2)
    size_kb = PAGES_PATH.stat().st_size / 1024
    print(f'💾  Pages   → {PAGES_PATH} ({len(pages)} pages, {size_kb:.1f} KB)')

    with open(PDF_URL_PATH, 'w', encoding='utf-8') as f:
        json.dump(pdf_urls, f, ensure_ascii=False, indent=2)
    print(f'💾  PDF URLs → {PDF_URL_PATH} ({len(pdf_urls)} URLs)')


def main():
    load_only = '--load' in sys.argv

    if load_only:
        if not PAGES_PATH.exists():
            print(f'❌  {PAGES_PATH} not found. Run without --load first.')
            sys.exit(1)
        with open(PAGES_PATH, encoding='utf-8') as f:
            pages = json.load(f)
        with open(PDF_URL_PATH, encoding='utf-8') as f:
            pdf_urls = json.load(f)
        blocked = 0
        print(f'📂  Loaded {len(pages)} pages, {len(pdf_urls)} PDF URLs from disk')
    else:
        items = run_crawl()
        pages, pdf_urls, blocked = _split_pages_and_pdfs(items)
        save(pages, pdf_urls)

    en = sum(1 for p in pages if '/ar' not in p.get('url', ''))
    ar = sum(1 for p in pages if '/ar' in p.get('url', ''))

    print(f'\nSummary:')
    print(f'  HTML pages : {len(pages)} (EN: {en}, AR: {ar})')
    print(f'  PDF URLs   : {len(pdf_urls)}')
    if blocked:
        print(f'  ⚠️  Blocked/WAF pages skipped: {blocked} '
              f'(raise delay or check proxy if this is high)')
    print(f'\nNext: python -X utf8 main.py')


if __name__ == '__main__':
    main()
