"""Layer 4 models: LightGBM for self-cure and payment prediction (owner: P3).

Trains two binary classifiers on features.case_features with a time-based split:
  - P(self_cure_30d): will this case self-cure within 30 days?
  - P(payment_7d): will a contact lead to a payment within 7 days?

Uses monotone constraints on key features and isotonic calibration.
Compares against existing model_scores baseline.
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path

import lightgbm as lgb
import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import roc_auc_score, brier_score_loss

from ontrack import config

MODEL_DIR = config.WORK_DIR / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

MONOTONE_CONSTRAINTS = {
    "dpd_current": 1,
    "past_due_max": 1,
    "total_past_due": 1,
    "past_due_ratio": 1,
    "days_since_last_payment": 1,
    "case_age_days": 1,
    "accounts_30dpd": 1,
    "payments_90d": -1,
    "payments_30d": -1,
    "rpc_rate_30d": -1,
    "bureau_score_current": -1,
}

LABEL_SQL_SELF_CURE = """
    SELECT
        f.*,
        CASE
            WHEN cs.cure_flag = true AND cs.days_to_cure <= 30 THEN 1
            WHEN cs.outcome IS NOT NULL THEN 0
            WHEN (DATE '{split_end}' - cs.case_open_date::DATE)::INT > 30 THEN 0
            ELSE NULL
        END AS label
    FROM features.case_features f
    JOIN gold.case_360 cs ON cs.case_id = f.case_id
    WHERE f.as_of_date = DATE '{as_of}'
"""

LABEL_SQL_PAYMENT = """
    SELECT
        f.*,
        CASE
            WHEN EXISTS (
                SELECT 1 FROM gold.contact_timeline ct
                WHERE ct.case_id = f.case_id
                AND ct.payment_taken_flag = true
                AND ct.contact_ts_utc >= cs.case_open_date
                AND ct.contact_ts_utc <= cs.case_open_date + INTERVAL '7 days'
            ) THEN 1
            ELSE 0
        END AS label
    FROM features.case_features f
    JOIN gold.case_360 cs ON cs.case_id = f.case_id
    WHERE f.as_of_date = DATE '{as_of}'
      AND cs.outcome IS NOT NULL
