"""
Address Hotels + Resorts — Retrieval / Veracity Test Runner

Runs the question bank in test_questions.json against the address_knowledge
Typesense collection and scores each question:

  FAQ / INFERENCE : PASS if the KB returns an in-threshold hit (the agent has
                    the material to answer). WEAK if borderline, FAIL if nothing.
  OUT_OF_SCOPE    : PASS if the KB returns NOTHING relevant (a grounded agent
                    will correctly decline). FAIL if it unexpectedly has strong
                    content for something we deliberately excluded / don't hold.

Retrieval mode needs only the Typesense keys. Answer mode (--answers) routes each
question through the `address-gpt` conversation model (run
scripts/update_system_prompt.py first) and prints the grounded reply for eyeballing.

Usage:
  python -X utf8 test/run_tests.py                     # all questions, retrieval
  python -X utf8 test/run_tests.py --type OUT_OF_SCOPE # filter by type
  python -X utf8 test/run_tests.py --property address_downtown
  python -X utf8 test/run_tests.py --num 1-10
  python -X utf8 test/run_tests.py --save              # write test_results.json
  python -X utf8 test/run_tests.py --answers           # also show address-gpt answers
"""
import argparse
import json
import os
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env')
sys.path.insert(0, str(ROOT))
try:
    from query_normalizer import normalize_query   # Arabic dialect → MSA (as in production)
except Exception:
    def normalize_query(q, verbose=False):
        return q

QUESTIONS_PATH = ROOT / 'test' / 'test_questions.json'
RESULTS_PATH   = ROOT / 'test' / 'test_results.json'

NODE      = os.getenv('TYPESENSE_NODE_1')
API_KEY   = os.getenv('TYPESENSE_API_KEY')
COLLECTION = 'address_knowledge'
MODEL_ID   = 'address-gpt'
TOP_K      = 10

# Distance thresholds (lower = closer). e5-large in-domain hits land ~0.15-0.25.
STRONG = 0.30   # clearly relevant
WEAK   = 0.38   # borderline
DIVIDER = '-' * 72


