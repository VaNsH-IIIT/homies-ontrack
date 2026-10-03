"""Layer 4 models: LightGBM self-cure and payment propensity (owner: P3).

    python -m ontrack.l4_nba.models

Two binary classifiers on ``features.case_features``, trained point-in-time (issue #3):

* population at each ``as_of``: cases open and unresolved at that date (``build_case_features``);
* labels measured strictly after ``as_of``:
    - ``self_cure_30d``: the case is cured (outcome ``cured``) with ``as_of < cure_date <= as_of + 30 days``;
      cured later, closed another way, or still open after 30 days -> 0
    - ``payment_7d``: a payment through any contact (agent call, SMS/email payment link, app, IVR) with
      ``as_of <= contact_ts_utc < as_of + 7 days``
* time split: monthly ``as_of`` dates stacked for training, a later month for early stopping and
  isotonic calibration, a later month again as the untouched test set (reported AUC);
* monotone constraints in the direction of the label (higher overdue -> less likely to self-cure);
* sanity check: retrain without the top SHAP feature; a collapse would mean one feature carries the label;
* baseline: the bank's existing ``model_scores`` (``cure_30d``, ``self_cure``) on the same test cases.
"""
from __future__ import annotations

import json
import pickle

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import brier_score_loss, roc_auc_score

from ontrack import config
from ontrack.l3_features.structured.features import FEATURE_COLUMNS, TABLE, build_case_features

MODEL_DIR = config.WORK_DIR / "models"
MODEL_VERSION = "p3-v1.0"

TRAIN_DATES = ["2025-11-01", "2025-12-01", "2026-01-01", "2026-02-01", "2026-03-01", "2026-04-01", "2026-05-01"]
VALID_DATE = "2026-06-01"   # early stopping + calibration
TEST_DATE = "2026-07-01"    # reported metrics; the bank's scores dated 2026-06-30 line up with it
# Production calibration: the latest as_of whose 30-day outcome is complete (as_of + 30 = snapshot). Its
# population (long-running open cases, ~10% self-cure) is closest to the live book, so the probabilities
# shown to agents are realistic. Ranking and AUC do not depend on it.
LIVE_CALIBRATION_DATE = "2026-08-29"

LABEL_SQL = {
    "self_cure_30d": """
        SELECT f.case_id, f.as_of_date,
               coalesce(c.outcome = 'cured' AND c.cure_date > f.as_of_date
                        AND c.cure_date <= f.as_of_date + INTERVAL 30 DAY, false)::INT AS label
        FROM {table} f JOIN gold.case_360 c ON c.case_id = f.case_id
        WHERE f.as_of_date IN ({dates})
    """,
    "payment_7d": """
        SELECT f.case_id, f.as_of_date,
               (count(h.contact_id) > 0)::INT AS label
        FROM {table} f
        LEFT JOIN gold.contact_timeline t ON t.case_id = f.case_id
             AND t.contact_ts_utc >= f.as_of_date AND t.contact_ts_utc < f.as_of_date + INTERVAL 7 DAY
        LEFT JOIN bronze.contact_history h ON h.contact_id = t.contact_id
             AND (coalesce(h.payment_taken_flag, false) OR coalesce(h.link_payment_flag, false)
                  OR coalesce(h.app_payment_after_contact_flag, false)
                  OR coalesce(h.ivr_self_serve_payment_flag, false))
        WHERE f.as_of_date IN ({dates})
        GROUP BY 1, 2
    """,
}

# +1: higher value -> higher probability of the label. Same direction for both labels (both are good outcomes).
MONOTONE = {
    "self_cure_30d": {
        "overdue_now": -1, "overdue_growth_pct": -1, "days_since_last_payment": -1,
        "acct_months_min_paid_6m": 1, "bureau_score": 1, "bureau_delinquent_trades": -1,
        "salary_gap_months_3m": -1,
    },
    "payment_7d": {
        "days_since_last_payment": -1, "payments_30d": 1, "acct_months_min_paid_6m": 1,
        "bureau_score": 1, "salary_gap_months_3m": -1,
    },
}

