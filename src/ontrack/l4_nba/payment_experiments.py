"""K12: can the payment-within-7-days model do better? Reproducible experiments (owner: P3).

    python -m ontrack.l4_nba.payment_experiments      # ~3 min on the full data; read-only

Tries, against the current model (same training months, same validation and test months):
  1. extra point-in-time features: the customer's response history (share of past outbound contacts followed by a
     payment within 7 days, windows closed before as_of), link clicks and recency, usual payday timing;
  2. stronger regularisation (smaller trees, more data per leaf);
  3. the conditional question "will they pay if contacted?" (rows with a contact in the 7-day window only).
Decision rule (TASKS K12): merge only if test AUC improves by 0.03 or more. None did; see EVALUATION.md.
"""
from __future__ import annotations

import pandas as pd
from sklearn.metrics import roc_auc_score

from ontrack.l4_nba import models as M

PAY = ("coalesce(h.payment_taken_flag,false) OR coalesce(h.link_payment_flag,false) "
       "OR coalesce(h.app_payment_after_contact_flag,false) OR coalesce(h.ivr_self_serve_payment_flag,false)")
EXTRA = ["out_180d", "resp_rate_180d", "resp_n_180d", "clicks_90d", "days_since_click",
         "days_since_any_payment_cust", "days_to_payday", "payday_in_7d"]


def extra_features(con, dates: list[str]) -> pd.DataFrame:
    in_list = ", ".join(f"DATE '{d}'" for d in dates)
    con.execute(f"""CREATE OR REPLACE TEMP TABLE _k12_ev AS
        SELECT t.case_id, x.golden_id, t.contact_ts_utc AS ts, h.direction, ({PAY}) AS paid,
               (coalesce(h.link_clicked_flag,false) OR coalesce(h.email_clicked_flag,false)) AS clicked
        FROM gold.contact_timeline t JOIN bronze.contact_history h ON h.contact_id = t.contact_id
        JOIN gold.case_360 x ON x.case_id = t.case_id WHERE t.case_id IS NOT NULL""")
    con.execute("""CREATE OR REPLACE TEMP TABLE _k12_out AS
        SELECT o.golden_id, o.ts, (p.ts IS NOT NULL AND p.ts < o.ts + INTERVAL 7 DAY)::INT AS resp
        FROM (SELECT golden_id, ts FROM _k12_ev WHERE direction = 'outbound') o
        ASOF LEFT JOIN (SELECT golden_id, ts FROM _k12_ev WHERE paid) p ON o.golden_id = p.golden_id AND p.ts >= o.ts""")
    e = con.execute(f"""
    WITH f AS (SELECT case_id, golden_id, as_of_date FROM {M.TABLE} WHERE as_of_date IN ({in_list})),
    r AS (SELECT f.case_id, f.as_of_date, count(o.ts) AS out_180d, avg(o.resp) AS resp_rate_180d,
                 sum(o.resp) AS resp_n_180d
          FROM f LEFT JOIN _k12_out o ON o.golden_id = f.golden_id
               AND o.ts < f.as_of_date - INTERVAL 7 DAY AND o.ts >= f.as_of_date - INTERVAL 180 DAY GROUP BY 1, 2),
    c AS (SELECT f.case_id, f.as_of_date, count(e.ts) FILTER (WHERE e.clicked) AS clicks_90d,
                 min(f.as_of_date - e.ts::DATE) FILTER (WHERE e.clicked) AS days_since_click,
                 min(f.as_of_date - e.ts::DATE) FILTER (WHERE e.paid) AS days_since_any_payment_cust
          FROM f LEFT JOIN _k12_ev e ON e.golden_id = f.golden_id AND e.ts < f.as_of_date
               AND e.ts >= f.as_of_date - INTERVAL 90 DAY GROUP BY 1, 2),
    s AS (SELECT f.case_id, f.as_of_date, median(day(s.last_credit_date)) AS payday_dom
          FROM f JOIN gold.customer_xref x ON x.golden_id = f.golden_id AND x.source_system = 'crm'
          JOIN bronze.salary_credit_history s ON s.crm_customer_id = x.source_key AND s.last_credit_date IS NOT NULL
           AND strptime(s.credit_month || '-01', '%Y-%m-%d')::DATE < date_trunc('month', f.as_of_date)
           AND strptime(s.credit_month || '-01', '%Y-%m-%d')::DATE >= date_trunc('month', f.as_of_date) - INTERVAL 6 MONTH
          GROUP BY 1, 2)
    SELECT f.case_id, f.as_of_date, coalesce(r.out_180d, 0) AS out_180d, r.resp_rate_180d,
           coalesce(r.resp_n_180d, 0) AS resp_n_180d, coalesce(c.clicks_90d, 0) AS clicks_90d,
           coalesce(c.days_since_click, 999) AS days_since_click,
           coalesce(c.days_since_any_payment_cust, 999) AS days_since_any_payment_cust,
           CASE WHEN s.payday_dom IS NULL THEN NULL
                ELSE (CAST(s.payday_dom AS INT) - day(f.as_of_date) + 31) % 31 END AS days_to_payday
    FROM f LEFT JOIN r USING (case_id, as_of_date) LEFT JOIN c USING (case_id, as_of_date)
    LEFT JOIN s USING (case_id, as_of_date)""").fetchdf()
    e["payday_in_7d"] = (e["days_to_payday"] <= 7).astype(float).where(e["days_to_payday"].notna())
    return e


