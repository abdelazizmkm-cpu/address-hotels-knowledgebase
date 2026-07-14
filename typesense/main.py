"""
Address Hotels + Resorts RAG Knowledgebase — Main Orchestration Script

Pipeline:
  1. Connect to Typesense Cloud  (credentials from .env)
  2. Create address_knowledge collection
  3. Load Apify crawl output (data/apify_pages.json)
     → Run scripts/apify_crawl.py FIRST if this file doesn't exist yet
  4. Build chunks from Apify pages (tagged by property + language + doc_type)
  5. Save checkpoint
  6. Add static facts and store all chunks in Typesense

Run:
  python -X utf8 main.py

Pass --fresh to drop and recreate the collection from scratch:
  python -X utf8 main.py --fresh

Pass --no-apify to skip Apify data and only upsert static facts:
  python -X utf8 main.py --no-apify
"""
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
import typesense
from schemas import create_collections

load_dotenv()

TYPESENSE_NODES = [
    os.getenv('TYPESENSE_NODE_1', ''),
    os.getenv('TYPESENSE_NODE_2', ''),
    os.getenv('TYPESENSE_NODE_3', ''),
]
TYPESENSE_PORT     = os.getenv('TYPESENSE_PORT', '443')
TYPESENSE_PROTOCOL = os.getenv('TYPESENSE_PROTOCOL', 'https')
TYPESENSE_API_KEY  = os.getenv('TYPESENSE_API_KEY', '')

COLLECTION   = 'address_knowledge'
BATCH_SIZE   = 100
MIN_TEXT_LEN = 150

APIFY_PAGES_PATH = Path(__file__).resolve().parent.parent / 'data' / 'apify_pages.json'
CHECKPOINT_PATH  = Path(__file__).resolve().parent.parent / 'data' / 'chunks_checkpoint.json'


