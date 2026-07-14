# Address Hotels + Resorts KB — Test Scenarios

Veracity + retrieval test coverage for the `address_knowledge` Typesense collection (**~430 bilingual chunks, 10 UAE properties, EN + Arabic**, embedding model `ts/multilingual-e5-large`, conversation model `address-gpt`).

Three question types, matching prior builds (Elithair, Qatar Automotives):
- **FAQ** — direct factual questions the agent must answer from the knowledge base.
- **Inference** — multi-hop questions where the right hotel isn't named and must be deduced.
- **Out-of-scope** — questions the agent must **decline** (non-UAE Address properties, non-hotel requests, or anything not in the KB). It must say it doesn't have the information, never invent.

Arabic scenarios are answered in **Modern Standard Arabic (MSA)**, including Gulf / Egyptian / Levantine dialect inputs. Run the automated grader with `python -X utf8 test/run_tests.py --answers` (routes each question through `address-gpt`; Arabic queries auto-filtered to `language:=[ar,any]`).

**Latest result (2026-07-11):** FAQ 24/24 · Inference 11/11 · Out-of-scope 11/12 → **46/47** (the one miss is an API timeout, not a wrong answer). Expected answers below are grounded in the actual crawled/indexed content.

---

## A. FAQ — English

| #  | Send | Expected | Result |
|----|------|----------|--------|
| A1 | What's special about Address Beach Resort? | World's highest outdoor infinity pool (ZETA Seventy Seven, ~293.9 m, Level 77); two Guinness World Records; two 77-storey towers in JBR |  |
| A2 | Where is the spa at Address Beach Resort, and how many rooms? | The Spa at Address, Level 75 — highest spa in Dubai; **9 treatment rooms** |  |
| A3 | Where is Address Beach Resort located? | Jumeirah Beach Residence (JBR), Dubai Marina; views of Bluewaters Island and Ain Dubai |  |
| A4 | What restaurants are at Address Beach Resort? | ZETA Seventy Seven, The Restaurant, The Beach Grill, The Lounge; plus Mott 32, OSH DEL MAR, DREAMS |  |
| A5 | How do I contact Address Beach Resort reservations? | +971 4 879 8899 · StayAtBeachResort@addresshotels.com |  |
| A6 | Where is Address Downtown and what are its views? | Downtown Dubai; views of Burj Khalifa and the Dubai Fountain |  |
| A7 | What is Address Sky View? | 5-star hotel of two towers connected by a sky bridge, Downtown Dubai |  |
| A8 | Which Address hotel connects directly to Dubai Mall? | Address Dubai Mall — direct connection from Level 1. **Note:** the Address Downtown page also states it "offers direct access to Dubai Mall", so naming Address Downtown is not an invention — don't mark it as one |  |
| A9 | Where is Address Montgomerie? | Emirates Hills, overlooking Dubai's premier golf course |  |
| A10 | Where is Address Creek Harbour? | Dubai Creek Harbour |  |
| A11 | Where is Palace Downtown? | Downtown Dubai |  |
| A12 | Does Palace Dubai Creek Harbour have a spa? | Yes — a spa at Dubai Creek Harbour |  |
| A13 | Is Address Beach Resort Fujairah good for families? | Yes — Qix Kids Club, family pool, beachfront pool villas |  |
| A14 | Where is Palace Beach Resort Fujairah? | **Al Faseel, Corniche Road, Fujairah**, overlooking the Indian Ocean. (Corrected 2026-07-13 — an earlier version of this doc wrongly said "Al Aqah"; **Al Aqah is Address Beach Resort Fujairah**, a different property. It also has a **Qix Club**.) |  |
| A15 | What is The Spa Longevity? | Address's signature luxury wellness spa concept |  |
| A16 | What is U by Emaar? | Emaar's loyalty program — earn/redeem Upoints across Emaar hospitality, leisure, retail |  |
| A17 | What are the check-in and check-out times? | Check-in 3:00 PM (15:00), check-out 12:00 noon; early check-in 11:00 AM / late check-out 4:00 PM on request |  |
| A18 | How do I contact Address Montgomerie / Palace Dubai Creek Harbour? | Montgomerie: +971 4 390 5600 · stay@addresshotels.com. Palace DCH: +971 4 559 8888 · stayatpalacecreek@palacehotels.com |  |

## B. Inference — English (deduce the hotel)

| #  | Send | Expected | Result |
|----|------|----------|--------|
| B1 | I want a beachfront Dubai hotel with a record-breaking pool. | Address Beach Resort (JBR) |  |
| B2 | Which Address hotel is best for Burj Khalifa views? | Address Downtown / Address Sky View |  |
| B3 | I'm going to Fujairah with kids — which resort and what's there for children? | Address Beach Resort Fujairah — Qix Kids Club |  |
| B4 | Which Address hotel suits a golf trip? | Address Montgomerie (Emirates Hills golf course) |  |
| B5 | I want to stay connected to shopping. | Address Dubai Mall |  |
| B6 | Where's the highest spa in Dubai? | The Spa at Address Beach Resort, Level 75 |  |
| B7 | Which Address hotels are in Downtown Dubai? | Address Downtown, Palace Downtown, Address Dubai Mall, Address Sky View |  |
| B8 | Where can I eat at Mott 32? | Address Beach Resort |  |
| B9 | A quiet waterfront stay away from the marina buzz? | Dubai Creek Harbour (Address / Palace Creek Harbour) |  |