def _with_extra(con, dates, extra):
    df = M.load_frame(con, "payment_7d", dates)
    df["as_of_date"] = pd.to_datetime(df["as_of_date"])
    ex = extra.assign(as_of_date=pd.to_datetime(extra["as_of_date"]))
    return df.merge(ex, on=["case_id", "as_of_date"], how="left").sort_values(["as_of_date", "case_id"]).reset_index(drop=True)


def _auc(booster, df, cols) -> float:
    return round(float(roc_auc_score(df["label"], booster.predict(M._matrix(df, cols)))), 4)


def run(con) -> pd.DataFrame:
    extra = extra_features(con, M.TRAIN_DATES + [M.VALID_DATE, M.TEST_DATE])
    tr, va, te = (_with_extra(con, d, extra) for d in (M.TRAIN_DATES, [M.VALID_DATE], [M.TEST_DATE]))
    base = list(M.FEATURE_COLUMNS)
    rows = []
    for name, cols in [("current model", base), ("+ response history", base + EXTRA[:3]),
                       ("+ link clicks", base + EXTRA[3:6]), ("+ payday timing", base + EXTRA[6:]),
                       ("+ all new features", base + EXTRA)]:
        b = M._fit(tr, va, cols, "payment_7d")
        rows.append({"experiment": name, "AUC valid": _auc(b, va, cols), "AUC test": _auc(b, te, cols)})
    params = dict(M.PARAMS)
    try:
        M.PARAMS = {**params, "num_leaves": 7, "min_child_samples": 400}
        b = M._fit(tr, va, base, "payment_7d")
        rows.append({"experiment": "smaller trees (7 leaves, 400 per leaf)", "AUC valid": _auc(b, va, base),
                     "AUC test": _auc(b, te, base)})
    finally:
        M.PARAMS = params
    seen = set(map(tuple, con.execute(f"""
        SELECT DISTINCT t.case_id, f.as_of_date::VARCHAR FROM {M.TABLE} f JOIN gold.contact_timeline t
          ON t.case_id = f.case_id AND t.contact_ts_utc >= f.as_of_date AND t.contact_ts_utc < f.as_of_date + INTERVAL 7 DAY
        """).fetchall()))
    keep = lambda d: d[[(c, str(a)[:10]) in seen for c, a in zip(d["case_id"], d["as_of_date"])]].reset_index(drop=True)  # noqa: E731
    trc, vac, tec = keep(tr), keep(va), keep(te)
    b = M._fit(trc, vac, base, "payment_7d")
    rows.append({"experiment": "only cases contacted in the window (pay if contacted?)", "AUC valid": _auc(b, vac, base),
                 "AUC test": _auc(b, tec, base)})
    out = pd.DataFrame(rows)
    out["vs current (test)"] = (out["AUC test"] - out.loc[0, "AUC test"]).round(4)
    return out


if __name__ == "__main__":
    from ontrack.db import connect
    print(run(connect(read_only=True)).to_string(index=False))
