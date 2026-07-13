"""
Address Hotels + Resorts — Query Normalizer

Normalizes Arabic dialect queries to compact Modern Standard Arabic search terms
before vector retrieval against address_knowledge.

Problem: A user asking "عايز أعرف في إيه أكل عندكم" (Egyptian: "I want to know
what food you have") uses dialect vocabulary that may not match MSA
hotel/hospitality terms in the knowledgebase. Normalizing to "مطاعم فندق"
improves retrieval.

English queries pass through unchanged — multilingual-e5-large handles them well.
Falls back to the original query on any API error.

NOTE: the term list below is generic Address-brand hospitality vocabulary. After
the first crawl, enrich it with the real venue names (restaurants, spas, room
categories) surfaced from the site so dialect queries map onto actual content.
"""
import os

from openai import OpenAI

_client: OpenAI | None = None

_SYSTEM_PROMPT = (
    "أنت محرك بحث متخصص في فنادق ومنتجعات العنوان (Address Hotels + Resorts) الفاخرة. "
    "استخرج استعلام بحث مختصراً بالعربية الفصحى (3-7 كلمات كحد أقصى) من سؤال المستخدم. "
    "ركّز على الموضوع الرئيسي المتعلق بالفندق. "
    "إذا ذكر المستخدم اسم فندق معيّن (مثل العنوان وسط المدينة، العنوان سكاي فيو، "
    "العنوان بوليفارد، منتجع العنوان الشاطئي)، أبقِ اسم الفندق في الاستعلام. "
    "استخدم مصطلحات فندقية فصيحة من هذه القائمة عند الانطباق:\n"
    "- غرف وأجنحة الفندق\n"
    "- أسعار الغرف\n"
    "- الأجنحة الفاخرة\n"
    "- الشقق الفندقية\n"
    "- مطاعم الفندق\n"
    "- المقاهي والبارات\n"
    "- سبا ومركز العافية\n"
    "- مركز اللياقة البدنية\n"
    "- المسبح\n"
    "- قاعات المناسبات والاجتماعات\n"
    "- حفلات الزفاف\n"
    "- العروض والباقات الخاصة\n"
    "- موقع الفندق\n"
    "- التواصل مع الفندق\n"
    "- حجز غرفة\n"
    "- الإفطار وخدمة الطعام\n"
    "لا تُضمّن شرحاً أو بنية جملة كاملة أو علامة استفهام. "
    "أعد استعلام البحث فقط."
)


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    return _client


def _is_arabic(text: str) -> bool:
    return any('؀' <= c <= 'ۿ' for c in text)


def normalize_query(query: str, verbose: bool = False) -> str:
    """
    Normalize an Arabic query to compact MSA hotel search terms.

    English queries pass through unchanged. Returns the original query on
    any API error so the retrieval pipeline is never blocked.
    """
    if not _is_arabic(query):
        return query

    openai_key = os.getenv('OPENAI_API_KEY')
    if not openai_key:
        return query

    try:
        response = _get_client().chat.completions.create(
            model='gpt-4o-mini',
            messages=[
                {'role': 'system', 'content': _SYSTEM_PROMPT},
                {'role': 'user',   'content': query},
            ],
            temperature=0,
            max_tokens=50,
        )
        normalized = response.choices[0].message.content.strip()
        if not normalized:
            return query
        if verbose and normalized != query:
            print(f'  [normalized] {query!r} → {normalized!r}')
        return normalized
    except Exception as exc:
        if verbose:
            print(f'  [normalizer fallback] {exc}')
        return query
