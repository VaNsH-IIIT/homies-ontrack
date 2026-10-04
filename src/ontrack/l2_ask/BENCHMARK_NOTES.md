# Benchmark notes (P2-T1)

Sources: `data/benchmark_questions.csv` (35 questions), `labels/benchmark_dev_answers.csv` (21 dev gold answers),
`labels/benchmark_answers_template.csv`, release README "Benchmark questions". More questions arrive **19:00 IST, 4 Oct**.

## Counts

| | Count |
|---|---:|
| Questions released | 35 (dev 21 · test 14) |
| Difficulty | easy 14 · medium 16 · hard 5 |
| Have a `metric_id` (certified metric) | 15 |
| Data (SQL) questions | 18 |
| Document / policy questions | 9 |
| Transcript summaries ("most recent recorded call on case …") | 3 |
| Should be refused (our reading) | 5: BQ-018 (off topic), BQ-023 (PII), BQ-024 (proxy), BQ-029, BQ-031 (protected) |

## Answer format (template + dev gold)

Columns: `question_id, answer, sql_or_sources, refused`. One row per question, in question order.

* **Tables** → small CSV with a header, one row per group, ordered by the group key. Gold uses snake_case
  headers with `_pct` for percentages, e.g. `queue,avg_dpd,open_cases`. We emit the same shape, plus a count column.
* **Percentages** are in points (0–100), rounded as the tolerance suggests (`±0.1 pts` → 1–2 decimals).
* **Single numbers** → a one-column CSV (`promise_kept_rate_pct\n35.1`).
* **Document answers** → one or two sentences with the key facts; `sql_or_sources` lists the cited sections as JSON,
  e.g. `["POL-COLL-001 §5.2"]`. Scoring checks **key facts + the cited document**.
* **Transcript answers** → `reason; promise amount and date; next step`; source `["transcript <id>"]`.
* **Refusals** → `refused = true`, answer `Refuse: <reason>` (gold: `Refuse: protected ground`, `Refuse: outside scope`).
* **Tolerances seen:** `exact`, `±0.1 pts`, `±0.5 pts`, `±0.1 days`, `±0.05`, `±0.01 CAD`, `±1 CAD`,
  `exact count, ±1 CAD`, `direction of effect`. Blank for document / refusal questions.

## Per question

R = refuse · D = data (SQL) · Doc = documents · T = transcript. Tables are dataset names (`bronze.<name>` for us).

| ID | Split | Type | Tables / sources | Notes and traps |
|---|---|---|---|---|
| BQ-001 | test | Doc | POL-COLL-001, FAQ, REG-SUM-001 | CASL applies to commercial messages, not collections reminders |
| BQ-002 | dev | Doc | POL-COLL-001 §5.2 | **Trap:** superseded script v1.0 says 5/week; current policy says 3 in any rolling 7 days |
| BQ-003 | dev | D | **promises_to_pay** | broken rate by `least(prior_broken_ptp_count,3)`; denominator = resolved promises |
| BQ-004 | dev | D | collections_cases | open = `outcome IS NULL`; `avg(current_dpd)` by `queue` |
| BQ-005 | dev | Doc | POL-COLL-001 §5.3, FAQ Q2 | National DNCL = telemarketing only |
| BQ-006 | dev | D | contact_history | `dispute_raised_flag`, 15–22 Sep vs 7–14 Sep on `contact_ts_local`; spike after INC-0914. Deterministic since G24 (`dispute_window.py`) |
| BQ-007 | dev | D | **promises_to_pay**, agents | `coalesce(site,'self_serve')`; due 1 Jul–28 Sep |
| BQ-008 | test | D | collections_cases | cure within 30 days of open for July 2026 opens (`cure_flag`, `days_to_cure`) |
| BQ-009 | test | Doc | POL-COLL-004 / POL-COLL-001 | consumer proposal → insolvency hold, stop collection, refer |
| BQ-010 | dev | D | contact_history, collections_cases | `within_permitted_hours_flag`; **coalesce(channel_v2, channel)**; province from the case |
| BQ-011 | dev | D | contact_history | RPC by `contact_hour_local`, Sep 1–27; **channel_v2 drift** |
| BQ-012 | dev | D | card_accounts | snapshot 2026-09-28, status active/blocked, `dpd IS NOT NULL`; not `cycles_delinquent` |
| BQ-013 | test | D | **promises_to_pay** | paid against promises in Sep 2026 (`amount_paid`, payment date) |
| BQ-014 | test | D | collections_cases, agents, case_assignment_history | randomised pilot only (`assignment_method='random'`); answer = direction of effect |
| BQ-015 | test | D | card_accounts, loan_accounts | `chargeoff_date` in 12 months to 28 Sep; count and amount by product |
| BQ-016 | dev | T | call_transcripts (+ JSON), collections_cases | latest transcript for the case → reason, promise, next step |
| BQ-017 | dev | D | account_monthly_snapshot | `month_end_date` in **several formats**; dpd 1–30 at 2026-03-31 → dpd > 30 at 2026-06-30 |
| BQ-018 | dev | R | — | weather: outside scope |
| BQ-019 | dev | Doc | POL-COLL-004 §4.2, qa_checklist item 7 | acknowledge, record, offer an eligible option before asking for payment |
| BQ-020 | test | Doc | POL-COLL-001 / POL-COLL-004 | legal action rules (not a refusal: a policy question) |
| BQ-021 | test | T | call_transcripts | as BQ-016 |
| BQ-022 | dev | T | call_transcripts | as BQ-016 |
| BQ-023 | test | R | — | names + phones export: direct PII |
| BQ-024 | dev | R | — | FSA is a **proxy** for protected grounds and income |
| BQ-025 | test | D | contact_history, collections_cases | outbound attempts per open case by `current_bucket` |
| BQ-026 | dev | Doc | POL-COLL-004 §4.2, HPT-2026 | **Trap:** FAQ says 6 months; current policy v4.2 says 3 months at 50% |
| BQ-027 | test | D | contact_history | `sum(contact_cost_cad)/count(*)` by channel, Sep 2026, exclude system events; channel_v2 |
| BQ-028 | dev | D | **promises_to_pay**, collections_cases | randomised only; kept rate by `test_cell` |
| BQ-029 | test | R | — | citizenship / newcomer: protected |
| BQ-030 | test | Doc | ops_events INC-0923, IR-2026-0923 | dialer outage, capacity down ~60% |
| BQ-031 | dev | R | — | gender, marital status: protected |
| BQ-032 | dev | D | collections_cases | hardship rate by `primary_product`, opened 2026 |
| BQ-033 | test | Doc | PRC-COLL-010 | grace period before a promise is broken |
| BQ-034 | dev | D | **promises_to_pay** | kept / resolved, due in Aug 2026 |
| BQ-035 | dev | D | collections_cases | open by `current_bucket`; ~4% buckets disagree with `current_dpd` (gold keeps the stored bucket) |

