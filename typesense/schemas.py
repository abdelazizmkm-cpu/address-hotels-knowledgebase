"""
Typesense collection schema for Address Hotels + Resorts RAG Knowledgebase.

Single collection: address_knowledge
  All content across every Address property (rooms, dining, spa, offers, events,
  residences, static facts) lives here, tagged by `property`.

Multi-property retrieval:
  Address is a brand with many hotels, so every chunk carries a `property` facet
  (e.g. address_downtown, address_beach_resort, address_sky_view, ... , or
  `brand` for brand-level pages that aren't tied to one hotel). This lets the
  agent scope a query to a single hotel the same way QSW filtered by `center`.

Language-split retrieval:
  - language=en  → English page chunks
  - language=ar  → Arabic page chunks
  - language=any → bilingual or language-agnostic content

At query time, route filter_by:
  Arabic  query → language:=[ar,any]
  English query → language:=[en,any]
  Scope to a hotel → language:=[en,any] && property:=address_downtown

Embedding model: ts/multilingual-e5-large
  Typesense-hosted, no external API key required. Handles AR + EN natively.

doc_type values:
  room_page        — rooms, suites, residences accommodation
  dining_page      — restaurants, bars, lounges, cafes
  spa_page         — spa, wellness, fitness
  offer_page       — special offers, packages, promotions
  meetings_page    — meetings, events, ballrooms, conferences
  wedding_page     — weddings, celebrations
  destination_page — location, nearby attractions, things to do
  general_page     — homepage, about, brand, contact, misc
  fact             — manually authored static facts (per-property contact, overview)
"""


def create_collections(client, force_recreate: bool = False):
    """
    Create the address_knowledge collection.

    force_recreate=True  → delete and recreate (use for schema changes)
    force_recreate=False → skip if already exists; upsert handles updates
    """
    schema = _address_knowledge_schema()
    name = schema['name']

    if force_recreate:
        try:
            client.collections[name].delete()
            print(f"  Deleted existing: {name}")
        except Exception:
            pass
        client.collections.create(schema)
        print(f"  ✅ Created: {name}")
        return

    try:
        info = client.collections[name].retrieve()
        print(f"  ✅ Collection exists ({info.get('num_documents', '?')} docs) — reusing")
        return
    except Exception:
        pass

    client.collections.create(schema)
    print(f"  ✅ Created: {name}")


def _f(name, ftype, optional=False, facet=False):
    field = {'name': name, 'type': ftype}
    if optional:
        field['optional'] = True
    if facet:
        field['facet'] = True
    return field


def _address_knowledge_schema():
    return {
        'name': 'address_knowledge',
        'fields': [
            _f('text',        'string'),
            _f('doc_type',    'string', facet=True),
            _f('property',    'string', facet=True),
            _f('language',    'string', facet=True),
            _f('title_en',    'string'),
            _f('title_ar',    'string'),
            _f('source_url',  'string', optional=True),
            _f('chunk_index', 'int32'),
            {
                'name': 'embedding',
                'type': 'float[]',
                'embed': {
                    'from': ['text'],
                    'model_config': {'model_name': 'ts/multilingual-e5-large'},
                },
            },
        ],
    }