# ── Static facts ──────────────────────────────────────────────────────────────
# Manually authored facts that guarantee critical info (per-property contact,
# overview, address) is always retrievable even when a page scrapes poorly.
#
# Authored ONLY where retrieval had a real gap. Contact-retrieval testing showed
# 8/10 UAE properties return their contact reliably from crawled content; two did
# not (their main reservations line was never cleanly crawled — only department
# sub-page numbers). These facts fix exactly those two, from verified page data.
# Do NOT invent values. Each fact MUST carry a `property` key.
STATIC_FACTS: list[dict] = [
    {
        'id': 'fact_montgomerie_contact_en',
        'text': (
            "Address Montgomerie — Contact & Location\n\n"
            "Phone: +971 4 390 5600\n"
            "Email: stay@addresshotels.com\n"
            "Address: Emirates Hills, P.O. Box 36700, Dubai, UAE\n\n"
            "Address Montgomerie is a 5-star hotel in Emirates Hills, Dubai, "
            "overlooking a Colin Montgomerie-designed 18-hole championship golf "
            "course. To book, contact the hotel by the phone or email above, or "
            "book on the official website."
        ),
        'doc_type': 'fact', 'property': 'address_montgomerie', 'language': 'en',
        'title_en': 'Address Montgomerie — Contact & Location',
        'title_ar': 'العنوان مونتجمري — التواصل والموقع',
        'source_url': 'https://www.addresshotels.com/en/hotels/address-montgomerie/',
        'chunk_index': 0,
    },
    {
        'id': 'fact_montgomerie_contact_ar',
        'text': (
            "العنوان مونتجمري — التواصل والموقع\n\n"
            "الهاتف: +971 4 390 5600\n"
            "البريد الإلكتروني: stay@addresshotels.com\n"
            "العنوان: تلال الإمارات، ص.ب. 36700، دبي، الإمارات العربية المتحدة\n\n"
            "العنوان مونتجمري فندق خمس نجوم في تلال الإمارات بدبي، يطلّ على ملعب "
            "غولف للبطولات من 18 حفرة صمّمه كولين مونتجمري. للحجز، تواصل مع الفندق "
            "عبر الهاتف أو البريد الإلكتروني أعلاه أو عبر الموقع الرسمي."
        ),
        'doc_type': 'fact', 'property': 'address_montgomerie', 'language': 'ar',
        'title_en': 'Address Montgomerie — Contact & Location',
        'title_ar': 'العنوان مونتجمري — التواصل والموقع',
        'source_url': 'https://www.addresshotels.com/ar/hotels/address-montgomerie/',
        'chunk_index': 0,
    },
    {
        'id': 'fact_palace_dch_contact_en',
        'text': (
            "Palace Dubai Creek Harbour — Contact & Location\n\n"
            "Phone: +971 4 559 8888\n"
            "Hotel inquiries: info.padch@palacehotels.com\n"
            "Reservations: stayatpalacecreek@palacehotels.com\n"
            "Dining reservations: dineatcreek@palacehotels.com\n"
            "Location: Dubai Creek Harbour, Dubai, UAE\n\n"
            "Palace Dubai Creek Harbour is a 5-star hotel at Dubai Creek Harbour. "
            "To book, contact the hotel by the phone or reservations email above, "
            "or book on the official website."
        ),
        'doc_type': 'fact', 'property': 'palace_dubai_creek_harbour', 'language': 'en',
        'title_en': 'Palace Dubai Creek Harbour — Contact & Location',
        'title_ar': 'بالاس دبي كريك هاربر — التواصل والموقع',
        'source_url': 'https://www.addresshotels.com/en/hotels/palace-dubai-creek-harbour/',
        'chunk_index': 0,
    },
    {
        'id': 'fact_palace_dch_contact_ar',
        'text': (
            "بالاس دبي كريك هاربر — التواصل والموقع\n\n"
            "الهاتف: +971 4 559 8888\n"
            "استفسارات الفندق: info.padch@palacehotels.com\n"
            "الحجوزات: stayatpalacecreek@palacehotels.com\n"
            "حجوزات المطاعم: dineatcreek@palacehotels.com\n"
            "الموقع: دبي كريك هاربر، دبي، الإمارات العربية المتحدة\n\n"
            "بالاس دبي كريك هاربر فندق خمس نجوم في دبي كريك هاربر. للحجز، تواصل مع "
            "الفندق عبر الهاتف أو بريد الحجوزات أعلاه أو عبر الموقع الرسمي."
        ),
        'doc_type': 'fact', 'property': 'palace_dubai_creek_harbour', 'language': 'ar',
        'title_en': 'Palace Dubai Creek Harbour — Contact & Location',
        'title_ar': 'بالاس دبي كريك هاربر — التواصل والموقع',
        'source_url': 'https://www.addresshotels.com/ar/hotels/palace-dubai-creek-harbour/',
        'chunk_index': 0,
    },
    # Check-in / check-out — uniform across UAE properties (confirmed on 8 property
    # pages, EN + AR). Was answering in AR but not EN; brand-level fact fixes both.
    {
        'id': 'fact_checkin_checkout_en',
        'text': (
            "Check-in & Check-out — Address Hotels + Resorts (UAE)\n\n"
            "Standard check-in time: 3:00 PM (15:00).\n"
            "Standard check-out time: 12:00 PM (noon).\n"
            "Early check-in from 11:00 AM and late check-out until 4:00 PM are "
            "available on request, subject to availability.\n\n"
            "These standard times apply across Address Hotels + Resorts properties "
            "in the UAE."
        ),
        'doc_type': 'fact', 'property': 'brand', 'language': 'en',
        'title_en': 'Check-in & Check-out Times',
        'title_ar': 'مواعيد تسجيل الوصول والمغادرة',
        'source_url': 'https://www.addresshotels.com/en/',
        'chunk_index': 0,
    },
    {
        'id': 'fact_checkin_checkout_ar',
        'text': (
            "مواعيد تسجيل الوصول والمغادرة — فنادق ومنتجعات العنوان (الإمارات)\n\n"
            "وقت تسجيل الوصول القياسي: الساعة 3:00 عصراً (15:00).\n"
            "وقت تسجيل المغادرة القياسي: الساعة 12:00 ظهراً.\n"
            "يتوفّر تسجيل وصول مبكر من الساعة 11:00 صباحاً وتسجيل مغادرة متأخّر حتى "
            "الساعة 4:00 عصراً عند الطلب، حسب توفّر الغرف.\n\n"
            "تنطبق هذه المواعيد القياسية على فنادق ومنتجعات العنوان في الإمارات."
        ),
        'doc_type': 'fact', 'property': 'brand', 'language': 'ar',
        'title_en': 'Check-in & Check-out Times',
        'title_ar': 'مواعيد تسجيل الوصول والمغادرة',
        'source_url': 'https://www.addresshotels.com/ar/',
        'chunk_index': 0,
    },
]