def _post(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        f'https://{NODE}:443{path}',
        data=json.dumps(body).encode(),
        headers={'X-TYPESENSE-API-KEY': API_KEY, 'Content-Type': 'application/json'},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def _lang_filter(question: str) -> str:
    """Route Arabic queries to [ar,any], English to [en,any] — same as production."""
    if any('؀' <= c <= 'ۿ' for c in question):
        return 'language:=[ar,any]'
    return 'language:=[en,any]'


def _search(question: str, prop: str | None) -> list[dict]:
    filt = _lang_filter(question)
    if prop:
        filt += f' && property:={prop}'
    body = {'searches': [{
        'collection':   COLLECTION,
        'query_by':     'embedding',
        'q':            question,
        'per_page':     TOP_K,
        'exclude_fields':'embedding',
        'filter_by':    filt,
        'vector_query': 'embedding:([], distance_threshold:0.5)',
    }]}
    return _post('/multi_search', body)['results'][0].get('hits', [])


# Phrases that mark a grounded refusal (out-of-scope handled correctly).
REFUSAL_SIGNS = (
    "i don't have information", 'i do not have information', "don't have information",
    'no information', 'can only assist', 'can only help', 'only assist with',
    'only help with', 'outside', 'not able to', "can't help", 'cannot help',
    'cannot assist', 'unable to',
    # Arabic refusals / "I can only help with Address UAE" patterns
    'لا أملك معلومات', 'لا يمكنني', 'لا أستطيع', 'خارج نطاق', 'مساعدتك فقط',
    'المساعدة فقط', 'أساعدك فقط', 'أساعدك إلا', 'المساعدة إلا',
    'فقط بمعلومات', 'فقط فيما يتعلق', 'فقط في ما يتعلق', 'فقط في ما يخص',
    'فقط فيما يخص', 'فقط في استفسارات',
)


def _answer(question: str) -> str:
    params = {'conversation': 'true', 'conversation_model_id': MODEL_ID, 'q': question}
    url = f'https://{NODE}:443/multi_search?' + urllib.parse.urlencode(params)
    body = {'searches': [{
        'collection':   COLLECTION,
        'query_by':     'embedding',
        'per_page':     10,
        'exclude_fields':'embedding',
        'filter_by':    _lang_filter(question),
        'vector_query': 'embedding:([], distance_threshold:0.35)',
    }]}
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={'X-TYPESENSE-API-KEY': API_KEY, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=90) as r:
        res = json.load(r)
    return (res.get('conversation') or {}).get('answer', '(no answer)')


def _is_refusal(answer: str) -> bool:
    a = answer.lower()
    return any(s in a for s in REFUSAL_SIGNS)


def _verdict(qtype: str, best: float | None) -> str:
    is_oos = qtype.upper() == 'OUT_OF_SCOPE'
    if is_oos:
        if best is None or best > WEAK:
            return 'PASS'
        if best > STRONG:
            return 'WEAK'
        return 'FAIL'   # KB unexpectedly has strong content
    # FAQ / INFERENCE
    if best is not None and best <= STRONG:
        return 'PASS'
    if best is not None and best <= WEAK:
        return 'WEAK'
    return 'FAIL'


def _run_one(q: dict, answers: bool) -> dict:
    num, qtype = q.get('#', '?'), q.get('type', '')
    prop, question = q.get('property'), q['question']
    hits = _search(question, prop)
    best = hits[0].get('vector_distance') if hits else None

    rec = {'number': num, 'type': qtype, 'property': prop, 'question': question,
           'expected': q.get('expected', ''), 'best_distance': best}

    ans = None
    if answers:
        try:
            ans = _answer(question)
            rec['answer'] = ans
        except Exception as e:
            ans = f'ERROR {e}'
            rec['answer'] = ans

    # Verdict: with --answers judge by the model's actual behaviour (the real
    # out-of-scope test); without, fall back to the retrieval-distance heuristic.
    if answers and ans is not None:
        refused = _is_refusal(ans)
        if qtype.upper() == 'OUT_OF_SCOPE':
            verdict = 'PASS' if refused else 'FAIL'
        else:
            verdict = 'FAIL' if refused else 'PASS'
    else:
        verdict = _verdict(qtype, best)
    rec['verdict'] = verdict

    print(f'\n{DIVIDER}')
    print(f'Q{num:>3} [{qtype}] {q.get("category","")}  ->  {verdict}')
    print(f'  Ask     : {question}')
    print(f'  Expected: {q.get("expected","")}')
    best_str = f'{best:.3f}' if best is not None else 'none'
    print(f'  Best hit: dist={best_str}')
    for h in hits[:2]:
        d = h['document']
        title = d.get('title_en') or d.get('title_ar') or '(untitled)'
        print(f'     [{h.get("vector_distance"):.3f}] ({d.get("property")}/{d.get("doc_type")}) {title[:55]}')
    if ans is not None:
        print(f'  Answer  : {ans[:280]}')
    return rec


def _summary(results: list[dict]) -> None:
    print(f'\n{"=" * 72}\nSUMMARY — {len(results)} questions\n{"=" * 72}')
    by_type: dict[str, list] = {}
    for r in results:
        by_type.setdefault(r['type'], []).append(r)
    for t, rows in sorted(by_type.items()):
        p = sum(1 for r in rows if r['verdict'] == 'PASS')
        w = sum(1 for r in rows if r['verdict'] == 'WEAK')
        f = sum(1 for r in rows if r['verdict'] == 'FAIL')
        print(f'  {t:14} PASS {p:>2} | WEAK {w:>2} | FAIL {f:>2}   (of {len(rows)})')
    total_pass = sum(1 for r in results if r['verdict'] == 'PASS')
    print(f'  {"TOTAL":14} PASS {total_pass}/{len(results)}')


def _parse_nums(spec: str) -> set[int]:
    nums: set[int] = set()
    for part in spec.split(','):
        part = part.strip()
        if '-' in part:
            a, b = part.split('-', 1)
            nums.update(range(int(a), int(b) + 1))
        elif part:
            nums.add(int(part))
    return nums


def main() -> None:
    ap = argparse.ArgumentParser(description='Address Hotels retrieval test runner')
    ap.add_argument('--type', help='FAQ | INFERENCE | OUT_OF_SCOPE')
    ap.add_argument('--property', help='filter by property key')
    ap.add_argument('--num', help='question numbers, e.g. 1-10 or 5,12')
    ap.add_argument('--answers', action='store_true', help='also query address-gpt for the grounded answer')
    ap.add_argument('--save', action='store_true', help='write test/test_results.json')
    args = ap.parse_args()

    if not NODE or not API_KEY:
        print('Missing Typesense creds in .env'); sys.exit(1)

    with open(QUESTIONS_PATH, encoding='utf-8') as f:
        questions = json.load(f)
    if args.type:
        questions = [q for q in questions if q.get('type', '').upper() == args.type.upper()]
    if args.property:
        questions = [q for q in questions if q.get('property') == args.property]
    if args.num:
        keep = _parse_nums(args.num)
        questions = [q for q in questions if q.get('#') in keep]
    if not questions:
        print('No questions match the filters.'); sys.exit(0)

    print(f'Running {len(questions)} question(s) against {COLLECTION}...')
    results = [_run_one(q, args.answers) for q in questions]
    _summary(results)

    if args.save:
        payload = {'run_at': datetime.now(timezone.utc).isoformat(),
                   'total': len(results), 'results': results}
        with open(RESULTS_PATH, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f'\nSaved {RESULTS_PATH}')


if __name__ == '__main__':
    main()
