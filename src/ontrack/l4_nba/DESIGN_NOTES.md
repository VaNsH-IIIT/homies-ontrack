# Layer 4 Design Notes (P3 — Kris)

## Action set

| Action | Channel | Cost signal | Notes |
|---|---|---|---|
| `do_nothing` | — | 0 | Self-cure path; no outbound contact |
| `call` | phone | `channel_capacity.unit_cost_cad` | Requires `consent_call`, permitted hours |
| `sms` | sms | `channel_capacity.unit_cost_cad` | Requires `consent_sms` |
| `email` | email | `channel_capacity.unit_cost_cad` | Requires `consent_email` |
| `push_notification` | push | `channel_capacity.unit_cost_cad` | Requires `consent_push` |
| `reminder_letter` | mail | `channel_capacity.unit_cost_cad` | Postal; no real-time consent gate |
| `hardship_referral` | — | 0 | Routes to human-only queue |
| `specialist_agent` | phone | `channel_capacity.unit_cost_cad` | Higher-skill agent; human review |

Legal/repossession deferred to phase 2.

## Labels

### 1. Self-cure in 30 days (primary)

**Source:** `collections_cases.cure_flag` and `collections_cases.days_to_cure`

```
label = 1  WHERE cure_flag = true AND days_to_cure <= 30
label = 0  WHERE outcome IS NOT NULL AND NOT (cure_flag AND days_to_cure <= 30)
           — i.e. case resolved some other way, or still open 30+ days later
```

Cases that are still open and fewer than 30 days old at the label horizon are excluded (censored).

### 2. Payment within 7 days of a contact

**Source:** `contact_history.payment_taken_flag`, `contact_history.link_payment_flag`

```
label = 1  WHERE any contact in the 7-day window has payment_taken_flag = true
label = 0  WHERE no payment within 7 days of the contact
```

Grain: one row per (case_id, contact_id). This is the action-response label: did this specific contact lead to a payment?

**Fallback:** if `payment_taken_flag` coverage is poor, fall back to matching payment events from `card_statements` or `loan_instalments` within 7 days of a contact timestamp.

### 3. Roll-forward (30-day DPD worsening)

**Source:** `collections_cases.dpd_at_entry` vs `dpd_at_day_30` (or `card_accounts.dpd` / `loan_accounts.dpd` 30 days later)

```
label = 1  WHERE dpd_at_day_30 > dpd_at_entry  — customer got worse
label = 0  WHERE dpd_at_day_30 <= dpd_at_entry — stayed same or improved
```

This is the primary business metric (30-day roll rate). A good self-cure model should be anti-correlated with roll-forward.

## Time-based train / validate / test split

Snapshot date: 2026-09-28. Outcomes need 30 days to mature.

| Split | Cases with outcome finalised in | Purpose |
|---|---|---|
| **Train** | before 2026-06-01 | Model fitting |
| **Validate** | 2026-06-01 to 2026-07-31 | Hyperparameter tuning, calibration |
| **Test** | 2026-08-01 to 2026-08-28 | Final hold-out evaluation |

Cases opened after 2026-08-28 cannot have mature 30-day outcomes by the snapshot, so they are scoring-only (open cases for NBA recommendations).

## Feature groups (built in P3-T3)

| Group | Examples | Source tables |
|---|---|---|
| Delinquency | `dpd`, `dpd_max_12m`, `dpd_trend_3m`, `times_30dpd_12m` | `gold.c360_account`, `bronze.account_monthly_snapshot` |
| Payment behaviour | `days_since_last_payment`, `payments_90d`, `payment_to_overdue_ratio` | `gold.contact_timeline`, `bronze.card_statements`, `bronze.loan_instalments` |
| Cash flow | `payroll_delay_days`, `salary_gap`, `ei_started`, `payment_failures` | `bronze.deposit_accounts`, `bronze.salary_credit_history` |
| Contact response | `answer_rate_30d`, `rpc_rate_30d`, `best_hour`, `cap_headroom` | `gold.contact_timeline`, `bronze.channel_capacity` |
| Bureau / exposure | `score_delta_90d`, `utilisation_trend` | `bronze.external`, `bronze.bureau_history` |
| Case-level | `case_age_days`, `treatment_stage`, `total_contacts`, `rpc_count` | `gold.case_360`, `gold.contact_timeline` |

Text features (`hardship_signal`, `stated_delay_reason`, etc.) come from P2's `features.text_signals` when available.

**Blocked columns:** outcome columns (`cure_flag`, `dpd_at_day_30`, `outcome`, `dpd_at_day_N`) and all `config.PROTECTED_COLUMNS` are never used as features.

## Model choices

- **Algorithm:** LightGBM (fast, interpretable via SHAP, supports monotone constraints)
- **Monotone constraints:** DPD and overdue amount increase risk monotonically; days since last payment increases risk
- **Calibration:** isotonic regression on the validate set
- **Comparison baseline:** existing `bronze.model_scores` and `bronze.nba_recommendation_last`

## Ranking logic

```
For each open case:
  1. Policy gate → allowed_actions, blocked_actions (with reasons)
  2. Score each allowed action: expected_recovery = P(payment|action) × expected_amount
  3. Subtract contact cost: net_value = expected_recovery - unit_cost_cad
  4. Rank by net_value; pick top action
  5. If hardship flagged → route to human-only queue regardless of score
  6. Generate top-3 SHAP reasons as plain-English sentences
```

## Decisions that differ from the submitted design

| Change | Why |
|---|---|
| Skip Feast/Redis online store for hackathon | DuckDB is fast enough for batch scoring; no real-time serving needed in the demo |
| Template-based explanations instead of LLM narration for v0 | Faster, no API cost, still satisfies "plain English" requirement; LLM narration added in phase 2 |
| Skip uplift modelling in v0 | Needs verified `test_cell` randomisation; direct response models first, uplift if `test_cell` is clean |
| Roll-forward as third label | Design mentions it as primary metric but lists only two models; adding it strengthens the business case |