# ── Typesense client ──────────────────────────────────────────────────────────

def load_typesense_client():
    nodes = [h for h in TYPESENSE_NODES if h]
    if not nodes or not TYPESENSE_API_KEY:
        raise ValueError(
            "Missing Typesense credentials. Set TYPESENSE_NODE_1/2/3 and "
            "TYPESENSE_API_KEY in .env"
        )
    return typesense.Client({
        'nodes': [{'host': h, 'port': TYPESENSE_PORT, 'protocol': TYPESENSE_PROTOCOL}
                  for h in nodes],
        'api_key': TYPESENSE_API_KEY,
        'connection_timeout_seconds': 300,
    })


# ── Nav boilerplate stripper ──────────────────────────────────────────────────

_NAV_PATTERNS = re.compile(
    r'(Cookie Policy|Accept Cookies|Privacy Policy|Skip to content'
    r'|Share this page|Breadcrumb|Menu|Toggle navigation'
    r'|Best Rate Guaranteed)',
    re.IGNORECASE,
)

# Booking-widget (Eat App reservation modal + hotel selector + date picker)
# boilerplate that the crawler appends to many pages. We strip the UI chrome and
# the fake sample reservation, but KEEP useful booking content — real reservation
# phone/email, check-in/out times, opening hours, "book directly" sentences —
# because those are full sentences, not the short UI labels blocked here.
_BOILERPLATE_SUBSTR = (
    'powered by eat app', 'protected by recaptcha', 'recaptcha requires verification',
    'booking reference #', 'john.smith@xyzmail.com', 'john smith', 'allergic to nuts',
    'select & enter your code', 'select number of guests', 'select a hotel and check',
    'select a table type', 'select a time', 'select a date', 'select a code type',
    'i am booking for someone else', 'you can apply upto two codes', "you can't apply",
    'this combination is not valid', 'iata code', 'corporate code', 'promo code',
    'group code', 'add a room', 'looking to make a group booking', 'special instructions',
    'guest information', 'guest info', 'booking details', 'enter your code',
    # Arabic booking-widget chrome (hotel selector, date picker, Eat App modal)
    'اختر الفنادق', 'كل الفنادق', 'تسجيل الوصول - تسجيل المغادرة',
    'تسجيل الوصول – تسجيل المغادرة', 'الغرف والضيوف', 'رمز الخصم', 'البحث عن غرف',
    'إضافة غرفة', 'أحجز لشخص', 'بادر بالحجز الآن', 'اختر فندقًا وتحقق',
    'اختيار فندق والتحقق', 'حدد تاريخًا', 'اختر هذه التواريخ', 'يتمّ عرض جميع الأسعار',
    'حجز المطاعم', 'حجوزات المطاعم', 'معلومات عن النزيل', 'معلومات النزيل',
    'تفاصيل الحجز', 'إرشادات خاص', 'طلبات خاص', 'اختيار الوقت', 'اختر نوع الطاولة',
    'هل ترغب في إجراء حجز', 'اتصل بفريقنا لحجوزات', 'رمز اتحاد النقل الجوي',
    'الرمز الترويجي', 'رمز المجموعة', 'رمز الشركة', 'يمكنك استخدام ما يصل إلى رمزين',
    'هذه التوليفة غير صالحة', 'اختيار فندق', 'الهاتف الجوال',
)

