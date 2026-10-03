# P2 (Garv) · status and requests to the team

Live file: P2 updates it on branch **`p2/report`** whenever something changes. P2 checks `origin` every few minutes
for your pushes and replies here. Reply by pushing to your own branch, commenting on the PR, or editing TASKS.md.

_Last updated: 3 Oct 2026, 16:45 IST, **by P1 (Vansh)**, who covers P2 from 16:30 to 19:50 while Garv's Claude limit resets._

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

## 🔜 For Garv after 19:50

1. Finish the transcripts: `python -m ontrack.l3_features.text.extract --workers 6` (on your machine; the cache is per machine).
2. `python -m ontrack.l3_features.text.evaluate` (80 labelled transcripts): post the transcript hardship recall (design target ≥ 90%). P1 fills it into the deck.
3. Fix anything the end-to-end test finds (P1 will open issues for you).
4. Your 1-minute video segment for the Ask page: 2 benchmark questions with SQL, 1 refusal. The script is in `docs/pitch/deck_outline.md`.

## Notes for the team

- `python -m ontrack.l1_factory.build` rewrites `docs/data_quality_report.md`; P2 never commits it.
- Ask reads `bronze.*` for the benchmark (the gold reference SQL is on raw tables) and `gold.*` for C360 questions.
