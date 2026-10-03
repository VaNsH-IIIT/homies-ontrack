# P2 (Garv) · status and requests to the team

Live file: P2 updates it on branch **`p2/report`** whenever something changes. P2 checks `origin` every few minutes
for your pushes and replies here. Reply by pushing to your own branch, commenting on the PR, or editing TASKS.md.

_Last updated: 3 Oct 2026, 16:45 IST_

## 🙋 Requests (please answer)

| # | To | Request | Why | Status |
|---|---|---|---|---|
| R1 | **P1 Vansh** | **Decide `promises_to_pay` for Layer 2.** Proposal: Ask may read it read-only (aggregates only, PII columns blocked); it stays out of features and decisions. Currently allowed by default; `ONTRACK_ASK_BLOCK_PTP=1` restores the 30-table scope. | 6 benchmark questions need it (BQ-003, 007, 013, 028, 034 data; BQ-033 procedure doc): ~5 points of 35. | ⏳ waiting |
| R2 | **P1 Vansh** | **Merge P2 PRs in order** T1 → T2 → T3 → T4 (stacked branches; each later one contains the earlier). | P1 merges to main. | ⏳ waiting |
| R3 | **P1 Vansh** | **LLM access for the final benchmark run.** Ask uses `ANTHROPIC_API_KEY` if set, otherwise the logged-in **Claude Code CLI** (`claude -p`). Whoever runs `run_benchmark` at 19:00 on 4 Oct needs one of the two. Answers are cached under `$ONTRACK_WORK_DIR/llm_cache`, so a re-run of unchanged questions needs no LLM. | Document, transcript and non-certified data questions use Claude. | ⏳ please confirm who runs it |
| R4 | **P3 Kris** | **Confirm what you read from `features.text_signals`** (P2-T6): interface columns are `source_type, source_id, contact_id, case_id, crm_customer_id, event_ts, hardship_signal, hardship_confidence, evidence_quote, evidence_turn_index, stated_delay_reason, stated_payday, dispute_mentioned, model, prompt_version`. Planned: one row per note / transcript of **open cases**; `hardship_signal` boolean, confidence 0–1. Tell me if you want a per-case roll-up too (e.g. `features.text_signals_case`). | Your hardship routing (P3-T7) joins it. | ⏳ waiting |
| R5 | **P3 Kris** | When `gold.nba_recommendation` is on main, ping here: Ask will answer "which open cases are most likely to roll forward" from it (design, Layer 2 example). | Demo question. | ⏳ waiting |

## ✅ Done (branches pushed)

| Task | Branch | Result |
|---|---|---|
| P2-T1 notes | `p2/P2-T1-benchmark-notes` | `src/ontrack/l2_ask/BENCHMARK_NOTES.md` |
| P2-T2 runner + scorer | `p2/P2-T2-runner` | `python -m ontrack.l2_ask.run_benchmark` writes all 35 rows; `python -m ontrack.l2_ask.score_dev` |
| P2-T3 certified metrics + guarded NL-to-SQL | `p2/P2-T3-nl-to-sql` | certified templates match **all 9** certified dev answers exactly; dev 13/21 without LLM |
| P2-T4 refusals | `p2/P2-T4-refusals` | dev should-refuse 3/3, false refusals 0/18; red-team 26/26 refused, 0/14 false; SQL guard 10/10 blocked |

## 🔜 In progress

P2-T3 LLM path (documents, transcripts, other data) → P2-T5 dev scoreboard → P2-T6 text signals → P2-T7 cited
search → P2-T8 Ask page → P2-T9 benchmark hardening.

## Notes for the team

- `python -m ontrack.l1_factory.build` rewrites `docs/data_quality_report.md`; P2 never commits it.
- Ask reads `bronze.*` for the benchmark (the gold reference SQL is on raw tables) and `gold.*` for C360 questions.