## C. Out-of-scope — English (must decline)

| #  | Send | Expected | Result |
|----|------|----------|--------|
| C1 | Tell me about Address Jabal Omar Makkah. | Decline — KB covers UAE Address properties only |  |
| C2 | Book me a room at Address Istanbul. | Decline — outside UAE scope |  |
| C3 | What are the rates at Address Beach Resort Bahrain? | Decline — out of scope |  |
| C4 | Tell me about Address Marassi in Egypt. | Decline — out of scope |  |
| C5 | Can you book me a flight to Dubai? | Decline — not a hotel service |  |
| C6 | What's the weather in Dubai this week? | Decline — not in the KB |  |
| C7 | Recommend good restaurants outside the Address hotels. | Decline — only Address venues |  |
| C8 | What's the nightly room rate at Address Downtown? | No fixed nightly price — direct to booking, don't invent |  |
| C9 | Tell me about the Burj Al Arab hotel. | Decline — not an Address property |  |

---

## D. FAQ — Arabic (answered in MSA)

| #  | Send | Expected | Result |
|----|------|----------|--------|
| D1 | أين يقع سبا منتجع شاطئ العنوان وكم عدد غرفه؟ | الطابق 75، الأعلى في دبي، تسع غرف علاج |  |
| D2 | ما الذي يميّز منتجع شاطئ العنوان؟ | أعلى مسبح لانهائي في العالم (الطابق 77)، رقمان قياسيان في غينيس |  |
| D3 | أين يقع فندق العنوان وسط المدينة وما إطلالاته؟ | وسط مدينة دبي، إطلالات على برج خليفة ونافورة دبي |  |
| D4 | هل منتجع شاطئ العنوان الفجيرة مناسب للعائلات؟ | نعم — نادي كيكس، مسابح عائلية |  |
| D5 | كيف يمكنني حجز إقامة في منتجع شاطئ العنوان؟ | عبر الموقع أو فريق الحجوزات: 97148798899+ / StayAtBeachResort@addresshotels.com |  |

## E. Arabic dialects (input in dialect → answered in MSA)

| #  | Send | Dialect | Expected | Result |
|----|------|---------|----------|--------|
| E1 | وش يميّز منتجع شاطئ العنوان عن باقي الفنادق؟ | Gulf | MSA answer — أعلى مسبح لانهائي، رقمان قياسيان في غينيس |  |
| E2 | عايز أعرف إزاي أحجز في منتجع شاطئ العنوان؟ | Egyptian | MSA answer — طريقة الحجز + رقم/بريد التواصل |  |
| E3 | شو المطاعم يلّي بمنتجع شاطئ العنوان؟ | Levantine | MSA answer — قائمة المطاعم |  |

## F. Inference & Out-of-scope — Arabic

| #  | Send | Type | Expected | Result |
|----|------|------|----------|--------|
| F1 | أريد فندقاً على الشاطئ في دبي مع مسبح يحطّم الأرقام القياسية. | Inference | منتجع شاطئ العنوان (جي بي آر) |  |
| F2 | أي فندق من العنوان مناسب لرحلة غولف؟ | Inference | العنوان مونتجمري (تلال الإمارات) |  |
| F3 | حدّثني عن فندق العنوان إسطنبول. | Out-of-scope | يرفض — فنادق العنوان في الإمارات فقط |  |
| F4 | احجز لي رحلة طيران إلى دبي. | Out-of-scope | يرفض — ليست خدمة فندقية |  |
| F5 | ما هي حالة الطقس في دبي هذا الأسبوع؟ | Out-of-scope | يرفض — ليست ضمن قاعدة المعرفة |  |

---

## G. Property-scoping sanity check

The `property` facet isolates a hotel. A generic question scoped to one property must return only that hotel.

| #  | Send (filter `property:=X`) | Expected | Result |
|----|------|----------|--------|
| G1 | "dining options" scoped to `address_downtown` | Only Address Downtown |  |
| G2 | "spa and wellness" scoped to `address_beach_resort` | Only Address Beach Resort (Level 75) |  |
| G3 | "rooms and suites" scoped to `address_beach_resort_fujairah` | Only Fujairah resort |  |

## H. Known content gaps (agent correctly declines — pending client)

These aren't on the website, so the agent says "I don't have that information" (correct — no invention). Add as facts if the client provides them:
- Parking · Airport transfer · Pet policy

---

## Smoke checklist (pre-demo)

1. `address_knowledge` live (`python -X utf8 main.py` prints the property/language breakdown; expect ~430 chunks, 10 properties, EN + AR).
2. Automated grader green: `python -X utf8 test/run_tests.py --answers` — FAQ/Inference answered, out-of-scope declined, in both languages.
3. `address-gpt` responding (created via `scripts/update_system_prompt.py`).
4. Spot check: one FAQ, one inference, one out-of-scope through the conversation model in each language — grounded, no invention, declines non-UAE properties, numbers exact.
