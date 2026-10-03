# Task board

Owned by **P1 (Vansh)**. Do only the tasks with your ID, only inside your folders (see the ownership table in [README](README.md#team-and-ownership)).
Status: `[ ]` to do · `[~]` in progress · `[x]` merged to `main`. Update your own rows in your PR.

**Tasks say what must work, not how.** The "Done when" column and the interfaces in the README are fixed; the approach inside your folders is yours: choose libraries, prompts, features and models, and experiment. Fixed regardless: the table names and columns in the interfaces, the hackathon rules (no protected attributes, a plain-English reason for every decision, human review, hardship flagged), and the design as the base (log any change and why).

## Phase 1: now → **14:00 IST, 3 Oct** (first end-to-end test)

Goal: every layer runs at a basic level on real data, so we can test end to end at 14:00 and then improve.
Until P1's `gold.*` tables land (~13:30), P2 and P3 build on the `bronze.*` views (available ~11:00; until then read the raw files with DuckDB directly).

### P1 · Vansh · Layer 1 (Data Product Factory) + integration

| ID | By | Task | Done when |
|---|---|---|---|
| ✅ P1-T1 | 11:00 | `src/ontrack/db.py` (`connect()` to `$ONTRACK_WORK_DIR/ontrack.duckdb`) and `python -m ontrack.l1_factory.bronze`: one `bronze.<table>` view per dataset table, following the release README conventions (NA codes, nulls, IDs as strings to keep leading zeros). **Push to `main` at once: it unblocks P2 and P3.** | `SELECT count(*)` works on every bronze view; row counts printed |
| P1-T2 | 11:30 | `scripts/make_sample.py`: a consistent 5% customer sample across all tables, for teammates with weak laptops (shared by Drive link, never git) | sample builds and the bronze views run on it |
| ✅ P1-T3 | 12:30 | Silver: standardise names, `*_dob_raw` → ISO dates, phones → E.164, postal → A1A 1A1; latest `snapshot_date` per account; current CRM rows only; `channel`/`channel_v2` drift; count every issue found as you go | silver tables built; issue counts recorded |
| ✅ P1-T4 | 13:30 | Identity resolution v1 (tier-1 bridges): `national_id_hash`, `duplicate_of_crm_id`, `collections_cases.account_ids`, `loan_accounts.pad_source_account` → `gold.customer_xref` with `match_confidence`; then **gold v0** of every `gold.*` table in the README interfaces | `python -m ontrack.l1_factory.build` creates all gold tables with the interface columns |
| ✅ P1-T5 | 14:00 | Data quality checks v1 → generated `docs/data_quality_report.md`: issue, records affected, how handled | report generated from code, not typed by hand |

### P2 · Garv · Layer 2 (Insight and NLP) + benchmark

The benchmark is **scored automatically** and counts towards the 30% technical score. Extra questions arrive at **19:00 on 4 Oct**, so the runner must answer a whole question file in **one command**, with no hand edits.

| ID | By | Task | Done when |
|---|---|---|---|
| P2-T1 | 11:00 | Study `data/benchmark_questions.csv`, `labels/benchmark_dev_answers.csv`, `labels/benchmark_answers_template.csv` and the "Benchmark questions" section of the release README. Write `src/ontrack/l2_ask/BENCHMARK_NOTES.md`: how many questions, types, tables each needs, which should be refused, answer format and tolerance. **Tell P1 if any question needs `promises_to_pay`.** | notes committed |
| P2-T2 | 11:45 | `python -m ontrack.l2_ask.run_benchmark --questions <csv> --out benchmark/answers.csv` writes a valid answers file for every question (placeholders allowed at first), plus `python -m ontrack.l2_ask.score_dev`, which scores against the dev answers | valid CSV in the template format; dev score printed |
| P2-T3 | 13:00 | Certified metrics from `metric_definitions` (templated SQL); NL-to-SQL with Claude for the rest; sqlglot validator (SELECT only, allow-listed tables and columns, `PROTECTED_COLUMNS` blocked, minimum group size 10, row cap); up to two repair tries. Runs on bronze now, gold later | dev questions answered with the SQL saved in `sql_or_sources` |
| P2-T4 | 13:30 | Refusal guard before SQL (protected attributes, PII lists, prohibited uses, non-collections questions) and after SQL (validator) | refusal accuracy on dev `should_refuse` questions printed |
| P2-T5 | 14:00 | Dev scoreboard in your PR: answer accuracy and refusal accuracy, plus the 3 worst failure types | numbers in the PR description |

### P3 · Kris · Layer 3 structured features + Layer 4 (NBA)

| ID | By | Task | Done when |
|---|---|---|---|
| P3-T1 | 11:00 | Study the release README, the dictionary for `collections_cases`, `contact_history`, `customers` (consent and hold flags), `hardship_programs` and the policy docs. Write `src/ontrack/l4_nba/DESIGN_NOTES.md`: action set, labels (self-cure in 30 days from `cure_flag`/`days_to_cure`; payment within 7 days of a contact; roll-forward from `dpd_at_day_30`), time-based train/validate/test split | notes committed |
| P3-T2 | 12:00 | `src/ontrack/l4_nba/policy_gate.py`: for each open case, the allowed actions and the blocked actions, each with a plain-English rule reason (consent per channel, cease, do-not-call, insolvency/deceased/third-party holds, dispute, contact cap, permitted hours, stat holidays, hardship eligibility) | unit tests cover each rule; runs on all open cases |
| P3-T3 | 13:00 | `src/ontrack/l3_features/structured/`: **one** function `build_case_features(con, as_of_date)` for both training and live scoring, point-in-time correct; writes `features.case_features`; outcome columns and `PROTECTED_COLUMNS` blocked | features built for a past date (training) and the snapshot date (scoring) with the same code |
| P3-T4 | 13:45 | Models v0 (LightGBM): self-cure and payment-within-7-days (or roll-forward), time split; compare with the existing `model_scores` and `nba_recommendation_last` | metrics printed (AUC, calibration) |
| P3-T5 | 14:00 | Ranker + explanations v0 → `gold.nba_recommendation` for open cases, with `reason_1..3` in plain English and `blocked_actions`; `l4.decision_log` table + `record_decision()` for accept/edit/reject | recommendations for all open cases; a sample of 5 printed with reasons |

## 14:00 → 15:00 · First end-to-end test (P1 runs it on the full data)

1. `l1_factory.build` → gold tables exist with interface columns.
2. `l2_ask.run_benchmark` on the dev split → dev score.
3. `l4_nba.run` → recommendations with reasons for open cases.
4. Each owner fixes what broke in their own part. P1 updates this board with phase 2.

## Phase 2: after 15:00 (to be confirmed at the checkpoint)

| Owner | Planned |
|---|---|
| P1 | Splink probabilistic matching + held-out precision/recall; data contract YAML from DC-COLL-001; architecture diagram (PNG/PDF); data quality report final; Streamlit shell; README "how to run" |
| P2 | Text signals (`hardship_signal`, `stated_delay_reason`, `stated_payday`, `dispute_mentioned`) scored on the 500 public labels → `features.text_signals`; cited search (RAG) over notes and policies; Ask page in the app |
| P3 | SHAP reasons, hardship routing to the human-only queue, agent card page with accept/edit/reject, fairness and proxy check, offline evaluation vs baselines |
| All | Demo video (≤ 5 min), pitch deck (≤ 10 slides), final benchmark run at 19:00 on 4 Oct |

## Milestones

| By (IST) | Milestone |
|---|---|
| 3 Oct, 11:00 | Bronze views on `main`; everyone has data loaded |
| **3 Oct, 14:00** | **Phase 1 done; first end-to-end test** |
| 3 Oct, 22:00 | Phase 2 core working on full data |
| 4 Oct, 12:00 | Benchmark runner stable in one command; demo app runs end to end |
| 4 Oct, 17:00 | Deliverables drafted: contract, DQ report, architecture, README, deck |
| 4 Oct, 19:00 | Extra benchmark questions released: run, check, commit |
| 4 Oct, 20:30 | Final commit; video and deck links submitted (30 min buffer) |
