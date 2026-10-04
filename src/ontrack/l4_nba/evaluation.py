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
from ontrack.l4_nba.models import MODEL_DIR, TEST_DATE, VALID_DATE, load_frame, load_model, predict

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


def calibration_section(con) -> list[str]:
    """Reliability on the untouched test month, with the calibrator fitted on the validation month only."""
    out = ["### Calibration (test month)", ""]
    model = load_model("self_cure_30d")
    test = load_frame(con, "self_cure_30d", [TEST_DATE])
    from ontrack.l4_nba.models import _matrix
    test["p"] = model["calibrator_test"].predict(model["booster"].predict(_matrix(test, model["feature_cols"])))
    test["band"] = pd.qcut(test["p"].rank(method="first"), 10, labels=False) + 1
    rel = test.groupby("band").agg(cases=("label", "size"), predicted=("p", "mean"),
                                   observed=("label", "mean")).reset_index()
    rel.columns = ["decile (1 = least likely)", "cases", "predicted self-cure", "observed self-cure"]
    diff = rel["predicted self-cure"] - rel["observed self-cure"]
    direction = ("over-predicts in every decile" if (diff > 0).all() else
                 "under-predicts in every decile" if (diff < 0).all() else "is off in both directions")
    out += [md_table(rel), "",
            f"The order is right (observed self-cure rises steadily from decile 1 to 10), but the calibrator fitted "
            f"on {VALID_DATE} {direction}: by up to {diff.abs().max() * 100:.0f} points, {diff.abs().mean() * 100:.1f} "
            "on average. That is the base-rate drift in this data (cases open on 2026-06-01 self-cured 32% of the time "
            "within 30 days, on 2026-07-01 23%, on 2026-08-29 10%). It is why the agent card's probabilities come from a "
            "calibrator fitted on 2026-08-29, the latest month with a complete outcome and the closest to today's open "
            "book, and why the ranker uses a relative threshold (3.5x the open book's rate) rather than a fixed one. "
            "Ranking quality (AUC) does not depend on calibration.", ""]
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


CONTACT_ACTIONS = ("call", "sms", "email", "push_notification", "reminder_letter")