## `promises_to_pay` (raised with P1)

Our design scopes `promises_to_pay` out (30 of 31 tables). **Six questions need it:** BQ-003, 007, 013, 028, 034
(data) and BQ-033 (procedure document, no table needed). Without it we lose ~5 of 35 answers.
Proposal: allow it **read-only in Ask only** (aggregates, no PII columns), still out of features and decisions.
It is one switch: `ontrack.l2_ask.sql_guard.BLOCKED_TABLES`. **P1 decides.**

## Recurring traps (built into the prompt and the certified metrics)

1. `contact_history.channel` → `channel_v2` from 26 Sep: always `coalesce(channel_v2, channel)`.
2. Open case = `outcome IS NULL`. "Today" = snapshot **2026-09-28**, never the wall clock.
3. Superseded documents (`superseded_by` set) must not be cited; FAQ is older than the policy where they disagree.
4. Rates exclude open / cancelled promises from the denominator; randomised comparisons use `assignment_method = 'random'`.
5. Mixed date formats in `account_monthly_snapshot.month_end_date`.
6. Protected columns and proxies (FSA, postal area) are refused, not answered with a caveat.
7. **Qualifier vs dataset definition (G24).** "Late-fee disputes raised" = every contact with
   `contact_history.dispute_raised_flag`. The contact data has no subject field, so the qualifier can't narrow it.
   Case `dispute_type` describes a case's open dispute, not when one was raised. A fresh run on 4 Oct read "late-fee"
   literally (`dispute_type = 'late_fee'`: 29 vs 9, not 875 vs 566). BQ-006-style questions now take a deterministic
   route (`dispute_window.py`, no LLM), and the prompt states the rule for other qualifiers ("billing complaints").
8. "Outside permitted calling hours" = `NOT within_permitted_hours_flag` (never recomputed from hours); "in the
   12 months to D" = the day after D minus 12 months through D, inclusive (G24, pins BQ-010 / BQ-015 as answered).

### G24 scan: released questions where a qualifier could be read against the dataset's definition

Routes with the LLM switched off: 20 of the 35 are deterministic (certified, templates, refusals, BQ-006 now). The
15 on the LLM path, with their risk:

