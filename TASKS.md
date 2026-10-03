# Task board

Owned by **P1 (Vansh)**. Do only the tasks with your ID, only inside your folders (see the ownership table in [README](README.md#team-and-ownership)).
Status: `[ ]` to do · `[~]` in progress · `[x]` merged to `main`. Update your own rows in your PR.

**Tasks say what must work, not how.** The "Done when" column and the interfaces in the README are fixed; the approach inside your folders is yours: choose libraries, prompts, features and models, and experiment. Fixed regardless: the table names and columns in the interfaces, the hackathon rules (no protected attributes, a plain-English reason for every decision, human review, hardship flagged), and the design as the base (log any change and why).

## 📌 Final plan from P1 — read this first (updated 3 Oct, 21:50 IST)

**State:** everyone's work is merged into `main` (PRs #4, #6, #8, #10, #11, #12), verified by P1 on full data: 192 tests pass, benchmark dev 21/21, unseen rehearsal 21/21, all 5 app pages load. **No open issues.** Deck, README ("What changed": 24 rows) and video script have every number filled in.
**Deadline: 4 Oct, 21:00 IST** (commits after it don't count). Extra benchmark questions: **4 Oct, 19:00 IST**.

| Who | Task | When |
|---|---|---|
| **P1 Vansh** | Full `run_all` on `main` with the new stable `golden_id`s (running now) → restart the app → **demo run #2** (full click-through, `docs/pitch/video_script.md`) | 3 Oct, ~22:15 |
| **P2 Garv** | **Wire R5** now: Kris's merge added `gold.nba_recommendation.p_roll_forward`, so "which open cases are most likely to roll forward" can go live in Ask. Test after P1's run finishes (~22:15) | 3 Oct night |
| **P2 Garv** | Fix the broken French accent in one call quote (`"…depuis ao�t"`, case `CS-2026-899195`; raw notes are fine, so probably transcript reading/encoding). Found by Kris | 3 Oct night |
| **P3 Kris** | Small PR: drop the "golden_id differs between builds" note in `evaluation.py` (ids are stable now, commit `1fd561b`) and re-run `python -m ontrack.l4_nba.evaluation` on the new build | 3 Oct night |
| **P3 Kris** | Confirm or fix one voice-over line in `VIDEO_AGENT_CARD_SEGMENT.md`: "the salary deposits stopped" for `CS-2026-583749`. The card's reasons show reduced income, not salary | 3 Oct night |
| **P2 Garv** | Record the Ask segment (1:15–2:15) at 1080p: `python -m ontrack.l2_ask.warm_demo` first. Send the file (Drive link) to P1 | 4 Oct, by 14:00 |
| **P3 Kris** | Record the Agent card + evaluation segment (2:15–4:15) at 1080p. Search by `CS-2026-583749`. Send the file to P1 | 4 Oct, by 14:00 |
| **P1 Vansh** | Clear test decisions; record P1 segments (0:00–1:15, 4:15–5:00); stitch the video to ≤ 5:00; deck → PDF; README: video link, final check | 4 Oct, 14:00–18:30 |
| **P1 Vansh** (+ Garv on call) | **19:00: final benchmark** with the extra questions: `run_benchmark` on Vansh's laptop (runbook in `BENCHMARK_NOTES.md`), commit `benchmark/answers.csv` exactly as generated | 4 Oct, 19:00–19:45 |
| **All** | Code freeze 20:00; final `run_all` + submission by **20:30** (30 min buffer before 21:00) | 4 Oct |

### ✨ Polish tasks: make every part work perfectly (3 Oct night → 4 Oct 14:00)

Each one is done only when its "done when" holds on the full data. Post the result in issue #13.

| ID | Who | Task | Done when |
|---|---|---|---|
| G1 | **Garv** | **Answer stability:** run the benchmark 3× with a fresh LLM cache each time and diff the answers (BQ-014 showed answers can flip) | All data answers identical across the 3 runs; document / call answers keep the same facts and citations; any flip is fixed like BQ-014 |
| G2 | **Garv** | **Dry run of the 19:00 run:** a mock extra-questions file in the exact `benchmark_questions.csv` format (new ids, blank `metric_id`), run the way Vansh will run it (Claude Code CLI, `--workers 4`) | 0 errors, under 10 min for 35 + 15 questions, fallback written into the runbook (fewer workers, retry only failed ids) |
| G3 | **Garv** | **Ask page hardening:** try an empty question, "DROP TABLE cases", a 2,000-character question, French, emoji | No traceback ever; a clear message for each; the 5 example buttons answer in < 3 s after `warm_demo` |
| G4 | **Garv** | Record the Ask segment (1:15–2:15) and send it to Vansh | Every number on screen matches `VIDEO_ASK_SEGMENT.md`; 1080p, ≤ 60 s |
| K1 | **Kris** | **Repeatable training:** fixed seeds plus LightGBM `deterministic=True` and fixed `num_threads`, so a re-run gives the same numbers; then drop the golden_id note and regenerate `EVALUATION.md` on the new build (stable ids) | Two runs of `l4_nba.run` give identical AUCs and identical recommendations for all 96,000 cases |
| K2 | **Kris** | **Check the video facts:** confirm or fix "the salary deposits stopped" for `CS-2026-583749`, and every number in `VIDEO_AGENT_CARD_SEGMENT.md`, against the current build | Every claim traced to a query or table you can show |
| K3 | **Kris** | **Agent card on edge cases:** 5 random cases per action, plus no contacts, no bureau pull, French-speaking, cease, insolvency, deceased, dispute-only | All render with 3 reasons and no error; the page loads in < 3 s; accept / edit / reject each logged |
| K4 | **Kris** | Record the Agent card + evaluation segment (2:15–4:15) and send it to Vansh | Matches the checked script; 1080p, ≤ 2:00 |
| V1 | **Vansh (P1)** | Finish the full run with stable ids; add the accent issue to the DQ report as a coded check (19 issue types); update 18 → 19 in the deck, diagram and script | `run_all` all OK; DQ report regenerated, not hand-edited |
| V2 | **Vansh (P1)** | Test PR #14 (R5 + accent repair) on full data and merge it | R5 answers with SQL; demo quote reads "depuis août"; all tests pass |
| V3 | **Vansh (P1)** | Demo run #2, full click-through; time every page | Every page loads in < 3 s; nothing on screen contradicts the deck |
| V4 | **Vansh (P1)** | README "Submission" section at the top: links to every deliverable (architecture PDF/PNG, data contract, DQ report, `answers.csv`, deck PDF, video), plus a 3-command quick start for judges | Each link opens; a judge can run the system from the quick start alone |
| V5 | **Vansh (P1)** | Clear test decisions; record P1 segments; stitch the video (≤ 5:00); deck → PDF | Video uploaded unlisted, linked in the README |


Rules unchanged: stay in your folders, PRs to `main`, never commit data / `.duckdb` / `.env`, no hand edits to `answers.csv`.

To see issues assigned to you: `gh issue list --assignee @me --repo VaNsH-IIIT/homies-ontrack`

## Phase 1 → **16:30 IST, 3 Oct** for P2 and P3 (first end-to-end test 16:30–17:30)

Goal: every layer runs at a basic level on real data, then we improve.
**P1's Layer 1 is done and on `main`:** run `python -m ontrack.l1_factory.bronze` once (~10 min) and `python -m ontrack.l1_factory.build` (~1 min) to get every `bronze.*` and `gold.*` table in your local DuckDB. Times in the "By" column below were set for a 9:30 start: shift yours by your start time, but aim to finish phase 1 by 16:30.
**When your phase-1 tasks are done, continue straight into your phase-2 tasks below; don't wait.**

### P1 · Vansh · Layer 1 (Data Product Factory) + integration

| ID | By | Task | Done when |
|---|---|---|---|
| ✅ P1-T1 | 11:00 | `src/ontrack/db.py` (`connect()` to `$ONTRACK_WORK_DIR/ontrack.duckdb`) and `python -m ontrack.l1_factory.bronze`: one `bronze.<table>` view per dataset table, following the release README conventions (NA codes, nulls, IDs as strings to keep leading zeros). **Push to `main` at once: it unblocks P2 and P3.** | `SELECT count(*)` works on every bronze view; row counts printed |
| ✅ P1-T2 | 11:30 | `scripts/make_sample.py`: a consistent 5% customer sample across all tables, for teammates with weak laptops (shared by Drive link, never git) | sample builds and the bronze views run on it |
| ✅ P1-T3 | 12:30 | Silver: standardise names, `*_dob_raw` → ISO dates, phones → E.164, postal → A1A 1A1; latest `snapshot_date` per account; current CRM rows only; `channel`/`channel_v2` drift; count every issue found as you go | silver tables built; issue counts recorded |
| ✅ P1-T4 | 13:30 | Identity resolution v1 (tier-1 bridges): `national_id_hash`, `duplicate_of_crm_id`, `collections_cases.account_ids`, `loan_accounts.pad_source_account` → `gold.customer_xref` with `match_confidence`; then **gold v0** of every `gold.*` table in the README interfaces | `python -m ontrack.l1_factory.build` creates all gold tables with the interface columns |
| ✅ P1-T5 | 14:00 | Data quality checks v1 → generated `docs/data_quality_report.md`: issue, records affected, how handled | report generated from code, not typed by hand |

### P2 · Garv · Layer 2 (Insight and NLP) + benchmark

The benchmark is **scored automatically** and counts towards the 30% technical score. Extra questions arrive at **19:00 on 4 Oct**, so the runner must answer a whole question file in **one command**, with no hand edits.

| ID | By | Task | Done when |
|---|---|---|---|
| ✅ P2-T1 | 11:00 | Study `data/benchmark_questions.csv`, `labels/benchmark_dev_answers.csv`, `labels/benchmark_answers_template.csv` and the "Benchmark questions" section of the release README. Write `src/ontrack/l2_ask/BENCHMARK_NOTES.md`: how many questions, types, tables each needs, which should be refused, answer format and tolerance. **Tell P1 if any question needs `promises_to_pay`.** | notes committed |
| ✅ P2-T2 | 11:45 | `python -m ontrack.l2_ask.run_benchmark --questions <csv> --out benchmark/answers.csv` writes a valid answers file for every question (placeholders allowed at first), plus `python -m ontrack.l2_ask.score_dev`, which scores against the dev answers | valid CSV in the template format; dev score printed |
| ✅ P2-T3 | 13:00 | Certified metrics from `metric_definitions` (templated SQL); NL-to-SQL with Claude for the rest; sqlglot validator (SELECT only, allow-listed tables and columns, `PROTECTED_COLUMNS` blocked, minimum group size 10, row cap); up to two repair tries. Runs on bronze now, gold later | dev questions answered with the SQL saved in `sql_or_sources` |
| ✅ P2-T4 | 13:30 | Refusal guard before SQL (protected attributes, PII lists, prohibited uses, non-collections questions) and after SQL (validator) | refusal accuracy on dev `should_refuse` questions printed |
| ✅ P2-T5 | 14:00 | Dev scoreboard in your PR: answer accuracy and refusal accuracy, plus the 3 worst failure types | numbers in the PR description |

### P3 · Kris · Layer 3 structured features + Layer 4 (NBA)

| ID | By | Task | Done when |
|---|---|---|---|
| P3-T1 | 11:00 | Study the release README, the dictionary for `collections_cases`, `contact_history`, `customers` (consent and hold flags), `hardship_programs` and the policy docs. Write `src/ontrack/l4_nba/DESIGN_NOTES.md`: action set, labels (self-cure in 30 days from `cure_flag`/`days_to_cure`; payment within 7 days of a contact; roll-forward from `dpd_at_day_30`), time-based train/validate/test split | notes committed |
| P3-T2 | 12:00 | `src/ontrack/l4_nba/policy_gate.py`: for each open case, the allowed actions and the blocked actions, each with a plain-English rule reason (consent per channel, cease, do-not-call, insolvency/deceased/third-party holds, dispute, contact cap, permitted hours, stat holidays, hardship eligibility) | unit tests cover each rule; runs on all open cases |
| P3-T3 | 13:00 | `src/ontrack/l3_features/structured/`: **one** function `build_case_features(con, as_of_date)` for both training and live scoring, point-in-time correct; writes `features.case_features`; outcome columns and `PROTECTED_COLUMNS` blocked | features built for a past date (training) and the snapshot date (scoring) with the same code |
| P3-T4 | 13:45 | Models v0 (LightGBM): self-cure and payment-within-7-days (or roll-forward), time split; compare with the existing `model_scores` and `nba_recommendation_last` | metrics printed (AUC, calibration) |
| P3-T5 | 14:00 | Ranker + explanations v0 → `gold.nba_recommendation` for open cases, with `reason_1..3` in plain English and `blocked_actions`; `l4.decision_log` table + `record_decision()` for accept/edit/reject | recommendations for all open cases; a sample of 5 printed with reasons |

## 16:30 → 17:30 · First end-to-end test (P1 runs it on the full data)

1. `l1_factory.build` → gold tables exist with interface columns.
2. `l2_ask.run_benchmark` on the released questions → dev score.
3. `l4_nba.run` → recommendations with reasons for open cases.
4. Each owner fixes what broke in their own part.

## Phase 2 · after your phase 1 → 22:00 IST, 3 Oct (start each as soon as you finish phase 1)

### P1 · Vansh
| ID | Task | Done when |
|---|---|---|
| ✅ P1-T2 | 5% dev sample (`scripts/make_sample.py`) | sample zip shared by Drive |
| ✅ P1-T6 | Probabilistic matching (Splink) for keys left unlinked by tiers 1–2; precision/recall measured on held-out tier-1 case-to-account links | fewer singletons; precision/recall in the DQ report |
| ✅ P1-T7 | Data contract YAML for `gold.c360_customer`, from `files/docs/data_contracts/` (DC-COLL-001) | `contracts/c360_customer.yaml` with owner, schema, quality rules, allowed uses, refresh |
| ✅ P1-T8 | Streamlit shell `src/ontrack/app/main.py` + page `1_C360.py` (customer lookup: golden record, linked keys with match confidence, accounts, timeline) | `streamlit run src/ontrack/app/main.py` shows pages 1–3 (2 and 3 load when P2/P3 add them) |
| ✅ P1-T9 | Final architecture diagram (PNG/PDF) in `docs/` | file in repo |

### P2 · Garv
| ID | Task | Done when |
|---|---|---|
| ✅ P2-T6 | Text signals with Claude: `hardship_signal`, `stated_delay_reason`, `stated_payday`, `dispute_mentioned`, each with a confidence and the exact evidence quote (+ `turn_index`). Score on `labels/agent_notes_labels_public_500.csv` and `labels/call_transcripts_labels_public_500.csv`; then run on notes/transcripts of open cases (batched, cached) → `features.text_signals` | precision/recall per signal printed; table written with the interface columns |
| ✅ P2-T7 | Cited search (RAG) over `reference_documents` (`files/docs/`) and agent notes, for document-type benchmark questions; answers cite `doc_id` / section or `note_id` | document questions in the dev set answered with citations |
| ✅ P2-T8 | Ask page `src/ontrack/app/pages/2_Ask.py`: question box, editable "understood as" tokens, answer table, **SQL shown**, clear refusal message | page works in the app |
| ✅ P2-T9 | Benchmark hardening: full released set (dev + test) → `benchmark/answers.csv` in one command; error analysis on dev; ready for the 19:00 extra questions on 4 Oct | answers file for all questions; dev score in PR |

### P3 · Kris
| ID | Task | Done when |
|---|---|---|
| P3-T6 | SHAP-based reasons: top 3 drivers per recommendation mapped to plain-English templates, plus a counterfactual line ("would change if …") | every recommendation has 3 readable reasons |
| P3-T7 | Hardship routing: combine structured signals (payroll delay, EI deposits, payment failures, case `hardship_flag`) with `features.text_signals` from P2 (when available) → `hardship_flag`, `needs_human_review`; hardship / vulnerability / dispute / complaint cases go to a human-only queue | counts of routed cases printed; routing reason stored |
| P3-T8 | Agent card page `src/ontrack/app/pages/3_Agent_Card.py`: pick a case → recommendation, reasons, blocked actions, hardship alert; accept / edit / reject with reason → `l4.decision_log` | an override recorded from the UI |
| P3-T9 | Evaluation for the deck: back-test vs `nba_recommendation_last` and `model_scores`; fairness check offline (recommended-action rates by protected group, used only to test) | numbers in `src/ontrack/l4_nba/EVALUATION.md` |

## Phase 3 · 4 Oct (planned at the 17:30 review)

| Owner | Planned |
|---|---|
| All | Polish, bug fixes on full data, README "how to run", deck (≤ 10 slides), 5-minute demo video, final benchmark run at 19:00 |

## Milestones

| By (IST) | Milestone |
|---|---|
| ✅ 3 Oct, 11:15 | Layer 1 (bronze → gold, DQ report, dev sample) on `main` |
| **3 Oct, 16:30** | **P2/P3 phase 1 done; first end-to-end test** |
| 3 Oct, 22:00 | Phase 2 core working on full data |
| 4 Oct, 12:00 | Benchmark runner stable in one command; demo app runs end to end |
| 4 Oct, 17:00 | Deliverables drafted: contract, DQ report, architecture, README, deck |
| 4 Oct, 19:00 | Extra benchmark questions released: run, check, commit |
| 4 Oct, 20:30 | Final commit; video and deck links submitted (30 min buffer) |