_BOILERPLATE_EXACT = {
    'stay', 'offer:', 'offer', 'dine', 'done', 'modify', 'clear', 'search', 'apply',
    'next', 'previous', 'book now', 'find rooms', 'choose hotels', 'all hotels',
    'enter code', 'code', 'dates', 'check in - check out', 'check in – check out',
    'room and guests', 'rooms & guests', '1 adult, 0 child', '1 adult, 0 children',
    'adult (12+)', 'adults (12+)', 'children (4-11)', 'reserve now', 'check availability',
    'standard seating', 'window seating', 'hightop seating', 'bar seating',
    'counter seating', 'outdoor seating', 'global bistronomy', 'the restaurant',
    'first name', 'last name', 'email', 'mobile phone', 'special request',
    'view slide 1', 'view slide 2', 'view slide 3', '05122354234',
    # Section-nav menu labels (gallery/landing page tabs) — pure navigation
    'hotel overview', 'unparalleled comfort', 'exquisite dining',
    'world-class relaxation', 'world-class leisure', 'enchanting moments',
    'meeting and events', 'momentous occasions', 'video',
    'jan', 'feb', 'mar', 'apr', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec',
    'mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun',
    # Arabic date-picker + selector chrome (exact standalone lines)
    'تمّ', 'تم', 'حذف', 'البحث', 'تطبيق', 'تعديل', 'الاسم الأول', 'اسم العائلة',
    'البريد الالكتروني', 'البريد الإلكترونيّ', 'الإمارات العربية المتحدة',
    'الاثنين', 'الإثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت', 'الأحد',
    'يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو', 'يوليو', 'أغسطس',
    'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر',
}

_MONTHS = ('january', 'february', 'march', 'april', 'may', 'june', 'july',
           'august', 'september', 'october', 'november', 'december')
_COUNTRY_CODE_RE = re.compile(r'\+\d{1,4}\s*\([^)]*\)')

# Lines mentioning a non-UAE Address location (from the booking widget's
# worldwide hotel-selector list, or stray cross-brand references). Dropped so no
# non-UAE content survives in a UAE-only KB.
_NON_UAE_LINE_TERMS = (
    'istanbul', 'makkah', 'jabal omar', 'bahrain', 'marassi',
    'north coast', 'egypt', 'saudi arabia', 'turkey',
    # Arabic non-UAE location names (from the worldwide hotel selector)
    'اسطنبول', 'إسطنبول', 'البحرين', 'مراسي', 'مكة', 'مكّة', 'جبل عمر',
    'مصر', 'تركيا', 'السعودية',
)


def _clean_apify_text(text: str) -> str:
    """Strip nav + booking-widget boilerplate; keep real content and whitespace."""
    text = _COUNTRY_CODE_RE.sub('', text)   # remove +NN (Country) phone list
    out = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            out.append('')
            continue
        low = line.lower()
        # date-picker month header ("July 2026") or bare day number (1-31)
        if len(line.split()) <= 3 and any(low.startswith(m) for m in _MONTHS) \
                and re.search(r'\b20\d\d\b', low):
            continue
        if re.fullmatch(r'\d{1,6}', line):   # date-picker day cells + AR day+price cells
            continue
        if any(s in low for s in _BOILERPLATE_SUBSTR):
            continue
        if any(t in low for t in _NON_UAE_LINE_TERMS):
            continue
        if low in _BOILERPLATE_EXACT:
            continue
        if len(line.split()) < 4 and _NAV_PATTERNS.search(line):
            continue
        out.append(line)
    # Collapse a non-empty line that just repeats the previous non-empty line
    # (the booking widget echoes labels like "Address Dubai Mall" several times).
    deduped, last_ne = [], None
    for line in out:
        if line == '':
            deduped.append('')
            continue
        if line == last_ne:
            continue
        deduped.append(line)
        last_ne = line
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(deduped)).strip()


# ── UAE-only content filter ───────────────────────────────────────────────────
# Drop any page about an Address property outside the UAE. These leak in through
# the brand-level /en/offers/ and /en/dine/ aggregator pages, which list offers
# and venues for every Address property worldwide (Istanbul, Makkah, Bahrain,
# Egypt/Marassi). This KB is UAE-only.
_EXCLUDED_TERMS = (
    'istanbul', 'makkah', 'jabal omar', 'jabal-omar', 'bahrain',
    'marassi', 'north coast', 'north-coast',
    # Arabic property/city names that appear in non-UAE page titles
    'اسطنبول', 'إسطنبول', 'البحرين', 'مراسي', 'مكة', 'مكّة', 'جبل عمر',
)
_UAE_ANCHORS = (
    'dubai', 'fujairah', 'uae', 'united arab emirates', 'jbr', 'downtown',
    'creek harbour', 'emirates hills', 'jumeirah', 'al aqah',
    # Arabic anchors
    'دبي', 'الفجيرة', 'الإمارات', 'جميرا', 'وسط المدينة', 'كريك هاربر',
)