| id | wording that could be misread | dataset definition (pinned by) | risk now |
|---|---|---|---|
| BQ-006 | "late-fee disputes raised" | all `dispute_raised_flag` contacts | **none** (deterministic) |
| BQ-010 | "outside permitted calling hours", "customer province" | `within_permitted_hours_flag`; province from the case | low (prompt rules) |
| BQ-014 | "randomised pilot", "certified for vulnerable customers", "30-day cure" | `case_assignment_history.assignment_method = 'randomised_pilot'`; direction "Yes" under every cure definition | low (G1 rule) |
| BQ-015 | "card and loan accounts", "12 months to 28 Sep" | `chargeoff_date` in `card_accounts` + `loan_accounts` (one row per account), 29 Sep 2025 – 28 Sep 2026 | low (prompt rule; test split, hand-checked) |
| BQ-030 | "outbound call volume" | calls = `coalesce(channel_v2, channel) = 'call'`, outbound | low |
| BQ-001/002/005/009/019/020/026/033 | policy wording ("mid-stage account", "in a week", "grace period") | current policy wins over FAQ / superseded versions | low (document answers cite doc + section) |
| BQ-016/021/022 | "most recent recorded call" | latest `call_start_ts` for the case | low (`case_calls` tool) |

## Dev error analysis (P2-T9)

Score on our scorer (`python -m ontrack.l2_ask.score_dev`), full data:

| Stage | Dev | Notes |
|---|---:|---|
| Placeholders (runner only) | 3/21 | refusals only |
| + certified-metric templates (no LLM) | 13/21 | all 9 certified dev answers exact |
| + Claude agent (documents, transcripts, other SQL) | **21/21** | refusals 3/3, false refusals 0/18 |

Failures found and fixed on the way (general fixes, not per-question answers):

1. **Wrong table for contact events** (BQ-006 counted case-level disputes): convention added — events raised
   during contacts are counted from `contact_history` flags by `contact_ts_local`.
2. **"Why" questions lost their explanation** (BQ-030 returned only a table): new `explain` answer kind =
   one-sentence conclusion with cause / direction + the supporting table and SQL.
3. **Policy question refused as "legal advice"** (BQ-020, test split; flagged by P1): rule added — what our
   policies allow / require / do not cover is answered from the documents, never refused.
4. **FAQ contradicts the current policy** (BQ-026 trap): "policy wins over FAQ / script" rule; superseded
   versions labelled in the prompt and ranked last in search.
5. **Age wording** ("customers over 90 days past due") was refused as age: rule fixed; red-team 0/14 false refusals.

Caveats: our scorer approximates the organisers' (tables by key within tolerance; documents by cited doc + key
facts). Dev worked examples are shown to the agent leave-one-out (never the question being answered), so the dev
score is optimistic for the LLM path; certified-metric answers are deterministic and do not depend on examples.

## Runbook: extra questions at 19:00 IST, 4 Oct

```bash
git pull && python -m ontrack.l2_ask.search --build          # once, if the search index is missing
python -m ontrack.l2_ask.run_benchmark --questions <released + extra csv> --out submission/benchmark_answers.csv --workers 6
python -m ontrack.l2_ask.score_dev                            # dev still 21/21?
git add submission/benchmark_answers.csv && git commit -m "Benchmark: final answers" && git push
```

* Needs an LLM: `ANTHROPIC_API_KEY` in `.env`, or a logged-in Claude Code CLI (`claude`). Cached answers are reused.
* **Dry run (G2, 3 Oct night):** the 35 released + 15 mock extra questions (exact `benchmark_questions.csv` format,
  new ids, blank `metric_id`), no cache, Claude Code CLI, `--workers 4`: **50 answers in 132 s, 0 errors**.
* **If something fails (fallback, in this order):**
  1. Errors in the summary line (`Wrote N answers … (k errors)`): re-run only those, keeping the rest:
     `python -m ontrack.l2_ask.run_benchmark --questions <csv> --out submission/benchmark_answers.csv --retry-failed --workers 2`
  2. A Claude usage limit or network drop shows as many errors at once (on 3 Oct a run hit the limit: 13–16 of 35
     failed). Wait for the reset, or switch account / set `ANTHROPIC_API_KEY`, then `--retry-failed` again.
  3. Still failing: `--workers 1` (slower, gentlest on rate limits). Certified-metric questions and rule refusals
     never need the LLM, so they are always answered.
  4. Never edit `answers.csv` by hand; commit it exactly as generated.
* Any column layout works as long as `question_id` and `question_text` exist; a failing question is retried once
  and still gets a row. Per-question trace: `$ONTRACK_WORK_DIR/benchmark_trace.jsonl`.
* ~10 s per document question, ~20–60 s per non-certified data question, <1 s for certified metrics and rule refusals.

## Unseen-question rehearsal and test-split check (issue #9)

