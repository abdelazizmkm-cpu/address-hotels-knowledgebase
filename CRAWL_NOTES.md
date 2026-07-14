# Address Hotels KB — build notes

Working log for the Address Hotels + Resorts knowledgebase build. Scope: **UAE properties only** (decided 2026-07-09).

## Site facts

- Domain: https://www.addresshotels.com/en/ (WordPress, Azure CDN, **Cloudflare WAF**).
- WAF returns **403 to datacenter IPs** and 500 to raw HTTP. Crawl **must** use Apify **RESIDENTIAL** proxies + a real browser (playwright:firefox). Confirmed working 2026-07-09.
- Rich `metadata.jsonLd` per hotel page: `telephone`, `email`, `address`, `checkinTime`/`checkoutTime`, `amenityFeature`, and FAQ `mainEntity.acceptedAnswer` — use for authoritative static facts (no invention).

## UAE portfolio (10 properties) — the crawl scope

Dubai (8):
- Address Downtown — `/en/hotels/address-downtown`
- Palace Downtown — `/en/hotels/palace-downtown`
- Address Dubai Mall — `/en/hotels/address-dubai-mall`
- Address Sky View — `/en/hotels/address-sky-view`
- Address Montgomerie — `/en/hotels/address-montgomerie` (Emirates Hills)
- Address Creek Harbour — `/en/hotels/address-creek-harbour`
- Palace Dubai Creek Harbour — `/en/hotels/palace-dubai-creek-harbour`
- Address Beach Resort — `/en/resorts/address-beach-resort` (JBR / Dubai Marina)

Fujairah (2):
- Address Beach Resort Fujairah — `/en/resorts/address-beach-resort-fujairah`
- Palace Beach Resort Fujairah — `/en/resorts/palace-beach-resort-fujairah`

UAE destination pages included: `/en/hotels-in-dubai`, `/en/hotels-in-fujairah`, `/en/hotels-in-dubai-marina`, `/en/hotels-in-dubai-creek-harbour`, `/en/hotels-in-emirates-hills`, `/en/hotels-in-jumeirah-beach-residence`.
Brand sections included: `/en/dine`, `/en/wellness`, `/en/events`, `/en/weddings`, `/en/offers`.

Excluded (non-UAE): Bahrain (`address-beach-resort-bahrain`), Egypt (`address-marassi-golf-resort`, `address-beach-resort-marassi`, `palace-beach-resort`), Saudi (`address-jabal-omar-makkah`), Turkey (`address-istanbul`). Also excluded: `/en/blog`, `/en/blogs`, `/en/offers-global`, galleries.

To verify with client: FAQ prose mentions "Address Boulevard", "Address Fountain Views", "Address Grand Creek Harbour" — these are NOT in the current booking-widget portfolio (possibly renamed/retired). Not crawled.

## Apify runs (via session connection, RESIDENTIAL proxy)

- Probe (20-page, /en/): run `Fgm0WVOMRnKbsI6sd`, dataset `RVyA1jwikauAVy2bQ`.
- Portfolio discovery (homepage + city pages, rag-web-browser): datasets `gfq3GtlFXT6r5pWiE` (home), `dbvtpUajA3cKrgtqy` (Dubai), `c1VPZmg8aHSwvoV0D` (Fujairah).
- **Main EN UAE crawl:** run `maVUAyJCtRmR26ap0`, dataset `dwSEC0ZgwHJVT9j4G` (SUCCEEDED, ~234 content pages).
- **AR UAE crawl:** run `fpfZ7JiUDdQxIqy6d`, dataset `gxsNDeKneyQjk00it` (was RUNNING at pause 2026-07-09; let it finish, then fetch).

## Typesense — Hotel-Address cluster

- Node: `ifq728p93oa5n1cvp-1.a1.typesense.net:443` (single node). Keys in `.env` (from `Hotel-Address-api-keys-*.txt`).
- Collection: `address_knowledge` (facets: `property`, `doc_type`, `language`). Conversation model: `address-gpt`. History: `address_conversations`.

## Status (paused 2026-07-09)

DONE — English pass live and tested:
- EN indexed: **131 clean chunks** (non-UAE dropped, booking boilerplate stripped). `main.py` filters live in `typesense/main.py` (`_is_non_uae`, `_clean_apify_text`, `_PROPERTY_MAP`), now extended for Arabic too.
- `address-gpt` conversation model created (strict out-of-scope refusal + grounded recommendations).
- Test suite in `test/`: **34/34** (FAQ 16/16, Inference 9/9, Out-of-scope 9/9). Run `python -X utf8 test/run_tests.py --answers`.
- Peugeot collections backed up (scratchpad) + dropped; cluster upgraded to 4 GB.

## Arabic pass — DONE