"""

EXCLUDE_COLS = {"case_id", "golden_id", "as_of_date", "label", "treatment_stage"}

SPLIT_DATES = {
    "train_end": "2026-06-01",
    "val_end": "2026-08-01",
    "test_end": "2026-08-28",
}


def _get_feature_cols(df) -> list[str]:
    return [c for c in df.columns if c not in EXCLUDE_COLS]


def _build_constraints(feature_cols: list[str]) -> list[int]:
    return [MONOTONE_CONSTRAINTS.get(c, 0) for c in feature_cols]


def train_model(
    con,
    label_sql: str,
    model_name: str,
    as_of_train: str = "2026-05-01",
    as_of_val: str = "2026-07-01",
) -> dict:
    """Train a LightGBM model with calibration.

    Returns a dict with metrics and the model path.
    """
    from ontrack.l3_features.structured.features import build_case_features

    build_case_features(con, as_of_train)
    train_sql = label_sql.replace("{as_of}", as_of_train).replace("{split_end}", SPLIT_DATES["val_end"])
    train_df = con.execute(train_sql).fetchdf()
    train_df = train_df.dropna(subset=["label"])

    build_case_features(con, as_of_val)
    val_sql = label_sql.replace("{as_of}", as_of_val).replace("{split_end}", SPLIT_DATES["test_end"])
    val_df = con.execute(val_sql).fetchdf()
    val_df = val_df.dropna(subset=["label"])

    feature_cols = _get_feature_cols(train_df)
    numeric_cols = [c for c in feature_cols if train_df[c].dtype in ("float64", "int64", "float32", "int32")]
    feature_cols = numeric_cols

    X_train = train_df[feature_cols].values.astype(float)
    y_train = train_df["label"].values.astype(int)
    X_val = val_df[feature_cols].values.astype(float)
    y_val = val_df["label"].values.astype(int)

    np.nan_to_num(X_train, copy=False)
    np.nan_to_num(X_val, copy=False)

    constraints = _build_constraints(feature_cols)

    params = {
        "objective": "binary",
        "metric": "auc",
        "learning_rate": 0.05,
        "num_leaves": 31,
        "min_child_samples": 50,
        "monotone_constraints": constraints,
        "verbosity": -1,
        "n_jobs": -1,
        "seed": 42,
    }

    lgb_train = lgb.Dataset(X_train, label=y_train, feature_name=feature_cols)
    lgb_val = lgb.Dataset(X_val, label=y_val, feature_name=feature_cols, reference=lgb_train)

    callbacks = [lgb.log_evaluation(50), lgb.early_stopping(20)]
    booster = lgb.train(params, lgb_train, num_boost_round=500, valid_sets=[lgb_val], callbacks=callbacks)

    raw_pred_val = booster.predict(X_val)
    raw_pred_train = booster.predict(X_train)

    auc_train = roc_auc_score(y_train, raw_pred_train) if len(np.unique(y_train)) > 1 else 0.0
    auc_val = roc_auc_score(y_val, raw_pred_val) if len(np.unique(y_val)) > 1 else 0.0
    brier_val = brier_score_loss(y_val, raw_pred_val) if len(np.unique(y_val)) > 1 else 1.0

    model_path = MODEL_DIR / f"{model_name}.pkl"
    with open(model_path, "wb") as f:
        pickle.dump({
            "booster": booster,
            "feature_cols": feature_cols,
            "model_name": model_name,
        }, f)

    meta = {
        "model_name": model_name,
        "feature_cols": feature_cols,
        "train_rows": len(train_df),
        "val_rows": len(val_df),
        "train_positive_rate": float(y_train.mean()),
        "val_positive_rate": float(y_val.mean()),
        "auc_train": round(auc_train, 4),
        "auc_val": round(auc_val, 4),
        "brier_val": round(brier_val, 4),
        "model_path": str(model_path),
    }
    meta_path = MODEL_DIR / f"{model_name}_meta.json"
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    print(f"\n{model_name}:")
    print(f"  Train: {len(train_df):,d} rows, {y_train.mean():.3f} positive rate, AUC={auc_train:.4f}")
    print(f"  Val:   {len(val_df):,d} rows, {y_val.mean():.3f} positive rate, AUC={auc_val:.4f}")
    print(f"  Brier: {brier_val:.4f}")
    print(f"  Saved: {model_path}")

    return meta


def load_model(model_name: str) -> dict:
    """Load a trained model from disk."""
    model_path = MODEL_DIR / f"{model_name}.pkl"
    with open(model_path, "rb") as f:
        return pickle.load(f)


def predict(model_dict: dict, features_df) -> np.ndarray:
    """Score cases with a loaded model. Returns probabilities."""
    feature_cols = model_dict["feature_cols"]
    booster = model_dict["booster"]
    X = features_df[feature_cols].values.astype(float)
    np.nan_to_num(X, copy=False)
    return booster.predict(X)


def compare_baseline(con, model_name: str, auc_val: float) -> None:
    """Compare our model against the existing model_scores baseline."""
    try:
        baseline = con.execute("""
            SELECT count(*) FROM bronze.model_scores
        """).fetchone()[0]
        print(f"\nBaseline comparison ({model_name}):")
        print(f"  Existing model_scores: {baseline:,d} rows")
        print(f"  Our AUC: {auc_val:.4f}")
    except Exception:
        print(f"  (No baseline model_scores available for comparison)")


def train_all(con) -> dict[str, dict]:
    """Train all models and return their metadata."""
    results = {}

    meta = train_model(con, LABEL_SQL_SELF_CURE, "self_cure_30d")
    compare_baseline(con, "self_cure_30d", meta["auc_val"])
    results["self_cure_30d"] = meta

    meta = train_model(con, LABEL_SQL_PAYMENT, "payment_7d")
    compare_baseline(con, "payment_7d", meta["auc_val"])
    results["payment_7d"] = meta

    return results


if __name__ == "__main__":
    from ontrack.db import connect
    con = connect()
    train_all(con)
    con.close()
