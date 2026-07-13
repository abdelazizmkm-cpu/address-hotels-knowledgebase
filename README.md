# Address Hotels + Resorts RAG Knowledgebase

Crawls [addresshotels.com](https://www.addresshotels.com/en/) (EN + AR, whole site) and stores content in Typesense Cloud for a bilingual (Arabic/English) RAG AI assistant covering every Address property.

Built on the same pattern as the Al-Wadi Hotel and QSW knowledgebases (IndigoHive AI Agent Deployment Workflow): scrape → index in Typesense → conversation model → Cogfy workflow → WhatsApp (+ optional Hamsa voice).

## What's different from a single-hotel build

Address is a multi-property brand, so every chunk carries a `property` facet (e.g. `address_downtown`, `address_beach_resort`, `address_sky_view`, or `brand` for brand-level pages). Queries can be scoped to one hotel the way QSW scoped by `center`.

The site is behind a **WAF that returns 403 to datacenter IPs** (confirmed 2026-07-08), so the crawl runs through **Apify RESIDENTIAL proxies**. A plain datacenter crawler gets blocked.

## Collections

| Collection | Description |
|---|---|
| `address_knowledge` | Bilingual RAG chunks with auto-embeddings — faceted by `property`, `doc_type`, `language` |
| `address_conversations` | Conversation history for the `address-gpt` model |

`doc_type` values: `room_page`, `dining_page`, `spa_page`, `offer_page`, `meetings_page`, `wedding_page`, `destination_page`, `general_page`, `fact`.

### Retrieval architecture

Each document has a `language` tag (`ar` / `en` / `any`). Arabic queries filter to `[ar,any]`, English to `[en,any]` — preventing cross-language embedding dilution. Add `&& property:=address_downtown` to scope to one hotel.

Embedding model: `ts/multilingual-e5-large` (Typesense-hosted, no external API key required).

---

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure credentials
Copy `.env.example` to `.env` and fill in Typesense, Apify, and OpenAI credentials.

### 3. Run the Apify crawl (required first step)
```bash
python -X utf8 scripts/apify_crawl.py
```
Crawls addresshotels.com with Firefox (full JS) through residential proxies.
Outputs `data/apify_pages.json` and `data/apify_pdf_urls.json`.
The run reports how many pages were captured and how many were blocked by the WAF — check both before scaling up `maxCrawlPages`.

### 4. Build the knowledgebase
```bash
python -X utf8 main.py            # build / update
python -X utf8 main.py --fresh    # drop and recreate the collection
python -X utf8 main.py --no-apify # only upsert static facts
```

### 5. Re-index after a fresh crawl
```bash
python -X utf8 scripts/apify_index.py
python -X utf8 scripts/apify_index.py --dry-run
```

### 6. Set up the conversation model
```bash
python -X utf8 scripts/update_system_prompt.py
```
Creates or updates the `address-gpt` conversation model (requires `OPENAI_API_KEY`).

### 7. Export the knowledge base
```bash
python -X utf8 typesense/export_knowledge.py
```
Outputs `data/knowledge_base.txt`, grouped by property, ready to upload to a voice/assistant platform.

---

## Post-crawl TODO (don't skip)

1. **Verify property tagging.** Run the crawl, read the `Property:` breakdown printed by `main.py`. Any page in `brand` that actually belongs to a hotel means `_PROPERTY_MAP` in `typesense/main.py` needs a new slug. Refine and re-index.
2. **Author static facts from verified content.** `STATIC_FACTS` in `typesense/main.py` is intentionally empty. Fill it per property (contact, address, overview) from the scraped pages or the client — never invented — so critical info always retrieves.
3. **Refine crawl excludes.** After the first run, add the real booking-engine domain and any non-EN/AR language codes to `excludeUrlGlobs` in `scripts/apify_crawl.py`.

---

## Querying (Postman / API)

Grounded RAG answer via the `address-gpt` conversation model.

**Method + URL** (conversation params go in the query string, including `q`):
```
POST https://{TYPESENSE_HOST}/multi_search?conversation=true&conversation_model_id=address-gpt&q={question}
```

**Header:**
```
X-TYPESENSE-API-KEY: {SEARCH_ONLY_API_KEY}
```

**Body:**
```json
{
  "searches": [
    {
      "collection": "address_knowledge",
      "query_by": "embedding",
      "per_page": 10,
      "exclude_fields": "embedding",
      "filter_by": "language:=[en,any]",
      "vector_query": "embedding:([], distance_threshold:0.35)"
    }
  ]
}
```

**Response:** the grounded reply is in `conversation.answer`.

> - `q` is a **URL query parameter**, not in the body.
> - `filter_by`: use `language:=[ar,any]` for Arabic queries, `language:=[en,any]` for English. Append `&& property:=address_downtown` to scope to one hotel.
> - `per_page: 10` — the retrieval window (top_k). Keep ~8–10 so narrow facts aren't cut off.
> - `exclude_fields: "embedding"` is **required** — omitting it passes raw vectors into the LLM context.
> - Pass a stable `conversation_id={uuid}` URL param to keep multi-turn context.
> - Use the **search-only** key (read). Never expose the admin key in a client/agent.

---

## Project structure

```
├── scrapers/session.py            # Shared requests session (proxy-aware)
├── typesense/
│   ├── schemas.py                 # address_knowledge collection (property facet)
│   ├── main.py                    # connect → create → process → store; STATIC_FACTS
│   └── export_knowledge.py        # exports to data/knowledge_base.txt (by property)
├── scripts/
│   ├── apify_crawl.py             # whole-site crawl via residential proxies
│   ├── apify_index.py             # re-index crawl results
│   ├── update_system_prompt.py    # address-gpt conversation model
│   └── backup_collections.py      # JSONL backups
├── main.py                        # entry point → typesense/main.py
├── query_normalizer.py            # Arabic dialect → MSA (OpenAI)
├── requirements.txt
├── .env / .env.example
└── data/                          # (gitignored, generated by the pipeline)
```
