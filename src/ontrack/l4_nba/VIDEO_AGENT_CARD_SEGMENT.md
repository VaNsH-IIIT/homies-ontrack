# Video segment: Agent card and human queue (P3, 2:15-4:15)

For `docs/pitch/video_script.md` (P1 owns it; these replace the two `[TBD-P3]` lines). Numbers are from the
full data, snapshot 2026-09-28, after the fixes for #3 / #5 / #7. Search by **case id** `CS-2026-583749`.
Every claim below is checked against the build with stable golden_ids (commit 1fd561b): see "Fact check" at the end.

## One-take recording card (K14) · for Kris at 16:00

Checked in a real browser (Edge, headless, 1920×1080 at 110% zoom) on the full data: every step below renders,
with the measured time from click to finished screen. Total target **≤ 2:00**.

**Before you press record (about 5 minutes)**
1. `cd C:\dev\homies-ontrack` → `git checkout main` → `git pull`
2. `.venv\Scripts\python -m ontrack.l4_nba.run --score-only` (about 60 s; the card then matches `main`)
3. Old test decisions show up in the history table: if you see any, close the app and delete
   `D:\ontrack_work\decisions.duckdb` (local file, recreated empty)
4. `.venv\Scripts\streamlit run src/ontrack/app/main.py --client.toolbarMode viewer` (hides the "Deploy" button; same flag as the rest of the video)
5. Browser: open `http://localhost:8501/Agent_Card`, press **F11** (full screen, 1920×1080), zoom **110%** (Ctrl + `+`),
   wait until the case card is shown. Second tab: `EVALUATION.md` on GitHub (sections 2, 2b and 5)
6. Windows: notifications off (Do not disturb), close other apps; record with **Win+Alt+R** (mic: **Win+Alt+M**)

**The take**

| Time | Do exactly this | You should see | Render |
|---|---|---|---|
| 2:15 | Start on the loaded page, don't scroll yet | Metrics row: 96,000 · 59,9xx human-only (62%) · 46,2xx · 5,037 calls (= daily capacity); case **CS-2026-583749** | already loaded (1.2 s) |
| 2:30 | Scroll down slowly to the red banner | "Hardship: human decision required. Case flagged for hardship (reduced income); the customer described it in their own words (below)" and the quote *"I can't pay the whole thing. My pay got cut in Aug."* — transcript:4510675 | instant |
| 2:45 | Keep scrolling a little | **Hardship referral** · Channel: human queue · When: within 1 business day; 3 reasons; "↪ Automated contact resumes only after a person has reviewed the hardship…" | instant |
| 2:55 | Click **"Blocked actions (3) and the rule behind each"** | call and sms: "Hardship/vulnerability flagged — must route to specialist"; push_notification: "No consent push from customer" | 0.9 s |
| 3:05 | Scroll up, click the search box, select all, delete, press **Enter**; then **Action** dropdown → **call** | Queue table, highest dollars at risk first: **CS-2026-759035 · $11,581**; scroll down to its card: "Call: 96% chance the $12,030 stays unpaid without action; contact in the last 30 days brought no payment…" | 0.7 s + 0.8 s |
| 3:15 | Type **CS-2026-583749** in the search box, **Enter**; scroll to **Your decision**: click **edit**, *Action to take* → **specialist_agent**, *Reason code* → **customer_hardship**, click **Submit decision** | Green "Logged EDIT → specialist_agent", and the decision history table below | 1.3 s |
| 3:30 | Scroll to the top, click **"Queue overview for supervisors"** | Right-hand table: hardship_case_flag ~34,9xx · hardship_text ~8,9xx · hardship_income ~2,4xx, plus vulnerability, dispute, holds… (left: the action mix) | 0.9 s |
| 3:45 | Switch to the GitHub tab: EVALUATION **section 2**, then **2b** | §2 `cure_30d` row: AUC 0.717 vs 0.830; act-now 0.996 · §2b: "+$156,548" expected payments per round | — |
| 4:00 | Scroll to **section 5** | "Largest gap between groups" table: automated-case gaps of a few points | — |