# Non-UAE dialing codes (Bahrain +973, Saudi +966, Turkey +90, Egypt +20).
# UAE numbers are +971, so a local non-UAE contact number marks a non-UAE page
# even when its title gives no country away.
_NON_UAE_PHONE_RE = re.compile(r'\+(?:973|966|90|20)\s*\d')


# ── Known upstream errors on addresshotels.com ────────────────────────────────
# The site's Palace Beach Resort Fujairah spa page is TITLED "The Spa at Address
# Boulevard" (a template copy-paste error) even though its body correctly
# describes Palace Beach Resort Fujairah. Left uncorrected, the agent names the
# WRONG hotel when asked about Palace Fujairah's spa. Reported to the client
# 2026-07-13; correct here until they fix the page.
_SOURCE_CORRECTIONS = {
    'palace-beach-resort-fujairah/wellness/spa': [
        ('The Spa at Address Boulevard', 'The Spa at Palace Beach Resort Fujairah'),
    ],
}


def _apply_source_corrections(url: str, text: str, title: str) -> tuple[str, str]:
    for frag, pairs in _SOURCE_CORRECTIONS.items():
        if frag in url:
            for wrong, right in pairs:
                text = text.replace(wrong, right)
                title = title.replace(wrong, right)
    return text, title


def _is_non_uae(url: str, title: str, text: str) -> bool:
    hay = f'{url} {title}'.lower()
    if any(t in hay for t in _EXCLUDED_TERMS):
        return True
    if _NON_UAE_PHONE_RE.search(text):
        return True
    body = text.lower()
    if any(t in body for t in _EXCLUDED_TERMS) and not any(a in body for a in _UAE_ANCHORS):
        return True
    return False


def _infer_language_from_url(url: str) -> str:
    from urllib.parse import urlparse
    path = urlparse(url).path.lower()
    if path.startswith('/ar/') or path.rstrip('/') == '/ar':
        return 'ar'
    return 'en'


# Property inference. URL-slug → canonical hotel key mapping.
# Confirmed against addresshotels.com's UAE portfolio (10 properties) 2026-07-09.
# Order matters: most specific slugs FIRST, because shorter slugs are substrings
# of longer ones (e.g. 'address-beach-resort' is inside 'address-beach-resort-
# fujairah', and 'palace-downtown' must win before any 'downtown' match).
# Match on the full hyphenated slug, not bare words, to avoid palace/address mixups.
_PROPERTY_MAP = [
    # Fujairah (2) — must precede the plain address-beach-resort entry
    ('address-beach-resort-fujairah', 'address_beach_resort_fujairah'),
    ('palace-beach-resort-fujairah',  'palace_beach_resort_fujairah'),
    # Dubai (8)
    ('palace-dubai-creek-harbour',    'palace_dubai_creek_harbour'),
    ('address-creek-harbour',         'address_creek_harbour'),
    ('palace-downtown',               'palace_downtown'),
    ('address-downtown',              'address_downtown'),
    ('address-dubai-mall',            'address_dubai_mall'),
    ('address-montgomerie',           'address_montgomerie'),
    ('address-sky-view',              'address_sky_view'),
    ('address-beach-resort',          'address_beach_resort'),
]


def _infer_property(url: str) -> str:
    from urllib.parse import urlparse
    path = urlparse(url).path.lower()
    for needle, key in _PROPERTY_MAP:
        if needle in path:
            return key
    return 'brand'


def _infer_doc_type(url: str) -> str:
    from urllib.parse import urlparse
    path = urlparse(url).path.lower()
    if any(k in path for k in ('room', 'suite', 'accommodation', 'residence', 'villa',
                                'stay')):
        return 'room_page'
    if any(k in path for k in ('restaurant', 'bar', 'dining', 'lounge', 'cafe',
                                'food', 'eat', 'cuisine')):
        return 'dining_page'
    if any(k in path for k in ('spa', 'fitness', 'wellness', 'health', 'gym', 'pool')):
        return 'spa_page'
    if any(k in path for k in ('offer', 'deal', 'package', 'promotion', 'special')):
        return 'offer_page'
    if any(k in path for k in ('meeting', 'event', 'conference', 'ballroom', 'corporate',
                                'mice')):
        return 'meetings_page'
    if any(k in path for k in ('wedding', 'bridal', 'bride', 'celebration')):
        return 'wedding_page'
    if any(k in path for k in ('destination', 'explore', 'attraction', 'location',
                                'nearby', 'around', 'things-to-do')):
        return 'destination_page'
    return 'general_page'