# Repeatable training (K1): every seed fixed, deterministic histogram building on a fixed number of threads.
# Together with ordered input rows and rounded inputs (load_frame / _matrix), two runs give identical models.
PARAMS = {
    "objective": "binary", "metric": "auc", "learning_rate": 0.03, "num_leaves": 31,
    "min_child_samples": 100, "feature_fraction": 0.8, "bagging_fraction": 0.8, "bagging_freq": 1,
    "lambda_l2": 1.0, "verbosity": -1, "seed": 42, "bagging_seed": 42, "feature_fraction_seed": 42,
    "data_random_seed": 42, "deterministic": True, "force_col_wise": True, "num_threads": 4,
}
ROUND_DECIMALS = 6   # parallel float sums can differ in the last bits between runs


def ensure_features(con, dates: list[str]) -> None:
    """Build the feature rows for any of ``dates`` not yet in features.case_features."""
    have = set()
    try:
        have = {str(r[0]) for r in con.execute(f"SELECT DISTINCT as_of_date FROM {TABLE}").fetchall()}
    except Exception:
        pass
    for d in dates:
        if d not in have:
            build_case_features(con, d)


def load_frame(con, model_name: str, dates: list[str]) -> pd.DataFrame:
    """Features + label for the given as_of dates."""
    in_list = ", ".join(f"DATE '{d}'" for d in dates)
    labels = LABEL_SQL[model_name].format(table=TABLE, dates=in_list)
    return con.execute(f"""
        SELECT f.*, l.label FROM {TABLE} f
        JOIN ({labels}) l ON l.case_id = f.case_id AND l.as_of_date = f.as_of_date
        WHERE f.as_of_date IN ({in_list})
        ORDER BY f.as_of_date, f.case_id
    """).fetchdf()


def _matrix(df: pd.DataFrame, cols: list[str]) -> np.ndarray:
    return np.round(df[cols].astype(float).to_numpy(), ROUND_DECIMALS)


def _fit(train: pd.DataFrame, valid: pd.DataFrame, cols: list[str], model_name: str) -> lgb.Booster:
    params = dict(PARAMS, monotone_constraints=[MONOTONE[model_name].get(c, 0) for c in cols])
    pos = train["label"].mean()
    if pos < 0.05:  # rare label: weight positives up for the trees; isotonic calibration undoes it
        params["scale_pos_weight"] = min(20.0, (1 - pos) / max(pos, 1e-6) / 5)
    dtrain = lgb.Dataset(_matrix(train, cols), label=train["label"], feature_name=cols, free_raw_data=False)
    dvalid = lgb.Dataset(_matrix(valid, cols), label=valid["label"], reference=dtrain)
    return lgb.train(params, dtrain, num_boost_round=1500, valid_sets=[dvalid],
                     callbacks=[lgb.early_stopping(75, verbose=False)])


def _auc(y, p) -> float:
    return float(roc_auc_score(y, p)) if len(np.unique(y)) > 1 else float("nan")


def baseline_auc(con, test: pd.DataFrame, test_date: str) -> dict:
    """AUC of the bank's existing case scores (latest score on or before as_of) on our test rows."""
    out = {}
    scores = con.execute("""
        SELECT case_id, model_name, score FROM bronze.model_scores
        WHERE model_name IN ('cure_30d', 'self_cure', 'roll_forward_30d') AND case_id IS NOT NULL
          AND score_date <= CAST(? AS DATE) AND score IS NOT NULL
        QUALIFY row_number() OVER (PARTITION BY case_id, model_name ORDER BY score_date DESC, score_ts DESC) = 1
    """, [test_date]).fetchdf()
    for name, grp in scores.groupby("model_name"):
        m = test[["case_id", "label", "p"]].merge(grp[["case_id", "score"]], on="case_id")
        if len(m) < 100 or m["label"].nunique() < 2:
            continue
        s = -m["score"] if name == "roll_forward_30d" else m["score"]  # roll-forward is the opposite event
        out[name] = {"rows": int(len(m)), "auc_bank": round(_auc(m["label"], s), 4),
                     "auc_ours_same_rows": round(_auc(m["label"], m["p"]), 4)}
    return out


