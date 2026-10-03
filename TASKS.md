# Task board

Owned by **P1 (Vansh)**. Do only the tasks with your ID, only inside your folders (see the ownership table in [README](README.md#team-and-ownership)).
Status: `[ ]` to do · `[~]` in progress · `[x]` merged to `main`. Update your own rows in your PR.

**Tasks say what must work, not how.** The "Done when" column and the interfaces in the README are fixed; the approach inside your folders is yours: choose libraries, prompts, features and models, and experiment. Fixed regardless: the table names and columns in the interfaces, the hackathon rules (no protected attributes, a plain-English reason for every decision, human review, hardship flagged), and the design as the base (log any change and why).

## 📌 Review notes from P1 — read these first (updated 17:15 IST)

| For | What |
|---|---|
| **P3 (Kris)** | **Moving to Windows with a new Claude chat? Read "🔁 P3 restart on Windows" right below, all of it, before writing any code.** |
| **P2 (Garv)** | P1 covers P2 until 19:50. Everything is merged (PRs #4, #6); status and your next steps are in `P2_REPORT.md` on `p2/report`. |

## 🔁 P3 restart on Windows (Kris + your new Claude chat): read all of this first

Your new chat has none of your old context. **Paste this whole section into it as your first message.**

### 0. Before you leave Linux
- Run `git status` on the Linux machine. **Commit and push everything to `p3/working`, even unfinished work** (`git commit -am "WIP" && git push`). P1 last saw **`75d99cc` at 16:21** ("WIP: fix EV ranking formula"). Anything not pushed is lost.
- **Do not copy the old DuckDB file or old data folders.** That database was built from an older `main`: no text signals, old gold tables, and training data with the leak (see 3a). Build a fresh one on Windows (step 1).

### 1. Set up on Windows (about 40 min, mostly waiting)
1. Clone to a **short path** (`C:\dev\homies-ontrack`) and install: README → Setup steps 2–3. In `.env`: `MAPLE_DATA_DIR` = the unzipped **full** release (README step 4; not the 5% sample: final numbers must come from full data), `ONTRACK_WORK_DIR=D:/ontrack_work` (any folder outside the repo). An API key is optional: Garv's code falls back to the logged-in Claude Code CLI.
2. Get your branch **and** the latest `main`:
   ```bash
   git fetch origin && git checkout p3/working && git pull
   git merge origin/main            # AI_TOOLS.md conflict: keep both sets of rows
   ```
3. Build everything fresh, in one command (about 25 min on full data):
   ```bash
   python scripts/run_all.py --with-bronze --transcripts 0
   ```
   That runs bronze → Layer 1 build → contract → **text signals from notes (no LLM)** → **your L4** → benchmark. All steps should say OK. Then run `pytest tests/` (55 tests).
4. `streamlit run src/ontrack/app/main.py` → page 3 (Agent card).

### 2. What you already built (all on `p3/working`, runs end to end on full data)
`l3_features/structured/features.py` (point-in-time `build_case_features`), `l4_nba/policy_gate.py` (+ 38 tests), `models.py` (LightGBM self-cure 30d + payment 7d), `ranker.py` (EV ranking + SHAP reasons), `hardship.py` (routing, + tests), `run.py`, `evaluation.py` + `EVALUATION.md`, `DESIGN_NOTES.md`, `app/pages/3_Agent_Card.py`. P1's run at 16:58: L4 took 586 s and wrote **96,000 recommendations**. The code works; the **results are wrong** for the reasons below.

### 3. Fix, in this order (details in the issues)
**a. [#3](https://github.com/VaNsH-IIIT/homies-ontrack/issues/3) Label leakage: blocker.** Current AUCs (self-cure **0.964**, payment-7d **0.997**) are leaks and must **never** go into the deck, README or EVALUATION. Cause: training rows include cases already cured or closed at `as_of`, and the payment label sits before the feature date. Fix:
   - training population at `as_of` = cases **open and unresolved at `as_of`**: `case_open_date <= as_of AND (outcome_date IS NULL OR outcome_date > as_of) AND (cure_date IS NULL OR cure_date > as_of)`
   - labels **strictly after `as_of`**: self-cure = `cure_flag AND as_of < cure_date <= as_of + 30d`; payment-7d = a `payment_taken_flag` contact with `as_of < contact_ts_utc <= as_of + 7d`
   - stack monthly `as_of` dates (2026-01-01 … 2026-05-01) for training, validate on 2026-07-01, with the same `build_case_features(con, as_of)` each time
   - sanity check: retrain without the top SHAP feature; if AUC collapses, something still leaks. **Expect about 0.65–0.85; that is the right result.**

**b. [#7](https://github.com/VaNsH-IIIT/homies-ontrack/issues/7) Recommendation quality (from P1's end-to-end run).**
   - **92% of cases get `hardship_referral`** (88,778 of 96,000), and no call / SMS / email is ever chosen; `channel` is always null. Your own WIP note says it: `hardship_referral` costs $0, so it wins everywhere. **Allow `hardship_referral` only for hardship cases**, then rank the contact actions the gate allows by expected recovery − cost − harm. Target a believable spread (do_nothing for likely self-cures, digital for low risk, calls for high risk) and fill `channel` and `time_window`.
   - **Reasons read like raw features** ("2.0 total contacts on this case"). Write business reasons with whole numbers and why they matter, e.g. *"Likely to pay without a call (self-cure chance 68%): paid within 10 days in 4 of the last 5 cycles"*.
   - **Agent card crashes** on null values (`if row.get("channel")` → *boolean value of NA is ambiguous*). Fix: first line inside the case loop: `row = row.astype(object).where(row.notna(), None)`.
   - **Add a case_id / golden_id search box** to the agent card. Demo case: **`CS-2026-583749` / `G-0331645`** (4 systems, 5 products; said on a call "My pay got cut in Aug.").
   - Human-only queue is 52,299 of 96,000 (54%). This is OK (hardship-first), but put the split by reason (case flag / text / vulnerability / dispute) in `EVALUATION.md`.

**c. [#5](https://github.com/VaNsH-IIIT/homies-ontrack/issues/5) Text signals (Garv's, now on `main`).** In `hardship.py`, join **`features.text_signals_case`** on `case_id` once (columns `text_hardship_90d`, `text_hardship_evidence`, `text_dispute_any`, …) instead of one query per case. Bug: the current query has `WHERE hardship_signal = true`, so **disputes without hardship are missed**. Disputes go to the human queue on their own.

**d. Revert your edits to P1 files.** Commit `1d736ea` changed `README.md`, `TASKS.md`, `docs/data_quality_report.md` and `docs/pitch/deck_outline.md` (that one has the leaky AUCs). After merging `main`: `git checkout origin/main -- README.md TASKS.md docs/` and commit. Put your design changes and numbers in the **PR description**; P1 copies them into the README and deck.

**e. Open ONE PR** from `p3/working` → `main`, with: AUCs after the fix, the back-test vs `nba_recommendation_last` / `model_scores`, the fairness check, the action mix, and the human-queue split. Add your row in `AI_TOOLS.md`. P1 tests and merges it, then reruns the end-to-end demo.

### 4. Rules (unchanged)
Stay in your folders (`l3_features/structured/`, `l4_nba/`, `app/pages/3_*`, `tests/`). Never commit data, `*.duckdb` or `.env`. No protected attributes in features or decisions. `promises_to_pay` is **not** a model feature (only Ask may read it). Merge commits, not squash.

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
| P2-T6 | Text signals with Claude: `hardship_signal`, `stated_delay_reason`, `stated_payday`, `dispute_mentioned`, each with a confidence and the exact evidence quote (+ `turn_index`). Score on `labels/agent_notes_labels_public_500.csv` and `labels/call_transcripts_labels_public_500.csv`; then run on notes/transcripts of open cases (batched, cached) → `features.text_signals` | precision/recall per signal printed; table written with the interface columns |
| P2-T7 | Cited search (RAG) over `reference_documents` (`files/docs/`) and agent notes, for document-type benchmark questions; answers cite `doc_id` / section or `note_id` | document questions in the dev set answered with citations |
| P2-T8 | Ask page `src/ontrack/app/pages/2_Ask.py`: question box, editable "understood as" tokens, answer table, **SQL shown**, clear refusal message | page works in the app |
| P2-T9 | Benchmark hardening: full released set (dev + test) → `benchmark/answers.csv` in one command; error analysis on dev; ready for the 19:00 extra questions on 4 Oct | answers file for all questions; dev score in PR |

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