**Rehearsal** (`python -m ontrack.l2_ask.rehearsal`): 21 new questions with answers written by hand (independent
SQL that does not use our templates; key facts + citation for documents and calls): 11 data (6 certified, 5 not),
5 policy (incl. "can we call on 30 Sep" = must not be refused), 1 call summary, 4 refusals. **21/21** on a fresh run
(no cache). Found and fixed: "promotional" was refused only by the agent, now by the rules too.

**Test split, hand-checked** (no labels; checked against SQL / documents by hand):

| Q | Check | Verdict |
|---|---|---|
| BQ-001, 009, 033 | facts and sections match POL-COLL-001 §5.3 / §7.3, PRC-COLL-010 §3.3 | ✅ |
| BQ-008 | 29.46% with the certified default filters (insolvency / deceased holds excluded); 28.51% without. Kept the certified definition (dev gold always applies default filters) | ✅ (definition risk noted) |
| BQ-013 | sum of `amount_paid_against` by `paid_date` in Sep 2026 (metric time basis = payment date) | ✅ |
| BQ-014 | pilot = `case_assignment_history.assignment_method = 'randomised_pilot'`. Certified agents are higher under every definition (30 days from assignment 2.5% vs 1.6%; ever 3.6% vs 2.5%). One earlier run used the strategy test (`collections_cases.assignment_method = 'random'`) and said "No": fixed by a data convention in the prompt | ✅ "Yes" |
| BQ-015 | one row per account in `card_accounts` / `loan_accounts` (no snapshot double counting); 12 months = 29 Sep 2025 to 28 Sep 2026 | ✅ |
| BQ-020 | answered from the policies (not refused); says no policy permits legal action at two missed payments | ✅ |
| BQ-021 | matches transcript 510864 | ✅ |
| BQ-023, 029 | refused (PII; protected) | ✅ |
| BQ-025 | certified formula (outbound attempts / distinct cases in contact_history). Alternative "per open case incl. zero attempts" would be lower (1-30: 1.16 vs 1.50) | ✅ (definition risk noted) |
| BQ-027 | `sum(contact_cost_cad)/count(*)` by channel, system events excluded, channel_v2 coalesced | ✅ |
| BQ-030 | dialer outage INC-0923, ~60% capacity cut, calls 3,044 / 3,126 vs ~7,300 | ✅ |

## Backup runner (Garv's machine) (G13, G17): if Vansh's laptop or account fails at 19:00

On Garv's machine (own Claude Code login). Same three steps as `docs/rehearsal/1900_checklist.md`; target: full
answers within 15 minutes. **Nothing touches `submission/benchmark_answers.csv` until step 4.**

```bash
export PYTHONIOENCODING=utf-8; git pull                       # latest main
# 1. clean the organisers' file and ALWAYS put the released 35 first (ids kept once)
python scripts/normalize_questions.py D:/bench/extra_raw.csv D:/bench/final_questions.csv        --append-released "$MAPLE_DATA_DIR/data/benchmark_questions.csv"
# 2. answer into a scratch file ($ONTRACK_WORK_DIR/outputs/benchmark_answers.csv by default)
python -m ontrack.l2_ask.backup_run --questions D:/bench/final_questions.csv
# 3. check against the template and every question id
python scripts/check_submission.py --questions D:/bench/final_questions.csv --answers "$ONTRACK_WORK_DIR/outputs/benchmark_answers.csv"
# 4. only then
cp "$ONTRACK_WORK_DIR/outputs/benchmark_answers.csv" submission/benchmark_answers.csv
git checkout -b p2/final-answers && git add submission/benchmark_answers.csv && git commit -m "Benchmark: final answers"   && git push -u origin p2/final-answers          # main is protected: PR, ping Vansh in #13
```

**Two safety nets in `backup_run` (G17)**, so the released questions can't be dropped even if step 1 is skipped:
* it merges the given file after the released 35 by itself (released first, ids once; `--no-append-released` turns
  this off, only for a file that already is the full set);
* `validate()` fails if any released id (BQ-001 … BQ-035, read from `$MAPLE_DATA_DIR`) is missing from the answers.

`backup_run` also checks the data folder, database (bronze + gold), search index (builds it if missing), LLM access
(one test call) and that the file is readable; runs `run_benchmark --workers 4`; re-runs only failed questions up to
3 rounds with fewer workers; validates one row per unique id, no failed rows, `refused` true/false. Exit 0 only when
the file is complete.

Tested 4 Oct: the released 35 from the cache gave 35 rows, 0 errors, 2 s, `score_dev` **21/21**, byte-identical to
the committed answers. A file with **only one new question** gave 35 + 1 = 36 answers, `check_submission` "covers 36
question ids"; the same file with `--no-append-released` is caught by `validate` ("released questions missing (35)",
exit 1). Also 50 questions in 50 s; LLM broken → preflight stops (exit 2); certified questions answer without an LLM.