- AR crawl `fpfZ7JiUDdQxIqy6d` / dataset `gxsNDeKneyQjk00it` (376/377 pages) merged into `data/apify_pages.json` (234 EN + 143 AR).
- Reindexed bilingual: **~268 chunks (131 EN + 137 AR)**, all 10 UAE properties. `main.py` cleaner extended for Arabic (widget labels, weekdays/months, price-embedded date cells, Arabic non-UAE terms, +973/+966/+90/+20 phone check).
- Verified **zero literal non-UAE content** (EN + AR); the fuzzy keyword counts (مكة/مراسي/Saudi) are Typesense typo-tolerance, not real content.
- Test suite now bilingual (47 questions incl. Gulf/Egyptian/Levantine dialects). Runner is language-aware (`_lang_filter` → `[ar,any]`/`[en,any]`). **Effectively 47/47** — the RAG model answers in MSA, handles dialects, and refuses out-of-scope in Arabic. (Borderline AR retrieval-completeness items like the exact spa-room count vary ±1 run to run; fact-chunks would firm them up.)
- Note: the query normalizer (dialect→MSA) belongs in the Cogfy tool-call layer, NOT the built-in Typesense conversation (which shares one `q` for retrieve + answer); forcing it into the test runner degraded answers, so it was reverted there.

## Static facts — DONE (targeted)

- Tested contact retrieval across all 10 properties: 8/10 returned their contact reliably from crawled content; **Address Montgomerie** and **Palace Dubai Creek Harbour** did not (main reservations line was never cleanly crawled — only department sub-page numbers).
- Fetched authoritative contacts fresh and added **4 fact chunks (EN + AR)** in `STATIC_FACTS` (`typesense/main.py`) for only those two. Verified both now retrieve in both languages. KB = 272 chunks.
  - Address Montgomerie: +971 4 390 5600 · stay@addresshotels.com · Emirates Hills.
  - Palace Dubai Creek Harbour: +971 4 559 8888 · stayatpalacecreek@palacehotels.com (note `@palacehotels.com`).

## Chunking fix — DONE (2026-07-11)

- Found the root cause of the borderline AR retrieval misses: 64/268 chunks were oversized (up to 7,017 chars) because the crawler emits pages as one single-`\n` block with no blank-line paragraph breaks, so the paragraph-only splitter never split them — burying single facts in page-sized blobs.
- Rewrote `_split_text` in `typesense/main.py` to hard-split by lines/size, cap `MAX_CHUNK_CHARS=1400`. Result: **436 chunks, median ~1,060, max ~1,480**. Reindexed.
- Effect: EN specific-fact retrieval fixed (e.g. spa "9 treatment rooms" now answers). Remaining AR items resolved by **top_k=10** (a deep-ranked fact) and the dialect normalizer.
- Tuning: test runner `TOP_K`/`per_page` set to **10** (from 5). Recommend production Cogfy retrieval top_k ~8-10.
- Veracity note: even with correct context retrieved, the LLM occasionally misstates a specific number (said "seven" spa rooms when the context clearly says nine). Intermittent generative error, not data/chunking. Watch for it in demo; a numeric-heavy fact chunk or a "quote numbers exactly from context" prompt line can help.

## KB hardening pass — DONE (2026-07-11, before sharing with team)

- Dropped 14 gallery/`photos-and-videos` pages (pure section-nav menus) + stripped section-nav labels. KB = **430 chunks**.
- Added number-exactness rule to the `address-gpt` system prompt → fixed the "seven vs nine" spa-room wobble (now 9 consistently, 3/3).
- Static facts (6 total): contact for Address Montgomerie + Palace Dubai Creek Harbour (EN+AR); brand-level **check-in/out** (3:00 PM / 12:00 noon, early 11:00 / late 4:00) EN+AR — fixed an EN/AR asymmetry (was answering AR only). Times verified uniform across 8 property pages.
- Broad retrieval sweep: all common concierge queries retrieve in-threshold. Genuine content gaps (not on the site): **parking, airport transfer, pet policy** — agent correctly declines; ask client if they want these added as facts.
- Final suite: **46/47** (1 = network timeout; behaviourally 47/47).

## Resume here (next phase)

1. Cogfy workflow (tool-call loop) wiring `address-gpt` + the dialect query normalizer, retrieval top_k ~8-10 → WhatsApp.
2. Hamsa voice agent if in scope. Static-text KB already exported for it: `data/knowledge_base.txt` (`python -X utf8 typesense/export_knowledge.py`, 622 KB, bilingual, by property → section; matches the Elithair/UDC Hamsa format). Regenerate after any reindex.
- If more gaps surface in demo, add targeted fact chunks the same way (test first, only where retrieval misses).