def _make_id(url: str) -> str:
    return 'apify_' + re.sub(r'[^a-z0-9]+', '_', url.lower().split('?')[0]).strip('_')


# ── Text splitting ────────────────────────────────────────────────────────────

MAX_CHUNK_CHARS = 1400   # target + hard cap. Smaller than a page so a single fact
                         # (one FAQ answer) isn't buried in a page-sized blob.


def _split_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """Split into <= max_chars chunks.

    Paragraph breaks first, but any paragraph over the cap is further broken by
    lines — the crawler often emits pages as one single-\\n block with no
    blank-line paragraph breaks, so paragraph-only splitting left 6-7k chunks
    that drowned individual facts.
    """
    if len(text) <= max_chars:
        return [text]

    units: list[str] = []
    for para in re.split(r'\n{2,}', text):
        para = para.strip()
        if not para:
            continue
        if len(para) <= max_chars:
            units.append(para)
            continue
        buf = ''
        for line in para.split('\n'):
            line = line.strip()
            if not line:
                continue
            while len(line) > max_chars:            # a single monster line
                units.append(line[:max_chars])
                line = line[max_chars:]
            if buf and len(buf) + len(line) + 1 > max_chars:
                units.append(buf)
                buf = ''
            buf = f'{buf}\n{line}' if buf else line
        if buf:
            units.append(buf)

    chunks: list[str] = []
    cur = ''
    for u in units:
        if cur and len(cur) + len(u) + 2 > max_chars:
            chunks.append(cur)
            cur = ''
        cur = f'{cur}\n\n{u}' if cur else u
    if cur:
        chunks.append(cur)
    return chunks


# ── Page → chunks ─────────────────────────────────────────────────────────────

def page_to_chunks(item: dict) -> list[dict]:
    url      = item.get('url', '')
    metadata = item.get('metadata') or {}
    title    = (metadata.get('title') or '').strip()
    text_raw = (item.get('text') or item.get('markdown') or '').strip()

    # UAE-only KB: skip pages about non-UAE Address properties.
    if _is_non_uae(url, title, text_raw):
        return []

    # Skip gallery / photos pages — they are pure section-nav menus, no content.
    low = f'{url} {title}'.lower()
    if 'photos-and-videos' in low or '/gallery' in low or '| gallery' in low:
        return []

    # Correct known upstream errors on the source site before chunking.
    text_raw, title = _apply_source_corrections(url, text_raw, title)

    text = _clean_apify_text(text_raw)
    if len(text) < MIN_TEXT_LEN:
        return []

    language  = _infer_language_from_url(url)
    doc_type  = _infer_doc_type(url)
    prop      = _infer_property(url)
    title_en  = title if language == 'en' else ''
    title_ar  = title if language == 'ar' else ''
    id_base   = _make_id(url)
    sub_texts = _split_text(text)

    chunks = []
    for i, sub in enumerate(sub_texts):
        chunk_text = sub if i == 0 else (f'{title}\n\n{sub}' if title else sub)
        chunks.append({
            'id':          f'{id_base}_{i}',
            'text':        chunk_text,
            'doc_type':    doc_type,
            'property':    prop,
            'language':    language,
            'title_en':    title_en,
            'title_ar':    title_ar,
            'source_url':  url,
            'chunk_index': i,
        })
    return chunks


# ── Storage ───────────────────────────────────────────────────────────────────

