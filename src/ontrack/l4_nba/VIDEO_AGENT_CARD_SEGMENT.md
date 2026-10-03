# Video segment: Agent card and human queue (P3, 2:15-4:15)

For `docs/pitch/video_script.md` (P1 owns it; these replace the two `[TBD-P3]` lines). Numbers are from the
full data, snapshot 2026-09-28, after the fixes for #3 / #5 / #7. Search by **case id** `CS-2026-583749`.
Every claim below is checked against the build with stable golden_ids (commit 1fd561b): see "Fact check" at the end.

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
| 3:30 | EVALUATION section 4: queue split | "62% of the open book goes to a person first: about 46,000 hardship cases, nearly 9,000 of them found only in what customers said in notes and calls, and about 2,500 only in their salary deposits, plus vulnerability, disputes, complaints and legal holds." |
| 3:45 | EVALUATION section 2: back-test table | "We tested like with like: the same cases on 1 July, outcomes after that date. Our self-cure model scores 0.83 AUC against 0.72 for the bank's current model, and of the cases it says need action now, 99.5% really did not pay on their own." |
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
| 99.5% of "act now" cases did not pay on their own | 0.995 | `EVALUATION.md` section 2 |
| Fairness gaps for automated decisions stay within a few points | max 5.5 points (digital rate by marital status; gender 5.1 points, from the small U / X groups) | `EVALUATION.md` section 5 |

