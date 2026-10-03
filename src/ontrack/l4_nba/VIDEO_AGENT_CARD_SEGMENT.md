# Video segment: Agent card and human queue (P3, 2:15-4:15)

For `docs/pitch/video_script.md` (P1 owns it; these replace the two `[TBD-P3]` lines). Numbers are from the
full data, snapshot 2026-09-28, after the fixes for #3 / #5 / #7. Search by **case id** `CS-2026-583749`:
golden ids can differ between builds (G-0331645 on P1's, G-0331648 on a fresh build).

## 2:15-3:30 · Agent card (`streamlit run src/ontrack/app/main.py` -> Agent card)

| Time | On screen | Voice-over |
|---|---|---|
| 2:15 | Agent card opens on `CS-2026-583749`; metrics row (96,000 open cases, 59,939 human-only, 5,037 calls = capacity) | "Every open case gets a next best action. The policy gate removes anything the rules don't allow, the model ranks what's left, and the agent sees why." |
| 2:30 | Red hardship banner and the quote *"I can't pay the whole thing. My pay got cut in Aug."* (from transcript 4510675) | "This customer told us on a call that their pay was cut. The case is flagged, the salary deposits stopped, and they said it in their own words, so OnTrack routes them to a hardship specialist, not to pressure." |
| 2:45 | Recommendation 🤝 Hardship referral; three reasons; counterfactual line | "Three reasons in plain English, with the numbers, and what would change the recommendation." |
| 2:55 | Open "Blocked actions": each with its rule (hardship: no calls or texts; no push consent) | "Blocked actions show the rule behind each one. No model can override a rule." |
| 3:05 | Clear the search, filter Action = call: top case by dollars at risk; show its reason | "For customers who aren't in hardship, payment links by text or email bring a payment within a week 12% of the time, calls only 3%, at 240 times the cost. So OnTrack goes digital first and saves the 5,037 daily call slots for the cases with the most at stake where nothing else has worked." |
| 3:15 | Back to the demo case: choose **edit** -> `specialist_agent`, reason `customer_hardship`, submit; history row appears | "The agent decides. Editing or rejecting needs a reason code, and every decision is logged for audit and for retraining." |

## 3:30-4:15 · Human queue and evaluation (`src/ontrack/l4_nba/EVALUATION.md`)

| Time | On screen | Voice-over |
|---|---|---|
| 3:30 | EVALUATION section 4: queue split | "62% of the open book goes to a person first: 46,226 hardship cases, of which 8,874 were found only in notes and calls and 2,480 only in salary deposits, plus vulnerability, disputes, complaints and legal holds." |
| 3:45 | EVALUATION section 2: back-test table | "We tested like with like: the same cases on 1 July, outcomes after that date. Our self-cure model scores 0.83 AUC against 0.72 for the bank's current model, and of the cases it says need action now, 99.6% really did not pay on their own." |
| 4:00 | EVALUATION section 5: fairness summary | "Fairness is tested offline across gender, age, citizenship, newcomer and accessibility groups: protected attributes are never inputs, and for the cases the model decides alone the gaps stay within a few points." |
