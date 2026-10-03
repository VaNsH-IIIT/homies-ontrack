# Layer 4 design notes (P3, Kris)

How Layer 3 structured features and Layer 4 (next best action) work after the fixes for #3, #5 and #7.
Numbers are from the full data (snapshot 2026-09-28); `EVALUATION.md` has the detail.

## Pipeline (`python -m ontrack.l4_nba.run`, ~90 s with training)

```
features.case_features (point-in-time, one row per case and as_of)
  -> models: self_cure_30d, payment_7d (LightGBM, trained on 7 stacked monthly as_of dates)
  -> hardship routing (case flag + customer's words + income shock; human-review reasons)
  -> policy gate (consent, cease, do-not-call, holds, dispute, contact cap, holidays, hardship)
  -> ranker (hardship first, then human review, then self-cure, then value per channel within capacity)
  -> gold.nba_recommendation (+ reasons, counterfactual, routing reason, evidence quote)
  -> Agent card (accept / edit / reject -> common.record_decision)
```

## Action set

| Action | Channel | When |
|---|---|---|
| `hardship_referral` | human queue | hardship only (case flag, customer's own words in the last 90 days, income shock) |
| `specialist_agent` | phone | needs a person for another reason: vulnerability, dispute, complaint, third-party representative |
| `do_nothing` | none | likely self-cure (>= 35%, 3.5x the open book's rate), nothing allowed, or not worth a contact |
| `call` | phone | most dollars at risk where contact has not worked, up to the day's call capacity (5,037) |
| `sms` / `email` / `push_notification` | digital payment link | best value channel the customer allows |
| `reminder_letter` | letter | no digital channel and no call slot, balance worth a $1.10 letter |

## Point-in-time features (`l3_features/structured/features.py`)

- Population at `as_of`: cases opened on or before it and **not cured or closed by then**.
- Inputs as known at `as_of`: contacts before it, the case's overdue at the latest milestone its age has
  reached, bureau pulls on or before it, salary months before its month, account month-ends at least 60 days
  before it (the monthly snapshot lags; same lag in training and scoring).
- Never read: snapshot-time values (`gold.c360_*` totals, `current_dpd`, `treatment_path`,
  `payments_since_open_*`, `accounts_in_case_count`), outcome columns, `config.PROTECTED_COLUMNS`,
  `promises_to_pay`. The function raises if an outcome or protected column appears.
- 36 features: case (overdue at entry and now, growth, age, product, open reason, prior cases), contacts
  (counts, right-party contacts, inbound, payments, link clicks, callbacks, hardship / dispute raised),
  bureau (score, utilisation, arrears elsewhere, applications), income (salary gaps, income change, payroll),
  accounts (minimum paid in the last 6 statements, utilisation, worst DPD, over limit).

## Labels and split (`l4_nba/models.py`)

- `self_cure_30d` = cured with `as_of < cure_date <= as_of + 30 days`; `payment_7d` = a payment through any
  contact (call, SMS / email link, app, IVR) in `[as_of, as_of + 7 days)`.
- Train on as_of 2025-11-01 ... 2026-05-01 (65K rows), early stopping + isotonic calibration on 2026-06-01,
  test on 2026-07-01 (32K rows). Production calibration on 2026-08-29, the latest month with a complete outcome.
- Results: self-cure AUC 0.83 on the test month (bank's `cure_30d` 0.72 on the same cases); payment AUC 0.58.
- **Repeatable:** fixed seeds, deterministic LightGBM on 4 threads, rows read in a fixed order, inputs rounded to
  6 decimals, deterministic tie-breaks; every training date is rebuilt each run. Two runs from scratch give the
  same AUCs and the same 96,000 recommendations. (Machines with different inputs, e.g. P1's cached Claude results,
  differ slightly: 0.828 vs 0.829.)
- **Calibration drift:** the self-cure rate of cases open at each date falls month by month (32% on 2026-06-01,
  23% on 2026-07-01, 10% on 2026-08-29: the open book never resolves inside the release). A calibrator fitted on
  June over-predicts July by up to 8 points, so the card's probabilities use the 2026-08-29 calibrator and the
  self-cure threshold is relative (3.5x the open book's rate).
- `p_roll_forward` = 1 - `p_cure_30d`: DPD rises by one a day until a case cures, so not curing within 30 days
  means rolling to the next bucket (used by Layer 2's roll-forward question). Cases that would pass 180 DPD
  within 30 days (DPD 151-180; charge-off happens at 181 in this data) cannot roll to a worse bucket: their
  `p_roll_forward` is NULL and the same number is `p_charge_off_risk`.

## Ranking (`l4_nba/ranker.py`)

Value of a contact = `overdue x (1 - p_cure) x response(channel) x responsiveness - unit cost`, where
response is measured from `contact_history` (payment within 7 days of an outbound contact, last 12 months:
SMS / email 12%, push 8%, call 3%, letter 2%), cost and capacity from `channel_capacity`, and responsiveness is
the payment model's score relative to the open book (0.5x-2x). `score` = dollars at risk = overdue x
(1 - p_cure), the queue priority.

## Agent card (`app/pages/3_Agent_Card.py`)

- Search by `case_id` or `golden_id` (demo case `CS-2026-583749`); clear it to browse the queue by action,
  human-only / automated and routing reason, highest dollars at risk first.
- Hardship banner with the customer's verbatim quote and its source; recommendation, channel, time window and
  service notes (French-speaking agent, manual dial); 3 reasons and a counterfactual; blocked actions with the
  rule behind each.
- **Why this channel:** expected value of every allowed action (`action_values`), with the decision path
  explained (hardship and human review: a person decides; calls are a deliberate policy for the most dollars at
  risk where contact has not worked, even when a payment link scores higher, decided by P1 on #17).
- **Supervisor view:** action mix with dollars at risk, and the human-only queue by first reason.
- Accept / edit / reject through `common.record_decision` (reason code needed to edit or reject), with history.

## Evaluation (`l4_nba/evaluation.py` -> `EVALUATION.md`)

Models and the drop-top-feature sanity check; calibration by decile; a like-with-like back-test against the bank's
`model_scores` (same cases on 2026-07-01, outcome after it; never cure rate by `nba_recommendation_last`, which
is selection); action mix, decision paths, channel economics; the human-only queue by reason; fairness offline:
recommendation rates by protected group (automated decisions within 5.5 points) and model accuracy by group
(self-cure AUC 0.800-0.849 in every group).

## How to check

```bash
python -m ontrack.l4_nba.run             # train + score, ~60 s
python -m ontrack.l4_nba.evaluation      # regenerate EVALUATION.md
pytest tests/test_policy_gate.py tests/test_hardship.py tests/test_ranker.py tests/test_l4_point_in_time.py
```

## What changed from the design (for the README table)

| Change | Why |
|---|---|
| **Training rows are point-in-time snapshots** (cases open at monthly `as_of` dates, labels after `as_of`) instead of one row per case | The first version leaked (AUC 0.96 / 0.997): rows included already-cured cases and features read 28-Sep values. Now AUC 0.83, honest and above the bank's own model on the same cases. |
| **Channel response measured from contact history, not uplift models** | `test_cell` has a no-contact holdout, but it still received contacts, so a clean per-channel uplift cannot be estimated; measured response rates and unit costs are used instead, and likely self-cures are left alone. |
| **Call capacity is a hard limit** (`channel_capacity`, 5,037 a day) | Calls go to the most dollars at risk where contact has not worked; payment links convert ~4x better per contact at a fraction of the cost. |
| **Hardship separated from human review** | Hardship (financial) gets `hardship_referral`; vulnerability, disputes, complaints, holds and cease requests need a person but are not hardship. Disputes from notes / calls are routed even without hardship. |
| **Template reasons from SHAP contributions**, not LLM narration | Fast, deterministic and auditable; every reason uses whole numbers and never contradicts its own value. |
| **No Feast / Redis online store** | Batch scoring of 96K cases takes about a minute in DuckDB. |
| **Language of service and autodialer consent do not block calls** | They change who calls and how (French-speaking agent, manual dial); blocking would treat customers differently. |