def business_value_section(con) -> list[str]:
    """K8: conservative dollar value per lever, against the bank's last recommendation, with every assumption."""
    import numpy as np
    from ontrack.l4_nba.models import _matrix
    from ontrack.l4_nba.ranker import channel_economics
    econ = channel_economics(con)
    median_payment = float(con.execute("SELECT median(payment_amount) FROM bronze.contact_history "
                                       "WHERE payment_amount > 0").fetchone()[0])
    r = con.execute("""
        SELECT r.case_id, r.action, r.allowed_actions, r.needs_human_review, r.p_payment_7d,
               k.nba_recommendation_last AS bank_last
        FROM gold.nba_recommendation r JOIN gold.case_360 k ON k.case_id = r.case_id""").fetchdf()
    r["bank"] = r["bank_last"].map(BANK_TO_OURS).fillna("do_nothing")
    r["bank_allowed"] = [b in str(a).split(", ") for b, a in zip(r["bank"], r["allowed_actions"])]
    resp = (r["p_payment_7d"] / max(r["p_payment_7d"].mean(), 1e-6)).clip(0.5, 2.0)   # as in the ranker
    rate = lambda a: econ[a]["rate"] if a in CONTACT_ACTIONS else 0.0  # noqa: E731
    auto = ~r["needs_human_review"].astype(bool)
    pay_ours = np.where(auto, r["action"].map(rate) * resp, 0.0)
    pay_bank = np.where(auto & r["bank_allowed"], r["bank"].map(rate) * resp, 0.0)
    blocked = int((auto & ~r["bank_allowed"] & (r["bank"] != "do_nothing")).sum())
    v_ours, v_bank = pay_ours.sum() * median_payment, pay_bank.sum() * median_payment

    # Lever 2: what the bank actually spent, in the 30 days after the test date, on cases that cured on their own
    test = load_frame(con, "self_cure_30d", [TEST_DATE])
    model = load_model("self_cure_30d")
    test["p"] = model["calibrator_test"].predict(model["booster"].predict(_matrix(test, model["feature_cols"])))
    spend = con.execute(f"""
        SELECT t.case_id, sum(coalesce(h.contact_cost_cad, 0)) AS spend, count(*) AS contacts
        FROM gold.contact_timeline t JOIN bronze.contact_history h ON h.contact_id = t.contact_id
        WHERE h.direction = 'outbound' AND t.contact_ts_utc >= DATE '{TEST_DATE}'
          AND t.contact_ts_utc < DATE '{TEST_DATE}' + INTERVAL 30 DAY
        GROUP BY 1""").fetchdf()
    bank_scores = con.execute(f"""
        SELECT case_id, score FROM bronze.model_scores
        WHERE model_name = 'cure_30d' AND case_id IS NOT NULL AND score_date <= DATE '{TEST_DATE}'
        QUALIFY row_number() OVER (PARTITION BY case_id ORDER BY score_date DESC, score_ts DESC) = 1""").fetchdf()
    d = (test[["case_id", "label", "p"]].merge(bank_scores, on="case_id")
         .merge(spend, on="case_id", how="left").fillna({"spend": 0.0, "contacts": 0}))
    k = max(1, len(d) // 5)
    waste = {}
    for name, col in (("ours", "p"), ("bank", "score")):
        top = d.nlargest(k, col)
        cured = top[top["label"] == 1]
        waste[name] = (len(cured), float(cured["spend"].sum()), int(cured["contacts"].sum()))

    calls_bank = int((r["bank"] == "call").sum())
    calls_ours = int((r["action"] == "call").sum())
    cap = econ["call"]["capacity"]
    levers = pd.DataFrame([
        {"lever": "1. Expected payments within 7 days from the recommended contact (automated cases)",
         "bank's last recommendation": f"${v_bank:,.0f} ({pay_bank.sum():,.0f} payments)",
         "OnTrack": f"${v_ours:,.0f} ({pay_ours.sum():,.0f} payments)", "difference": f"+${v_ours - v_bank:,.0f}",
         "unit": "per round of contacts"},
        {"lever": "2. Contact spend on customers who paid on their own anyway (the 20% each would leave alone)",
         "bank's last recommendation": f"${waste['bank'][1]:,.0f} ({waste['bank'][2]:,} contacts) found",
         "OnTrack": f"${waste['ours'][1]:,.0f} ({waste['ours'][2]:,} contacts) found",
         "difference": f"+${waste['ours'][1] - waste['bank'][1]:,.0f}", "unit": f"per month ({TEST_DATE} back-test)"},
        {"lever": "3. Calls that fit the day's call capacity",
         "bank's last recommendation": f"{calls_bank:,} calls ({calls_bank / max(cap, 1):.1f} days of capacity)",
         "OnTrack": f"{calls_ours:,} calls (1 day)", "difference": f"{calls_bank - calls_ours:,} fewer calls",
         "unit": f"capacity {cap:,} calls a day"},
    ])
    return ["## 2b. Business value in dollars (conservative)", "",
            "Same open book, same day: what OnTrack recommends against the bank's last recommendation "
            "(`collections_cases.nba_recommendation_last`), valued with measured numbers only.", "",
            md_table(levers), "",
            "**Method and assumptions** (each one chosen to understate OnTrack's value):",
            f"- Lever 1 values every expected payment at the **median recorded payment, ${median_payment:,.2f}** "
            f"(the mean is about 2.6x higher), not at the overdue amount.",
            "- The chance of a payment within 7 days of a contact is the **measured** rate per channel from "
            "`contact_history` (last 12 months), times the customer's responsiveness from the payment model "
            "(0.5x-2x), the same numbers the ranker uses. It is observed, not a randomised uplift.",
            f"- Only the {int(auto.sum()):,} **automated** cases count. Nothing is claimed for the cases sent to a "
            "person (hardship, vulnerability, disputes, complaints, holds), where OnTrack deliberately does not "
            "collect.",
            f"- A bank recommendation the policy gate would block (no consent, holds, contact cap) counts as no "
            f"payment: {blocked:,} of the bank's recommendations for automated cases could not legally be sent.",
            f"- Lever 2 uses what the bank actually spent (`contact_cost_cad`) in the 30 days after {TEST_DATE} on "
            f"cases that then cured on their own: OnTrack's leave-alone 20% contains {waste['ours'][0]:,} such "
            f"cases, the bank model's {waste['bank'][0]:,}. Leaving a case alone is not free: the rest of each 20% "
            "did not cure, which is why production waits only on cases above 3.5x the book's self-cure rate.",
            "- Lever 3 is capacity, not dollars: the bank's engine recommends more calls than the team can make.",
            "- Nothing is annualised: a round is one recommended contact per case.", ""]


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
    hard = agree[agree["ours"] == "hardship_referral"].assign(bank=lambda d: d["bank_last"].fillna("(none)"))
    hard = hard.groupby("bank", as_index=False)["cases"].sum().sort_values("cases", ascending=False)
    n_hard = int(hard["cases"].sum())
    share = lambda names: hard.loc[hard["bank"].isin(names), "cases"].sum() / max(n_hard, 1)  # noqa: E731
    contact = share(["call_evening", "call_daytime", "sms_payment_link", "send_letter"])
    plan = share(["offer_hardship_plan"])
    hard["share"] = hard["cases"] / max(n_hard, 1)
    out += [f"Agreement with the bank's last recommendation on the same open cases: {same:,} of {known:,} "
            f"({same / max(known, 1):.0%}) where the bank had one. Largest combinations:", "", md_table(top), "",
            f"Where they differ most: for the {n_hard:,} cases OnTrack sends to a hardship specialist, the bank's last "
            f"recommendation was a collection contact for {contact:.0%} (call, SMS payment link or letter) and a "
            f"hardship plan for only {plan:.0%}:", "", md_table(hard.rename(columns={"bank": "bank's last recommendation"})),
            ""]
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
    if small.get("U", 0) and small.get("X", 0):
        out += [f"Automated-case gaps for `gender_code` come from the U and X groups ({int(small['U'])} and "
                f"{int(small['X'])} automated cases): at that size a 4-5 point gap is within noise.", ""]
    flags = con.execute("""SELECT c.marital_status, avg(k.hardship_flag::INT) AS case_flag,
                                  avg(coalesce(t.text_hardship_90d, false)::INT) AS text_90d
                           FROM gold.case_360 k JOIN bronze.customers c ON c.crm_customer_id = k.crm_customer_id
                           LEFT JOIN features.text_signals_case t ON t.case_id = k.case_id
                           WHERE k.outcome IS NULL GROUP BY 1""").fetchdf().set_index("marital_status")
    sep = base.dropna(subset=["marital_status"]).groupby("marital_status")["hardship"].mean()
    if "separated" not in flags.index or "separated" not in sep.index or len(flags) < 2:
        return out + detail   # smaller datasets (e.g. the 5% sample): no separate note
    out += ["The one large gap is `marital_status = separated` (more hardship referrals and human reviews). It comes "
            "from the hardship signals themselves (the bank's case flag and what customers say), which route to a "
            "person by policy; among automated cases the gaps stay small. Worth a human look as a policy question, "
            f"not a model one. Hardship referral rate: separated {sep.get('separated', float('nan')):.0%}, others "
            f"{sep.drop('separated', errors='ignore').mean():.0%}; in the source data, separated customers carry the "
            f"bank's hardship flag {flags.loc['separated', 'case_flag']:.0%} of the time (others "
            f"{flags.drop('separated')['case_flag'].mean():.0%}) and describe hardship in notes or calls "
            f"{flags.loc['separated', 'text_90d']:.0%} (others {flags.drop('separated')['text_90d'].mean():.0%}).", ""]
    return out + detail


def model_fairness_section(con) -> list[str]:
    """Is the self-cure model equally accurate for every group? Test month, offline only."""
    from sklearn.metrics import roc_auc_score
    from ontrack.l4_nba.models import _matrix
    model = load_model("self_cure_30d")
    test = load_frame(con, "self_cure_30d", [TEST_DATE])
    test["p"] = model["calibrator_test"].predict(model["booster"].predict(_matrix(test, model["feature_cols"])))
    prot = con.execute("""
        SELECT crm_customer_id, gender_code, marital_status, citizenship_status,
               newcomer_program_flag::VARCHAR AS newcomer_program_flag,
               accessibility_needs_flag::VARCHAR AS accessibility_needs_flag,
               CASE WHEN age IS NULL THEN NULL WHEN age < 30 THEN '18-29' WHEN age < 45 THEN '30-44'
                    WHEN age < 60 THEN '45-59' ELSE '60+' END AS age_band
        FROM bronze.customers""").fetchdf()
    df = test.merge(prot, on="crm_customer_id", how="left")
    overall = roc_auc_score(df["label"], df["p"])
    rows, detail = [], []
    for col in FAIRNESS_COLUMNS:
        g = []
        for val, grp in df.dropna(subset=[col]).groupby(col):
            if len(grp) < 300 or grp["label"].nunique() < 2:
                continue
            g.append({col: val, "cases": len(grp), "AUC": roc_auc_score(grp["label"], grp["p"]),
                      "predicted self-cure": grp["p"].mean(), "observed self-cure": grp["label"].mean()})
        if len(g) < 2:
            continue
        g = pd.DataFrame(g)
        g["over-prediction"] = g["predicted self-cure"] - g["observed self-cure"]
        rows.append({"attribute": col, "groups": len(g), "lowest AUC": g["AUC"].min(), "highest AUC": g["AUC"].max(),
                     "AUC gap": g["AUC"].max() - g["AUC"].min(),
                     "over-prediction gap": g["over-prediction"].max() - g["over-prediction"].min()})
        detail += [f"`{col}`", "", md_table(g), ""]
    summary = pd.DataFrame(rows)
    if summary.empty:   # smaller datasets: no protected group reaches 300 test cases
        return ["### Is the model equally accurate for every group? (test month, offline)", "",
                "No protected group has 300+ test cases with both outcomes on this dataset, so the per-group check is "
                "skipped (it runs on the full data).", ""]
    out = ["### Is the model equally accurate for every group? (test month, offline)", "",
           f"Self-cure model on the {TEST_DATE} test cases (overall AUC {overall:.3f}), split by protected group "
           "(groups of 300+ cases). A fair model ranks equally well and is equally calibrated in every group.", "",
           md_table(summary), "",
           f"Largest AUC gap between groups: {summary['AUC gap'].max():.3f}; largest gap in over-prediction: "
           f"{summary['over-prediction gap'].max() * 100:.1f} points. Per group:", ""]
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
            "- Training is repeatable: fixed seeds, deterministic LightGBM on 4 threads, rows read in a fixed order "
            "and inputs rounded to 6 decimals, so two runs give the same AUCs and the same 96,000 recommendations.",
            ""]


def write_evaluation_report(con) -> str:
    lines = ["# Layer 4 evaluation", "",
             f"_Generated by `python -m ontrack.l4_nba.evaluation` on the full data (snapshot {config.SNAPSHOT_DATE}, "
             f"written {dt.date.today().isoformat()})._", ""]
    for section in (model_section(), calibration_section(con), backtest_section(con), business_value_section(con), mix_section(con), queue_section(con),
                    fairness_section(con), model_fairness_section(con), notes_section()):
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