*Exact counts on your screen can differ by a few cases from the deck (your build vs P1's); the voice-over uses
rounded numbers that hold on both.* If a click lands wrong, keep talking and redo the step: Vansh cuts the best take.

## 2:15-3:30 · Agent card (`streamlit run src/ontrack/app/main.py` -> Agent card)

| Time | On screen | Voice-over |
|---|---|---|
| 2:15 | Agent card opens on `CS-2026-583749`; metrics row (96,000 open cases, about 60,000 human-only, 5,037 calls = capacity) | "Every open case gets a next best action. The policy gate removes anything the rules don't allow, the model ranks what's left, and the agent sees why." |
| 2:30 | Red hardship banner and the quote *"I can't pay the whole thing. My pay got cut in Aug."* (from transcript 4510675) | "This customer told us on a call that their pay was cut. The bank had already flagged the case for reduced income, and the customer said it in their own words, so OnTrack routes them to a hardship specialist, not to pressure." |
| 2:45 | Recommendation 🤝 Hardship referral; three reasons; counterfactual line | "Three reasons in plain English, with the numbers, and what would change the recommendation." |
| 2:55 | Open "Blocked actions": each with its rule (hardship: no calls or texts; no push consent) | "Blocked actions show the rule behind each one. No model can override a rule." |
| 3:05 | Clear the search, filter Action = call: top case by dollars at risk; show its reason | "For customers who aren't in hardship, payment links by text or email bring a payment within a week 12% of the time, calls only 3%, and a call costs 240 times a text. So OnTrack goes digital first and saves the 5,037 daily call slots for the cases with the most at stake where nothing else has worked." |
| 3:15 | Back to the demo case: choose **edit** -> `specialist_agent`, reason `customer_hardship`, submit; history row appears | "The agent decides. Editing or rejecting needs a reason code, and every decision is logged for audit and for retraining." |

## 3:30-4:15 · Human queue and evaluation (`src/ontrack/l4_nba/EVALUATION.md`)

| Time | On screen | Voice-over |
|---|---|---|
| 3:30 | Agent card → open "Queue overview for supervisors" (same numbers as EVALUATION section 4) | "62% of the open book goes to a person first: about 46,000 hardship cases, nearly 9,000 of them found only in what customers said in notes and calls, and about 2,500 only in their salary deposits, plus vulnerability, disputes, complaints and legal holds." |
| 3:45 | EVALUATION sections 2 and 2b: back-test table, then the dollar table | "We tested like with like: the same cases on 1 July, outcomes after that date. Our self-cure model scores 0.83 AUC against 0.72 for the bank's current model, and of the cases it says need action now, more than 99% really did not pay on their own. On today's book that is about 160 thousand dollars more in expected payments per round of contacts than the bank's current recommendations, counted conservatively." |
| 4:00 | EVALUATION section 5: fairness summary | "Fairness is tested offline across gender, age, citizenship, newcomer and accessibility groups: protected attributes are never inputs, and for the cases the model decides alone the gaps stay within a few points." |

## Fact check (K2): every claim and where it comes from

Run on the full data, snapshot 2026-09-28, after `python -m ontrack.l4_nba.run` (repeatable: same numbers every run).
Exact counts are from Kris's build; the submission is P1's build (hardship 46,235, text-only 8,883, human-only
59,942), so the voice-over uses rounded numbers ("62%", "about 46,000", "nearly 9,000") that hold on both.

| Claim on screen / in the voice-over | Value | Source (query) |
|---|---|---|
| Open cases | 96,000 | `SELECT count(*) FROM gold.nba_recommendation` |
| Human-only queue, 62% | 59,940 (62.4%) | `SELECT sum(needs_human_review::INT) FROM gold.nba_recommendation` |
| Hardship cases | 46,227 | `... WHERE action = 'hardship_referral'` |
| Found only in notes and calls | 8,875 | `... WHERE routing_category = 'hardship_text'` (no case flag) |
| Found only in salary deposits | 2,480 | `... WHERE routing_category = 'hardship_income'` |
| Calls = daily call capacity | 5,037 | `... WHERE action = 'call'`; capacity: `SELECT sum(capacity_units) FROM bronze.channel_capacity WHERE channel = 'call' AND date = (SELECT max(date) FROM bronze.channel_capacity)` |
| Quote "I can't pay the whole thing. My pay got cut in Aug." | transcript 4510675 | `SELECT source_type, source_id, evidence_quote FROM features.text_signals WHERE case_id = 'CS-2026-583749' AND hardship_signal` |
| "The bank had already flagged the case for reduced income" | `hardship_flag = true`, `hardship_reason = reduced_income` (source: customer form) | `SELECT hardship_flag, hardship_reason, hardship_source FROM gold.case_360 WHERE case_id = 'CS-2026-583749'` |
| ~~"the salary deposits stopped"~~ (removed) | not true: $703.08 credited every month Dec 2025 - Aug 2026, not employer payroll | `bronze.salary_credit_history` for the customer's CRM key |
| Blocked: calls and texts (hardship), push (no consent) | as shown | `blocked_reasons` of the demo case |
| Links bring a payment within a week 12%, calls 3% | SMS 12.1%, email 12.2%, call 2.8% | `ranker.channel_economics()`: payment within 7 days of an outbound contact, last 12 months |
| A call costs 240 times a text | $2.40 vs $0.01 | `bronze.channel_capacity.unit_cost_cad` |
| Self-cure AUC 0.83 vs 0.72 for the bank's model | 0.830 vs 0.717 on the same 29,680 cases | `EVALUATION.md` section 2 (`cure_30d` row) |
| More than 99% of "act now" cases did not pay on their own | 0.996 on P1's build (Kris's build: 0.995) | `EVALUATION.md` section 2 |
| About $160K more expected payments per round of contacts | +$156,548 on P1's build (Kris's build: +$162,275) | `EVALUATION.md` section 2b: median payment $71.68, measured channel rates, automated cases only, blocked bank actions count as nothing |
| Fairness gaps for automated decisions stay within a few points | max 5.4 points on P1's build (digital rate by marital status; gender 4.9 points) | `EVALUATION.md` section 5 |

