# P2 (Garv) · status and requests to the team

Live file: P2 updates it on branch **`p2/report`** whenever something changes. P2 checks `origin` every few minutes
for your pushes and replies here. Reply by pushing to your own branch, commenting on the PR, or editing TASKS.md.

_Last updated: 3 Oct 2026, 19:20 IST, **by P1 (Vansh)**, who covered P2 from 16:30 to 19:50. **From 19:50 P2 is yours again, Garv.**_

## 👋 Garv: what happened while you were away (read first)

| What | Result |
|---|---|
| PR #4 (T1–T4) | ✅ merged to `main` (merge commit) |
| PR #6 (T5–T9), opened by P1 for you | ✅ merged to `main` after testing: dev 21/21 with your `answers.csv`, red-team 26/26 / 0 of 14 false, SQL guard 10/10, Ask page tested (certified answer + SQL; refusal) |
| Text signals, notes (full data) | ✅ `extract --skip-transcripts`: 292,365 notes in 70 s → `features.text_signals`; `features.text_signals_case` 66,865 open cases (37,455 with text hardship in 90 days) |
| `evaluate --transcripts 0` (notes) | hardship precision 0.97 · recall 0.98 · **F1 0.98**; clear-only F1 0.97; delay-reason accuracy 0.84; dispute F1 0.94; evidence overlap 95% |
| Transcripts | P1 is running `extract --max-transcripts 300 --workers 4` on Vansh's Claude CLI (cache in Vansh's `llm_cache`). **The rest is yours after 19:50.** |
| Numbers in the deck plan and the architecture diagram | ✅ 21/21, 26/26, notes F1 0.98 (`docs/pitch/deck_outline.md`). The transcript hardship recall is still `[TBD-P2]`. |

## 🙋 Requests (answered)

| # | To | Request | Answer |
|---|---|---|---|
| R1 | P1 | `promises_to_pay` for Layer 2 | ✅ **Approved:** Ask may read it read-only for aggregate answers (PII blocked); not a feature, model or decision input. Logged in README "What changed". Keep the current default. |
| R2 | P1 | Merge P2 PRs in order | ✅ #4 then #6, both merged |
| R3 | P1 | LLM access for the final benchmark run | ✅ **P1 runs it** at 19:00 on 4 Oct from Vansh's laptop (Claude Code CLI logged in), following your runbook in `BENCHMARK_NOTES.md`. Please be online then in case it breaks. |
| R4 | P3 | `text_signals` interface | P1 answered for you in #5: Kris should join `features.text_signals_case` on `case_id`. P1 also flagged two small bugs in his `hardship.py` (disputes missed; one query per case). |
| R5 | P3 | Ping when `gold.nba_recommendation` is on main | ⏳ waiting on Kris (#3 leakage first) |

## 🔜 For Garv after 19:50 (in this order)

1. **Transcript coverage: real gap, coding task.** Only **300 of 15,003** open-case transcripts have signals (2%). The LLM path does about 13 per minute with 4 workers, so all of them would take about 19 hours and far more than our limits. Proposal (your call on the method):
   - a **cheap model for every transcript**, trained on `labels/call_transcripts_labels_public_500.csv` the way you did for notes (customer turns only, evidence = the matching customer turn, `model` column says which model);
   - **Claude only for the top slice**: most recent N, or cases where the cheap model is unsure, or high balance. The cache keeps reruns free.
   - Target: `features.text_signals` covers **all** open-case transcripts in a few minutes; `run_all.py --transcripts 0` should still work with no LLM.
2. **Calls hardship number for the deck:** `python -m ontrack.l3_features.text.evaluate` → transcript hardship precision/recall (design target recall ≥ 90%), for both the cheap model and Claude. Post it here.
3. **A few tests for Ask** in `tests/test_l2_*.py` (pytest is now in `requirements.txt`): SQL guard blocks writes, protected and PII columns; scope guard refuses the red-team set and doesn't refuse policy questions (BQ-020 style); runner writes one row per question even when one fails.
4. **Your 1-minute Ask segment for the video:** 2 benchmark questions with SQL, 1 refusal, 1 document answer with citations. Script outline: `docs/pitch/deck_outline.md`.
5. Kris's PR will change `gold.nba_recommendation`. Once it's merged, check that "which open cases are most likely to roll forward" (R5) works in Ask.

P1's end-to-end run at 16:58 on your merged code: benchmark through Vansh's Claude CLI, **35 answers in 86 s, 0 errors, dev 21/21**. The 19:00 path tomorrow works.

## Notes for the team

- `python -m ontrack.l1_factory.build` rewrites `docs/data_quality_report.md`; P2 never commits it.
- Ask reads `bronze.*` for the benchmark (the gold reference SQL is on raw tables) and `gold.*` for C360 questions.
