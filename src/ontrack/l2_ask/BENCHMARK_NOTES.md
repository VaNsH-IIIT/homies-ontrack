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
| BQ-006 | dev | D | contact_history | `dispute_raised_flag`, 15–22 Sep vs 7–14 Sep on `contact_ts_local`; spike after INC-0914 |
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
python -m ontrack.l2_ask.run_benchmark --questions <released + extra csv> --out benchmark/answers.csv --workers 6
python -m ontrack.l2_ask.score_dev                            # dev still 21/21?
git add benchmark/answers.csv && git commit -m "Benchmark: final answers" && git push
```

* Needs an LLM: `ANTHROPIC_API_KEY` in `.env`, or a logged-in Claude Code CLI (`claude`). Cached answers are reused.
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