def store_chunks(client, chunks: list[dict]):
    if not chunks:
        print("  No chunks to store.")
        return

    total_success = 0
    total_failed  = []

    for batch_start in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[batch_start:batch_start + BATCH_SIZE]
        batch_end = batch_start + len(batch)
        print(f"  Storing chunks {batch_start + 1}–{batch_end} of {len(chunks)}...")

        jsonl = '\n'.join(json.dumps(c, ensure_ascii=False) for c in batch)
        for attempt in range(1, 4):
            try:
                raw = client.collections[COLLECTION].documents.import_(
                    jsonl, {'action': 'upsert'}
                )
                break
            except Exception as e:
                if attempt == 3:
                    print(f"    ⚠️  Batch failed after 3 attempts: {e}")
                    raw = None
                    break
                import time as _time
                wait = 15 * attempt
                print(f"    ⚠️  Attempt {attempt} failed, retrying in {wait}s...")
                _time.sleep(wait)

        if raw is None:
            continue

        results = [json.loads(r) for r in raw.splitlines() if r.strip()]
        ok      = sum(1 for r in results if r.get('success'))
        failed  = [r for r in results if not r.get('success')]
        total_success += ok
        total_failed.extend(failed)

        status = f"    ✅ {ok}/{len(batch)}"
        if failed:
            status += f", ⚠️  {len(failed)} failed"
            for r in failed[:3]:
                print(f"      ⚠️  {r}")
        print(status)

    print(f"  ✅ Total stored: {total_success} | Failed: {len(total_failed)}")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print("=" * 60)
    print("Address Hotels + Resorts RAG Knowledgebase Builder")
    print("=" * 60)

    force_recreate = '--fresh'    in sys.argv
    no_apify       = '--no-apify' in sys.argv

    print("\n[1/5] Connecting to Typesense Cloud...")
    client = load_typesense_client()
    print("  ✅ Connected")

    print("\n[2/5] Creating collection...")
    create_collections(client, force_recreate=force_recreate)

    all_chunks: list[dict] = []

    if no_apify:
        print("\n[3–4/5] Skipping Apify data (--no-apify)")
    elif CHECKPOINT_PATH.exists():
        print(f"\n[3–4/5] Loading from checkpoint ({CHECKPOINT_PATH})...")
        with open(CHECKPOINT_PATH, encoding='utf-8') as f:
            all_chunks = json.load(f)
        print(f"  ✅ {len(all_chunks)} chunks from checkpoint — skipping Apify processing")
    else:
        if not APIFY_PAGES_PATH.exists():
            print(f"\n❌  {APIFY_PAGES_PATH} not found.")
            print("    Run scripts/apify_crawl.py first, then re-run this script.")
            print("    Or pass --no-apify to only index static facts.\n")
            sys.exit(1)

        print(f"\n[3/5] Processing Apify HTML pages from {APIFY_PAGES_PATH}...")
        with open(APIFY_PAGES_PATH, encoding='utf-8') as f:
            apify_pages = json.load(f)
        print(f"  {len(apify_pages)} pages loaded")

        page_chunks = []
        skipped = 0
        for item in apify_pages:
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

        print(f"  ✅ {len(page_chunks)} chunks from {len(apify_pages) - skipped} pages "
              f"({skipped} skipped below threshold)")
        print(f"  Language: {dict(sorted(by_lang.items()))}")
        print(f"  Doc type: {dict(sorted(by_type.items()))}")
        print(f"  Property: {dict(sorted(by_prop.items()))}")
        all_chunks.extend(page_chunks)

        print(f"\n[4/5] Saving checkpoint...")
        CHECKPOINT_PATH.parent.mkdir(exist_ok=True)
        with open(CHECKPOINT_PATH, 'w', encoding='utf-8') as f:
            json.dump(all_chunks, f, ensure_ascii=False)
        print(f"  💾 Checkpoint saved: {len(all_chunks)} chunks")

    print(f"\n[5/5] Adding {len(STATIC_FACTS)} static facts and storing all chunks...")
    final_chunks = all_chunks + STATIC_FACTS
    for i, chunk in enumerate(final_chunks):
        chunk['chunk_index'] = i

    store_chunks(client, final_chunks)

    by_lang = {}
    by_type = {}
    by_prop = {}
    for c in final_chunks:
        by_lang[c['language']] = by_lang.get(c['language'], 0) + 1
        by_type[c['doc_type']] = by_type.get(c['doc_type'], 0) + 1
        by_prop[c['property']] = by_prop.get(c['property'], 0) + 1

    print("\n" + "=" * 60)
    print("Build complete!")
    print("=" * 60)
    print(f"\n  Total chunks: {len(final_chunks)}")
    print("\n  By language:")
    for lang, count in sorted(by_lang.items()):
        print(f"    {lang:>4}: {count}")
    print("\n  By doc_type:")
    for dtype, count in sorted(by_type.items()):
        print(f"    {dtype:<20}: {count}")
    print("\n  By property:")
    for prop, count in sorted(by_prop.items()):
        print(f"    {prop:<32}: {count}")
