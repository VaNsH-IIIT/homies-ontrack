# Pitch deck (≤ 10 slides, PDF) and 5-minute demo video: plan

Owner: P1 (assembles); every owner supplies their numbers and screenshots. Judging the build:
technical quality and working demo **30%** (includes the auto-scored benchmark) · business understanding **20%** ·
presentation and storytelling **20%** · innovative ideas **15%** · team work **15%**.

**One sentence to remember:** *AI recommends. Rules constrain. Humans decide. Outcomes improve the next recommendation.*
**One customer threads through the deck and the video** (a real golden_id from the data with 4+ source keys, an open case and a hardship signal; P1 picks it once L4 is merged).

`[TBD-P2]` / `[TBD-P3]` = number to fill from that owner's evaluation.

## Slides

| # | Title (the claim) | Content | Criterion |
|---|---|---|---|
| 1 | **OnTrack: the next best action for every collections case, with a person in charge** | Tagline · team and roles (P1 data, P2 Ask + text AI, P3 decisioning) · Maple Bank synthetic data, 1M customers | Presentation |
| 2 | **A customer's story is split across 5 systems, so hardship is spotted late** | 5 customer keys, messy formats (3 card name formats, 4 DOB formats, masked phones) · what it costs: wrong treatment, wasted contacts | Business |
| 3 | **Architecture: four layers on one governed base** | `docs/architecture/architecture.png` · AI and HUMAN markers · batch vs real time | Technical, presentation |
| 4 | **Layer 1: one trusted record per customer** | 31/31 tables loaded · 19 data issue types found and handled · 1,015,637 golden ids for 1,000,000 people · **Splink precision 99.8%, recall 99.4%** on 5,000 known links · conflict guard: 0 wrong merges · 1,924 uncertain matches go to a **data steward** (Match review page; decisions feed the next build) · contract 8/8 rules pass | Technical |
| 5 | **Layer 2: ask in plain English, see the SQL, get refused when it's off-limits** | Screenshot: question → understood-as tokens → answer + SQL · benchmark: **dev 21/21** (data 12/12, documents 4/4, transcripts 2/2, refusals 3/3, 0 false refusals) · red-team **26/26** refused, 0/14 false refusals · SQL guard blocks 10/10 · refusal example (protected attribute) | Technical (benchmark) |
| 6 | **Layer 3: conversations become features, with evidence** | Structured + text features from one definition (training = live) · hardship signal on the 500 labelled notes: **precision 0.97, recall 0.97, F1 0.97** (5-fold CV; design target recall ≥ 90%) · calls: Claude recall **1.00** (precision 0.98, 80 labels), trained model recall 0.99 (500 labels, CV) · all 292K notes + 15,003 open-case calls scored in under 6 min, no LLM needed → 37,761 open cases with text hardship in the last 90 days, **8,883 of them not in the case hardship flag** · evidence quote example ("only getting 3 days a week now") | Innovation, technical |
| 7 | **Layer 4: rules first, models second, a person decides** | Policy gate (39 tests) → models (self-cure AUC 0.83 vs the bank's 0.72) → ranking within allowed actions → plain-English reasons · agent card screenshot with accept/edit/reject | Technical, business |
| 8 | **Business value: fewer roll-forwards, fewer wasted contacts** | Back-test vs the bank's current rules engine (`model_scores`, same 29,680 cases): leave-alone 20% cured 53% vs 45%, act-now 20% not cured 99.5% vs 92%; hardship cases: the bank recommended collection contact for 71% (calls 45%), a hardship plan for 9% · "do nothing" for likely self-cures · value per 10,000 cases (method from our design) | Business |
| 9 | **Fair and governed by design** | No protected attributes anywhere (contract Q7, feature guard) · fairness check across groups (automated decisions within 5.5 points; self-cure AUC 0.800–0.849 in every group) · hardship → human-only queue · every decision logged with reason | Business, innovation |
| 10 | **What we built in 36 hours, and what comes next** | Team split and commit history (P1/P2/P3 branches and PRs) · what changed from the design and why · next: streaming, uplift models, champion/challenger | Team work |

## 5-minute demo video (show the system running on real data)

| Time | Show | Say |
|---|---|---|
| 0:00–0:30 | Home page: headline numbers, contract 8/8, DQ issues | "Five systems, one customer view, checked on every build." |
| 0:30–1:15 | C360 page: the demo customer; 4+ source keys with match method and confidence; accounts, cases, timeline | "Card, loan, deposit and bureau records resolved to one person, with 99.8% precision." |
| 1:15–2:15 | Ask page: 2 benchmark questions with SQL shown; 1 refused question (protected attribute) | "Every answer shows its SQL; off-limits questions are refused, with a reason." |
| 2:15–3:30 | Agent card for the demo customer: recommendation, 3 plain-English reasons, blocked actions, hardship alert; agent rejects with a reason code → decision log | "The model recommends, rules block what's not allowed, and the agent decides." |
| 3:30–4:15 | Hardship case routed to the human-only queue; evidence quote from the call | "Hardship raises care, never pressure." |
| 4:15–5:00 | Governance: decision log, fairness numbers, `run_all.py` summary | "One command rebuilds everything; nothing affects a customer without a person." |

## Checklist before recording
- [ ] All PRs merged; `python scripts/run_all.py` all OK on full data
- [ ] Demo customer chosen (P1) and the same id used in deck, video and live review
- [x] Numbers filled: benchmark (P2), hardship F1 on notes (P2)
- [x] Numbers filled: transcript hardship recall (P2)
- [ ] Numbers filled: model AUC + back-test + fairness (P3, after #3)
- Deck draft (10 slides, private artifact; Vansh can share it): https://claude.ai/artifact/H2Qq7azNj1pYuaKt3pjUUR
- [ ] Screen recording at 1080p, ≤ 5:00, uploaded unlisted (YouTube or Drive)