def train_model(con, model_name: str) -> dict:
    train = load_frame(con, model_name, TRAIN_DATES)
    valid = load_frame(con, model_name, [VALID_DATE])
    test = load_frame(con, model_name, [TEST_DATE])
    cols = list(FEATURE_COLUMNS)

    booster = _fit(train, valid, cols, model_name)
    raw_valid = booster.predict(_matrix(valid, cols))
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(raw_valid, valid["label"])
    raw_test = booster.predict(_matrix(test, cols))
    p_test = iso.predict(raw_test)
    test = test.assign(p=p_test)
    resolved = test["case_id"].isin(set(con.execute(
        "SELECT case_id FROM gold.case_360 WHERE outcome IS NOT NULL").fetchdf()["case_id"])).to_numpy()

    # top features by mean |SHAP| on the test set
    contrib = booster.predict(_matrix(test, cols), pred_contrib=True)[:, :-1]
    importance = pd.Series(np.abs(contrib).mean(axis=0), index=cols).sort_values(ascending=False)

    # sanity check: drop the top feature and retrain
    top = importance.index[0]
    cols_wo = [c for c in cols if c != top]
    booster_wo = _fit(train, valid, cols_wo, model_name)
    auc_wo = _auc(test["label"], booster_wo.predict(_matrix(test, cols_wo)))

    live = load_frame(con, model_name, [LIVE_CALIBRATION_DATE])
    iso_live = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(
        booster.predict(_matrix(live, cols)), live["label"])

    meta = {
        "model_name": model_name, "model_version": MODEL_VERSION,
        "live_calibration": {"as_of": LIVE_CALIBRATION_DATE, "rows": len(live),
                             "positive_rate": round(float(live["label"].mean()), 4)},
        "train_dates": TRAIN_DATES, "valid_date": VALID_DATE, "test_date": TEST_DATE,
        "rows": {"train": len(train), "valid": len(valid), "test": len(test)},
        "positive_rate": {"train": round(float(train["label"].mean()), 4),
                          "valid": round(float(valid["label"].mean()), 4),
                          "test": round(float(test["label"].mean()), 4)},
        "best_iteration": booster.best_iteration,
        "auc_valid": round(_auc(valid["label"], raw_valid), 4),
        "auc_test": round(_auc(test["label"], raw_test), 4),
        # cases that were resolved by the snapshot: signal beyond "this case is still open today"
        "auc_test_later_resolved": round(_auc(test.loc[resolved, "label"], raw_test[resolved]), 4),
        "brier_test_calibrated": round(float(brier_score_loss(test["label"], p_test)), 4),
        "mean_p_test_calibrated": round(float(p_test.mean()), 4),
        "top_features": {k: round(float(v), 4) for k, v in importance.head(8).items()},
        "sanity_drop_top_feature": {"dropped": top, "auc_test": round(auc_wo, 4)},
        "baseline_bank_scores": baseline_auc(con, test, TEST_DATE),
        "feature_cols": cols,
    }

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    with open(MODEL_DIR / f"{model_name}.pkl", "wb") as f:
        pickle.dump({"booster": booster, "calibrator": iso_live, "calibrator_test": iso,
                     "feature_cols": cols, "meta": meta}, f)
    with open(MODEL_DIR / f"{model_name}_meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, default=str)

    print(f"\n{model_name}: train {len(train):,} rows ({meta['positive_rate']['train']:.1%} positive), "
          f"test {len(test):,} rows ({meta['positive_rate']['test']:.1%} positive) on {TEST_DATE}")
    print(f"  AUC valid {meta['auc_valid']:.3f} | AUC test {meta['auc_test']:.3f} | "
          f"Brier test {meta['brier_test_calibrated']:.4f} | best iteration {booster.best_iteration}")
    print(f"  AUC test on cases resolved by the snapshot: {meta['auc_test_later_resolved']:.3f}")
    print(f"  top features: {', '.join(list(meta['top_features'])[:5])}")
    print(f"  sanity: without '{top}' AUC test = {auc_wo:.3f}")
    for name, b in meta["baseline_bank_scores"].items():
        print(f"  bank's {name}: AUC {b['auc_bank']:.3f} vs ours {b['auc_ours_same_rows']:.3f} on {b['rows']:,} rows")
    return meta


def load_model(model_name: str) -> dict:
    with open(MODEL_DIR / f"{model_name}.pkl", "rb") as f:
        return pickle.load(f)


def predict(model: dict, df: pd.DataFrame) -> np.ndarray:
    """Calibrated probabilities for the rows of ``df``."""
    raw = model["booster"].predict(_matrix(df, model["feature_cols"]))
    return model["calibrator"].predict(raw)


def train_all(con) -> dict[str, dict]:
    ensure_features(con, TRAIN_DATES + [VALID_DATE, TEST_DATE, LIVE_CALIBRATION_DATE])
    return {name: train_model(con, name) for name in LABEL_SQL}


if __name__ == "__main__":
    from ontrack.db import connect
    con = connect()
    train_all(con)
    con.close()
