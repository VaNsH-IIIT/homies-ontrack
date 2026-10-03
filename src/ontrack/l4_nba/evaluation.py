"""Evaluation for Layer 4: models, like-with-like back-test, action mix, human queue, fairness (owner: P3).

    python -m ontrack.l4_nba.evaluation        # writes src/ontrack/l4_nba/EVALUATION.md

Which comparison, and why (issue #7, point 6): ``collections_cases.nba_recommendation_last`` is tied to how
cases ended (cases with ``sms_payment_link`` cure 87%, every other recommendation 0%), so "cure rate by the
bank's recommendation" measures selection, not effect. This report compares like with like instead: the
same cases, at the same ``as_of`` (2026-07-01, the models' untouched test month), outcomes measured only
after it, scored by our model and by the bank's existing ``model_scores`` (dated 2026-06-30).
Protected attributes are read here only, offline, to test fairness; they never reach features or decisions.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pandas as pd

from ontrack import config
from ontrack.db import connect
from ontrack.l4_nba.models import MODEL_DIR, TEST_DATE, load_frame, load_model, predict

REPORT = Path(__file__).parent / "EVALUATION.md"
MIN_GROUP = 100
FAIRNESS_COLUMNS = ["gender_code", "marital_status", "citizenship_status", "newcomer_program_flag",
                    "accessibility_needs_flag", "age_band"]
BANK_TO_OURS = {"sms_payment_link": "sms", "call_evening": "call", "call_daytime": "call",
                "offer_hardship_plan": "hardship_referral", "send_letter": "reminder_letter"}


def md_table(df: pd.DataFrame, floatfmt: str = "{:,.3f}") -> str:
    """Markdown table without extra dependencies."""
    import numpy as np

    def fmt(v):
        if isinstance(v, (bool, np.bool_)):
            return str(bool(v))
        if isinstance(v, (int, np.integer)):
            return f"{int(v):,}"
        if isinstance(v, (float, np.floating)):
            if pd.isna(v):
                return ""
            return f"{v:,.0f}" if float(v).is_integer() and abs(v) >= 10 else floatfmt.format(v)
        return "" if v is None else str(v)
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    lines += ["| " + " | ".join(fmt(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join(lines)


def model_section() -> list[str]:
    out = ["## 1. Models (point-in-time, issue #3)", ""]
    rows = []
    for name in ("self_cure_30d", "payment_7d"):
        p = MODEL_DIR / f"{name}_meta.json"
        if not p.exists():
            continue
        m = json.loads(p.read_text(encoding="utf-8"))
        rows.append({"model": name, "train rows": m["rows"]["train"], "test rows": m["rows"]["test"],
                     "test positive rate": m["positive_rate"]["test"], "AUC valid": m["auc_valid"],
                     "AUC test": m["auc_test"], "AUC test, cases resolved by 28 Sep": m["auc_test_later_resolved"],
                     "Brier test": m["brier_test_calibrated"],
                     f"AUC without top feature ({m['sanity_drop_top_feature']['dropped']})":
                         m["sanity_drop_top_feature"]["auc_test"]})
        meta_last = m
    if not rows:
        return out + ["Models not trained yet.", ""]
    out += [f"Training rows: cases **open and unresolved** at each monthly as_of {', '.join(meta_last['train_dates'])}; "
            f"early stopping and calibration on {meta_last['valid_date']}; **test on {meta_last['test_date']}** "
            "(never seen in training). Labels are measured strictly after as_of: self-cure = cured within "
            "(as_of, as_of + 30 days]; payment = a payment through any contact in [as_of, as_of + 7 days).", ""]
    for r in rows:
        out += [f"**{r.pop('model')}**", "", md_table(pd.DataFrame([r])), ""]
    out += ["- The old numbers (AUC 0.964 / 0.997) were leakage: rows included cases already cured at as_of, the "
            "payment label sat before the feature date, and features read 28-Sep values (current DPD, latest bureau "
            "pull, `accounts_in_case_count`, which is above 1 only for cases still open today).",
            "- Sanity check: dropping the strongest feature does not collapse the AUC, so no single column carries "
            "the label.",
            "- 'Cases resolved by 28 Sep' removes the cases still open today: on those the self-cure model is much "
            "weaker (about 0.58). Much of its skill is spotting cases that get stuck, which is what the ranker needs "
            "(who will not pay on their own), but it is not a precise clock for when a case cures.",
            "- `payment_7d` is weak (payments are rare, 3%); it is only used as a 0.5x-2x responsiveness multiplier.",
            ""]
    m = json.loads((MODEL_DIR / "self_cure_30d_meta.json").read_text(encoding="utf-8"))
    out += ["Top drivers of the self-cure model (mean |SHAP| on the test month): "
            + ", ".join(f"`{k}`" for k in list(m["top_features"])[:6]) + ".", ""]
    return out


def backtest_section(con) -> list[str]:
    out = ["## 2. Back-test against the bank's models, like with like", "",
           f"Same cases, same date: every case open and unresolved on {TEST_DATE}, outcome after it. Our "
           "self-cure model vs the bank's `model_scores` (latest score on or before that date, `cure_30d`, "
           "`self_cure` and `roll_forward_30d` reversed). We do **not** compare cure rates by "
           "`nba_recommendation_last`: that column is tied to how cases ended (selection, not effect).", ""]
    test = load_frame(con, "self_cure_30d", [TEST_DATE])
    test["p"] = predict(load_model("self_cure_30d"), test)
    scores = con.execute("""
        SELECT case_id, model_name, score FROM bronze.model_scores
        WHERE model_name IN ('cure_30d', 'self_cure', 'roll_forward_30d') AND case_id IS NOT NULL
          AND score_date <= CAST(? AS DATE) AND score IS NOT NULL
        QUALIFY row_number() OVER (PARTITION BY case_id, model_name ORDER BY score_date DESC, score_ts DESC) = 1
    """, [TEST_DATE]).fetchdf()
    from sklearn.metrics import roc_auc_score
    rows = []
    for name, g in scores.groupby("model_name"):
        mm = test[["case_id", "label", "p"]].merge(g[["case_id", "score"]], on="case_id")
        s = -mm["score"] if name == "roll_forward_30d" else mm["score"]
        k = max(1, len(mm) // 5)
        ours_top = mm.nlargest(k, "p")["label"].mean()
        bank_top = mm.assign(s=s).nlargest(k, "s")["label"].mean()
        ours_bot = 1 - mm.nsmallest(k, "p")["label"].mean()
        bank_bot = 1 - mm.assign(s=s).nsmallest(k, "s")["label"].mean()
        rows.append({"bank model": name, "cases": len(mm), "cure rate": mm["label"].mean(),
                     "AUC bank": roc_auc_score(mm["label"], s), "AUC ours": roc_auc_score(mm["label"], mm["p"]),
                     "leave-alone 20%, cured: bank": bank_top, "leave-alone 20%, cured: ours": ours_top,
                     "act-now 20%, not cured: bank": bank_bot, "act-now 20%, not cured: ours": ours_bot})
    out += [md_table(pd.DataFrame(rows)), "",
            "Reading it: if the 20% of cases each model is most confident will self-cure were left alone, the "
            "'cured' columns show how many actually did; the 'act now' columns show how many of each model's "
            "bottom 20% really needed action. Higher is better in both.", ""]
    return out


def mix_section(con) -> list[str]:
    out = ["## 3. Recommendations for the open book (snapshot 2026-09-28)", ""]
    mix = con.execute("""SELECT action, count(*) AS cases, round(count(*) / sum(count(*)) OVER (), 3) AS share,
                                round(avg(p_cure_30d), 3) AS avg_self_cure, round(avg(overdue_now)) AS avg_overdue,
                                round(sum(needs_human_review::INT) / count(*), 3) AS human_review
                         FROM gold.nba_recommendation GROUP BY 1 ORDER BY 2 DESC""").fetchdf()
    path = con.execute("""SELECT decision_path, action, count(*) AS cases FROM gold.nba_recommendation
                          GROUP BY 1, 2 ORDER BY 1, 3 DESC""").fetchdf()
    out += [md_table(mix), "", "How each was decided (`decision_path`):", "", md_table(path), ""]
    out += ["- `hardship_referral` only for hardship cases (v0: 92% of all cases, 41K without hardship).",
            "- Calls are capped at the day's call capacity from `channel_capacity` and go to the cases with the "
            "most dollars at risk where contact has not worked; everyone else with a balance worth chasing gets "
            "the best digital channel they allow.",
            "- `channel` and `time_window` are filled for every case.", ""]
    from ontrack.l4_nba.ranker import channel_economics
    econ = channel_economics(con)
    out += ["Channel economics used (measured: payment within 7 days of an outbound contact, last 12 months; "
            "cost and capacity from `channel_capacity`):", "",
            md_table(pd.DataFrame([{"action": a, "contacts measured": e["contacts"], "payment within 7 days": e["rate"],
                                    "unit cost CAD": e["unit_cost"], "daily capacity": e["capacity"]}
                                   for a, e in econ.items()])), ""]
    agree = con.execute("""
        SELECT c.nba_recommendation_last AS bank_last, r.action AS ours, count(*) AS cases
        FROM gold.nba_recommendation r JOIN gold.case_360 c ON c.case_id = r.case_id
        GROUP BY 1, 2 ORDER BY 1, 3 DESC""").fetchdf()
    agree["bank_mapped"] = agree["bank_last"].map(BANK_TO_OURS)
    same = agree.loc[agree["bank_mapped"] == agree["ours"], "cases"].sum()
    known = agree.loc[agree["bank_last"].notna(), "cases"].sum()
    top = agree[agree["bank_last"].notna()].sort_values("cases", ascending=False).head(10)[["bank_last", "ours", "cases"]]
    out += [f"Agreement with the bank's last recommendation on the same open cases: {same:,} of {known:,} "
            f"({same / max(known, 1):.0%}) where the bank had one. Largest combinations:", "", md_table(top), "",
            "Disagreement is expected: the bank's engine sends an SMS link to almost everyone, including customers "
            "in hardship; OnTrack sends hardship to a person first.", ""]
    return out


def queue_section(con) -> list[str]:
    out = ["## 4. Human-only queue: who and why", ""]
    q = con.execute("""SELECT coalesce(routing_category, '(automated)') AS first_reason, count(*) AS cases,
                              round(count(*) / sum(count(*)) OVER (), 3) AS share_of_book
                       FROM gold.nba_recommendation GROUP BY 1 ORDER BY 2 DESC""").fetchdf()
    any_ = con.execute("""SELECT
            sum((routing_reasons ILIKE '%Case flagged for hardship%')::INT) AS case_hardship_flag,
            sum((routing_reasons ILIKE '%described hardship%')::INT) AS text_hardship_90d,
            sum((routing_reasons ILIKE '%Salary deposit%' OR routing_reasons ILIKE '%Income down%')::INT) AS income_shock,
            sum((routing_reasons ILIKE '%vulnerable%')::INT) AS vulnerability,
            sum((routing_reasons ILIKE '%disput%')::INT) AS dispute,
            sum((routing_reasons ILIKE '%complaint%')::INT) AS complaint,
            sum((routing_reasons ILIKE '%hold%' OR routing_reasons ILIKE '%Third-party%')::INT) AS holds,
            sum((routing_reasons ILIKE '%stop contacting%')::INT) AS cease,
            sum((routing_category = 'hardship_text')::INT) AS text_only_hardship
        FROM gold.nba_recommendation""").fetchdf().T.reset_index()
    any_.columns = ["signal (any, cases can have several)", "cases"]
    out += ["First (highest-priority) reason per case:", "", md_table(q), "", "Every signal, counted wherever it "
            "appears:", "", md_table(any_), "",
            "Hardship comes first (`hardship_case_flag` > `hardship_text` > `hardship_income`); text-only hardship "
            "is what notes and calls add on top of the case flag. Holds (insolvency, deceased, third-party), "
            "cease requests, disputes, complaints and vulnerability need a person by policy, without hardship.", ""]
    return out


def fairness_section(con) -> list[str]:
    out = ["## 5. Fairness check (offline only)", "",
           "Recommended-action rates by protected group on the open book. Protected attributes are joined here "
           "only, from `bronze.customers`, and are never features or decision inputs. Groups under "
           f"{MIN_GROUP} cases are not shown.", ""]
    base = con.execute(f"""
        SELECT r.action, r.needs_human_review, r.p_cure_30d,
               c.gender_code, c.marital_status, c.citizenship_status,
               c.newcomer_program_flag::VARCHAR AS newcomer_program_flag,
               c.accessibility_needs_flag::VARCHAR AS accessibility_needs_flag,
               CASE WHEN c.age IS NULL THEN NULL WHEN c.age < 30 THEN '18-29' WHEN c.age < 45 THEN '30-44'
                    WHEN c.age < 60 THEN '45-59' ELSE '60+' END AS age_band
        FROM gold.nba_recommendation r
        JOIN gold.case_360 k ON k.case_id = r.case_id
        JOIN bronze.customers c ON c.crm_customer_id = k.crm_customer_id
    """).fetchdf()
    base["digital"] = base["action"].isin(["sms", "email", "push_notification"])
    base["hardship"] = base["action"] == "hardship_referral"
    auto = base[~base["needs_human_review"].astype(bool)]
    summary, detail = [], []
    for col in FAIRNESS_COLUMNS:
        g = base.dropna(subset=[col]).groupby(col).agg(
            cases=("action", "size"), hardship_referral=("action", lambda s: (s == "hardship_referral").mean()),
            call=("action", lambda s: (s == "call").mean()), digital=("digital", "mean"),
            do_nothing=("action", lambda s: (s == "do_nothing").mean()),
            human_review=("needs_human_review", "mean"), avg_self_cure=("p_cure_30d", "mean")).reset_index()
        g = g[g["cases"] >= MIN_GROUP]
        if g.empty:
            continue
        detail += [f"**{col}**", "", md_table(g), ""]
        a = auto.dropna(subset=[col]).groupby(col).agg(
            n=("action", "size"), call=("action", lambda s: (s == "call").mean()), digital=("digital", "mean"),
            do_nothing=("action", lambda s: (s == "do_nothing").mean()))
        a = a[a["n"] >= MIN_GROUP]
        summary.append({"attribute": col, "groups": len(g),
                        "gap hardship_referral": g["hardship_referral"].max() - g["hardship_referral"].min(),
                        "gap human_review": g["human_review"].max() - g["human_review"].min(),
                        "automated cases: gap call": a["call"].max() - a["call"].min(),
                        "automated cases: gap digital": a["digital"].max() - a["digital"].min(),
                        "automated cases: gap do_nothing": a["do_nothing"].max() - a["do_nothing"].min()})
    out += ["Largest gap between groups (as fractions; 0.01 = 1 percentage point). The 'automated cases' columns "
            "are the cases the model and ranker decide alone (not in the human queue):", "",
            md_table(pd.DataFrame(summary)), ""]
    small = auto.groupby("gender_code").size()
    out += [f"Automated-case gaps for `gender_code` come from the U and X groups ({int(small.get('U', 0))} and "
            f"{int(small.get('X', 0))} automated cases): at that size a 4-5 point gap is within noise.", ""]
    flags = con.execute("""SELECT c.marital_status, avg(k.hardship_flag::INT) AS case_flag,
                                  avg(coalesce(t.text_hardship_90d, false)::INT) AS text_90d
                           FROM gold.case_360 k JOIN bronze.customers c ON c.crm_customer_id = k.crm_customer_id
                           LEFT JOIN features.text_signals_case t ON t.case_id = k.case_id
                           WHERE k.outcome IS NULL GROUP BY 1""").fetchdf().set_index("marital_status")
    sep = base.dropna(subset=["marital_status"]).groupby("marital_status")["hardship"].mean()
    out += ["The one large gap is `marital_status = separated` (more hardship referrals and human reviews). It comes "
            "from the hardship signals themselves (the bank's case flag and what customers say), which route to a "
            "person by policy; among automated cases the gaps stay small. Worth a human look as a policy question, "
            f"not a model one. Hardship referral rate: separated {sep.get('separated', float('nan')):.0%}, others "
            f"{sep.drop('separated', errors='ignore').mean():.0%}; in the source data, separated customers carry the "
            f"bank's hardship flag {flags.loc['separated', 'case_flag']:.0%} of the time (others "
            f"{flags.drop('separated')['case_flag'].mean():.0%}) and describe hardship in notes or calls "
            f"{flags.loc['separated', 'text_90d']:.0%} (others {flags.drop('separated')['text_90d'].mean():.0%}).", ""]
    return out + detail


def notes_section() -> list[str]:
    return ["## 6. Notes", "",
            "- The 96,000 open cases were all opened Apr-Sep 2026 and never resolve inside the release, so later "
            "training months have lower self-cure rates (61% of cases open on 2026-04-01 cured within 30 days, "
            "10% of those open on 2026-08-29). Production probabilities are calibrated on 2026-08-29, the latest "
            "month with a complete 30-day outcome; test metrics use the June calibrator.",
            "- The bank's no-contact holdout cured as often as its champion strategy (63.4% vs 62.7% within 30 "
            "days). The holdout still had some contacts, so this is a hint, not proof, that contact adds little for "
            "customers who would pay anyway; it is why OnTrack waits on likely self-cures.",
            "- `golden_id` values can differ between builds (the demo customer is G-0331645 on P1's build and "
            "G-0331648 on a fresh Windows build); `case_id` is stable, so the demo uses CS-2026-583749.", ""]


def write_evaluation_report(con) -> str:
    lines = ["# Layer 4 evaluation", "",
             f"_Generated by `python -m ontrack.l4_nba.evaluation` on the full data (snapshot {config.SNAPSHOT_DATE}, "
             f"written {dt.date.today().isoformat()})._", ""]
    for section in (model_section(), backtest_section(con), mix_section(con), queue_section(con),
                    fairness_section(con), notes_section()):
        lines += section
    report = "\n".join(lines)
    REPORT.write_text(report, encoding="utf-8", newline="\n")
    print(f"Evaluation report written to {REPORT}")
    return report


def main():
    con = connect(read_only=True)
    write_evaluation_report(con)
    con.close()


if __name__ == "__main__":
    main()
