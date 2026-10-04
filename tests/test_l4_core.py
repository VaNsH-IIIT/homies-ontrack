"""Layer 4 core logic: call capacity, reasons, channel economics, policy timing, model fitting (owner: P3).

Synthetic data only; no dataset needed.
"""
import datetime as dt

import duckdb
import numpy as np
import pandas as pd
import pytest
from sklearn.isotonic import IsotonicRegression

from ontrack.l4_nba import models as M
from ontrack.l4_nba.hardship import _num, _truthy
from ontrack.l4_nba.policy_gate import check_permitted_hours, check_stat_holidays
from ontrack.l4_nba.ranker import (
    _cad,
    _pct,
    _reason_1,
    _time_window,
    allocate_calls,
    channel_economics,
)

ECON = {
    "call": {"rate": 0.03, "unit_cost": 2.40, "capacity": 2},
    "sms": {"rate": 0.12, "unit_cost": 0.01, "capacity": 100},
    "email": {"rate": 0.12, "unit_cost": 0.001, "capacity": 100},
    "push_notification": {"rate": 0.08, "unit_cost": 0.001, "capacity": 100},
    "reminder_letter": {"rate": 0.02, "unit_cost": 1.10, "capacity": 100},
    "specialist_agent": {"rate": 0.03, "unit_cost": 7.20, "capacity": 0},
}


# ---------------------------------------------------------------------------------------------- call capacity
def case(cid, loss, action="email", candidate=True, values=None):
    return {"case_id": cid, "expected_loss": loss, "action": action, "path": "value", "call_candidate": candidate,
            "values": values if values is not None else {"email": 5.0, "call": 1.0}}


class TestAllocateCalls:
    def test_capacity_goes_to_most_dollars_at_risk(self):
        rows = [case("A", 100), case("B", 300), case("C", 200)]
        allocate_calls(rows, call_capacity=2)
        assert {r["case_id"]: r["action"] for r in rows} == {"A": "email", "B": "call", "C": "call"}

    def test_ties_broken_by_case_id(self):
        rows = [case("Z", 100), case("M", 100), case("A", 100)]
        allocate_calls(rows, call_capacity=1)
        assert [r["case_id"] for r in rows if r["action"] == "call"] == ["A"]

    def test_call_reason(self):
        rows = [case("A", 300), case("B", 200, action="call", values={"call": 9.0, "email": 5.0})]
        allocate_calls(rows, call_capacity=2)
        reasons = {r["case_id"]: r["call_reason"] for r in rows}
        assert reasons == {"A": "no_response", "B": "best_channel"}

    def test_over_capacity_call_falls_back_to_best_other_channel(self):
        rows = [case("A", 300), case("B", 200),
                case("C", 100, action="call", values={"call": 9.0, "sms": 3.0, "email": 4.0, "reminder_letter": -1.0})]
        allocate_calls(rows, call_capacity=2)
        c = next(r for r in rows if r["case_id"] == "C")
        assert (c["action"], c["path"]) == ("email", "call_queue_full")

    def test_over_capacity_with_no_other_channel_waits(self):
        rows = [case("A", 300), case("B", 200), case("C", 100, action="call", values={"call": 9.0, "letter": -2.0})]
        allocate_calls(rows, call_capacity=2)
        c = next(r for r in rows if r["case_id"] == "C")
        assert (c["action"], c["path"]) == ("do_nothing", "call_queue_full")

    def test_non_candidates_untouched_and_reason_defaults(self):
        rows = [case("A", 999, action="hardship_referral", candidate=False), case("B", 10)]
        allocate_calls(rows, call_capacity=5)
        a = rows[0]
        assert a["action"] == "hardship_referral" and a["call_reason"] is None

    def test_never_exceeds_capacity(self):
        rows = [case(f"C{i:03d}", float(i)) for i in range(50)]
        allocate_calls(rows, call_capacity=7)
        assert sum(r["action"] == "call" for r in rows) == 7


# ---------------------------------------------------------------------------------------------- reason wording
def rec(**kw):
    r = {"action": "email", "p_cure": 0.2, "overdue_now": 500.0, "path": "value", "routing_reason": None,
         "routing_category": None, "text_evidence": None, "allowed": ["do_nothing", "email"], "blocked": {},
         "call_reason": None}
    r.update(kw)
    return r


class TestReasonOne:
    def test_hardship_with_quote(self):
        out = _reason_1(rec(action="hardship_referral", routing_reason="Case flagged for hardship (job loss)",
                            routing_category="hardship_case_flag", text_evidence="I lost my job"), ECON)
        assert out == 'Hardship: Case flagged for hardship (job loss); the customer said "I lost my job"'

    def test_hardship_text_only_does_not_repeat_quote(self):
        reason = 'Customer described hardship in the last 90 days: "money is tight"'
        out = _reason_1(rec(action="hardship_referral", routing_reason=reason, routing_category="hardship_text",
                            text_evidence="money is tight"), ECON)
        assert out == f"Hardship: {reason}"

    def test_long_quote_is_cut(self):
        out = _reason_1(rec(action="hardship_referral", routing_reason="Case flagged for hardship",
                            routing_category="hardship_case_flag", text_evidence="x" * 300), ECON)
        assert out.endswith('..."') and len(out) < 200

    def test_specialist(self):
        out = _reason_1(rec(action="specialist_agent", path="human", routing_reason="Open dispute on the case"), ECON)
        assert out == "Needs a person: Open dispute on the case"

    def test_self_cure_wait(self):
        assert _reason_1(rec(action="do_nothing", path="self_cure", p_cure=0.4), ECON).startswith(
            "Likely to pay without contact: self-cure chance 40%")

    def test_call_queue_full_wait(self):
        assert "5,037" not in _reason_1(rec(action="do_nothing", path="call_queue_full"), ECON)
        assert "call slots" in _reason_1(rec(action="do_nothing", path="call_queue_full"), ECON)

    def test_person_no_contact(self):
        out = _reason_1(rec(action="do_nothing", path="human", routing_reason="Customer asked us to stop contacting them"),
                        ECON)
        assert out.startswith("Needs a person, no contact allowed")

    def test_no_channel_allowed_names_the_rule(self):
        out = _reason_1(rec(action="do_nothing", path="not_worth_contact", allowed=["do_nothing"],
                            blocked={"sms": ["Contact cap reached (3/3 contacts in last 7 days)"]}), ECON)
        assert out == "No contact allowed today (Contact cap reached (3/3 contacts in last 7 days)); review again in 7 days"

    def test_not_worth_contact(self):
        out = _reason_1(rec(action="do_nothing", path="not_worth_contact", overdue_now=20.0), ECON)
        assert out.startswith("Not worth a contact: $20 overdue")

    def test_call_reasons(self):
        assert "brought no payment" in _reason_1(rec(action="call", call_reason="no_response"), ECON)
        assert "best channel the customer has allowed" in _reason_1(rec(action="call", call_reason="best_channel"), ECON)

    def test_letter_and_digital(self):
        assert _reason_1(rec(action="reminder_letter"), ECON).startswith("Reminder letter: 80% chance the $500 stays unpaid")
        out = _reason_1(rec(action="sms", path="call_queue_full"), ECON)
        assert out.startswith("SMS payment link (call queue full today): 80% chance")
        assert "12% of contacts at $0.01 each (calls 3% at $2.40)" in out


class TestFormatting:
    def test_pct_and_cad(self):
        assert (_pct(0.001), _pct(0.999), _pct(0.25)) == ("under 1%", "over 99%", "25%")
        assert (_cad(0.001), _cad(2.4)) == ("under 1 cent", "$2.40")

    def test_time_windows(self):
        assert _time_window("call", 10) == "10:00-12:00 local (customer answers most at this time)"
        assert _time_window("call", 22) == "17:00-19:00 local (best answer rate)"     # outside 8-19: peak hour
        assert _time_window("call", None).startswith("17:00-19:00")
        assert _time_window("email", None) == "09:00-12:00 local"
        assert _time_window("reminder_letter", None) == "next mailing day"
        assert _time_window("hardship_referral", None) == "within 1 business day"
        assert _time_window("do_nothing", None) == "review again in 7 days"


# ---------------------------------------------------------------------------------------------- channel economics
def test_channel_economics_measures_response_and_reads_capacity():
    con = duckdb.connect()
    for s in ("gold", "bronze"):
        con.execute(f"CREATE SCHEMA {s}")
    # case K1: an SMS on day 1 followed by a link payment on day 3 (responded); a call on day 10 with no payment
    # case K2: an SMS on day 1 with no payment within 7 days (the payment on day 20 is too late)
    con.execute("""CREATE TABLE gold.contact_timeline AS SELECT * FROM (VALUES
        ('c1', 'K1', TIMESTAMP '2026-09-01 10:00', 'sms'),
        ('c2', 'K1', TIMESTAMP '2026-09-03 10:00', 'sms'),
        ('c3', 'K1', TIMESTAMP '2026-09-10 10:00', 'call'),
        ('c4', 'K2', TIMESTAMP '2026-09-01 10:00', 'sms'),
        ('c5', 'K2', TIMESTAMP '2026-09-20 10:00', 'ivr')) t(contact_id, case_id, contact_ts_utc, channel)""")
    con.execute("""CREATE TABLE bronze.contact_history AS SELECT * FROM (VALUES
        ('c1', 'outbound', false, false, false, false),
        ('c2', 'inbound',  false, true,  false, false),
        ('c3', 'outbound', false, false, false, false),
        ('c4', 'outbound', false, false, false, false),
        ('c5', 'inbound',  false, false, false, true)) t(contact_id, direction, payment_taken_flag, link_payment_flag,
                                                         app_payment_after_contact_flag, ivr_self_serve_payment_flag)""")
    con.execute("""CREATE TABLE bronze.channel_capacity AS SELECT * FROM (VALUES
        (DATE '2026-09-27', 'call', 9999, 9.99, false),
        (DATE '2026-09-28', 'call', 3000, 2.40, false), (DATE '2026-09-28', 'call', 2000, 2.40, false),
        (DATE '2026-09-28', 'sms', 40000, 0.01, false), (DATE '2026-09-28', 'email', 50, 0.001, true)
    ) t(date, channel, capacity_units, unit_cost_cad, outage_flag)""")
    e = channel_economics(con, "2026-09-28")
    assert e["sms"]["contacts"] == 2 and e["sms"]["rate"] == 0.5        # 1 of 2 outbound SMS followed by a payment
    assert e["call"]["contacts"] == 1 and e["call"]["rate"] == 0.0
    assert e["call"]["capacity"] == 5000 and e["call"]["unit_cost"] == 2.40   # latest date only, bands summed
    assert e["email"]["capacity"] == 0                                    # outage rows are not capacity
    assert e["specialist_agent"]["unit_cost"] == pytest.approx(2.40 * 3)


# ---------------------------------------------------------------------------------------------- policy timing
class TestPolicyTiming:
    row = {"permitted_call_start_local": "08:00", "permitted_call_end_local": "21:00"}

    def test_hours(self):
        assert check_permitted_hours(self.row, None) == []
        assert check_permitted_hours(self.row, dt.datetime(2026, 9, 29, 12)) == []
        assert check_permitted_hours(self.row, dt.datetime(2026, 9, 29, 22))[0][0] == "call"
        assert check_permitted_hours(self.row, dt.datetime(2026, 9, 29, 7))[0][0] == "call"

    def test_unreadable_hours_never_block(self):
        bad = {"permitted_call_start_local": "eight", "permitted_call_end_local": "21:00"}
        assert check_permitted_hours(bad, dt.datetime(2026, 9, 29, 3)) == []
        assert check_permitted_hours({}, dt.datetime(2026, 9, 29, 3)) == []

    def test_holiday_and_sunday(self):
        assert check_stat_holidays({}, dt.datetime(2026, 9, 30, 12))[0][0] == "call"     # Truth and Reconciliation
        assert check_stat_holidays({}, dt.datetime(2026, 9, 27, 12))                      # a Sunday
        assert check_stat_holidays({"sunday_contact_permitted": True}, dt.datetime(2026, 9, 27, 12)) == []
        assert check_stat_holidays({}, dt.datetime(2026, 9, 29, 12)) == []


def test_hardship_value_helpers():
    assert _truthy(True) and not _truthy(None) and not _truthy(float("nan")) and not _truthy(pd.NA)
    assert _num(None) == 0.0 and _num(float("nan"), 7.0) == 7.0 and _num("x", 1.0) == 1.0 and _num("2") == 2.0


# ---------------------------------------------------------------------------------------------- model fitting
def synthetic(n, seed):
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({c: rng.normal(size=n) for c in M.FEATURE_COLUMNS})
    df["overdue_now"] = rng.uniform(0, 3000, n)
    p = 1 / (1 + np.exp(-(1.5 - df["overdue_now"] / 800 + df["acct_months_min_paid_6m"])))
    df["label"] = (rng.uniform(size=n) < p).astype(int)
    df["case_id"] = [f"S{i}" for i in range(n)]
    return df


def test_fit_is_repeatable_and_respects_monotone_constraints():
    train, valid = synthetic(3000, 1), synthetic(1000, 2)
    cols = list(M.FEATURE_COLUMNS)
    b1 = M._fit(train, valid, cols, "self_cure_30d")
    b2 = M._fit(train, valid, cols, "self_cure_30d")
    probe = valid.head(200)
    assert np.array_equal(b1.predict(M._matrix(probe, cols)), b2.predict(M._matrix(probe, cols)))   # K1
    # self-cure is constrained to fall as overdue rises: sweep overdue for one case, all else fixed
    sweep = pd.concat([probe.iloc[[0]]] * 30, ignore_index=True)
    sweep["overdue_now"] = np.linspace(0, 3000, 30)
    p = b1.predict(M._matrix(sweep, cols))
    assert np.all(np.diff(p) <= 1e-12)


def test_predict_applies_the_calibrator():
    train, valid = synthetic(2000, 3), synthetic(800, 4)
    cols = list(M.FEATURE_COLUMNS)
    booster = M._fit(train, valid, cols, "self_cure_30d")
    raw = booster.predict(M._matrix(valid, cols))
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(raw, valid["label"])
    out = M.predict({"booster": booster, "calibrator": iso, "feature_cols": cols}, valid)
    assert np.allclose(out, iso.predict(raw)) and out.min() >= 0 and out.max() <= 1


# ---------------------------------------------------------------------------------------------- whole pipeline
def test_build_recommendations_end_to_end_on_a_synthetic_book(tmp_path, monkeypatch):
    """Score, route and rank a small synthetic open book with tiny trained models; check the hackathon rules."""
    import pickle

    from ontrack.l3_features.structured.features import INFO_COLUMNS, KEYS
    from ontrack.l4_nba.hardship import route_cases
    from ontrack.l4_nba.ranker import build_recommendations

    n, snap = 60, "2026-09-28"
    rng = np.random.default_rng(0)
    con = duckdb.connect()
    for s in ("gold", "bronze", "features"):
        con.execute(f"CREATE SCHEMA {s}")
    f = synthetic(n, 5).drop(columns=["label"])
    f["case_id"] = [f"CS-{i:03d}" for i in range(n)]
    f["golden_id"] = [f"G-{i:03d}" for i in range(n)]
    f["crm_customer_id"] = [f"C-{i:03d}" for i in range(n)]
    f["as_of_date"] = pd.Timestamp(snap)
    f["best_rpc_hour"] = 17
    f["has_payroll"] = 0
    f["salary_gap_months_3m"] = 0
    f["salary_drop_pct"] = np.nan
    f["dispute_raised_any"] = 0
    feats = f[KEYS + M.FEATURE_COLUMNS + INFO_COLUMNS]
    con.execute("CREATE TABLE features.case_features AS SELECT * FROM feats")

    flag = lambda k: [i % k == 0 for i in range(n)]  # noqa: E731
    cases = pd.DataFrame({
        "case_id": f["case_id"], "golden_id": f["golden_id"], "hardship_flag": flag(4), "hardship_reason": "job_loss",
        "dispute_flag": flag(9), "complaint_flag": False, "vulnerable_customer_flag": False,
        "insolvency_hold_flag": False, "deceased_hold_flag": False, "third_party_rep_flag": False,
        "cease_contact_flag": flag(11), "contacts_last_7d": 0, "contact_cap_7d": 7,
        "current_bucket_derived": "31-60", "current_dpd": rng.integers(1, 181, n)})
    con.execute("CREATE TABLE gold.case_360 AS SELECT * FROM cases")
    cust = pd.DataFrame({
        "golden_id": f["golden_id"], "consent_call": True, "consent_sms": flag(2), "consent_email": True,
        "consent_push": False, "consent_autodialer": False, "internal_do_not_call_flag": False,
        "cease_communication_flag": False, "insolvency_flag": False, "deceased_flag": False,
        "third_party_hold_flag": False, "vulnerability_flag": flag(13), "preferred_language": "EN"})
    con.execute("CREATE TABLE gold.c360_customer AS SELECT * FROM cust")
    con.execute("""CREATE TABLE gold.contact_timeline AS SELECT 'k' || i AS contact_id, 'CS-001' AS case_id,
                   TIMESTAMP '2026-06-01' + i * INTERVAL 1 DAY AS contact_ts_utc,
                   CASE WHEN i % 2 = 0 THEN 'sms' ELSE 'call' END AS channel FROM range(20) t(i)""")
    con.execute("""CREATE TABLE bronze.contact_history AS SELECT contact_id, 'outbound' AS direction,
                   (row_number() OVER () % 5 = 0) AS payment_taken_flag, false AS link_payment_flag,
                   false AS app_payment_after_contact_flag, false AS ivr_self_serve_payment_flag
                   FROM gold.contact_timeline""")
    con.execute("""CREATE TABLE bronze.channel_capacity AS SELECT * FROM (VALUES
        (DATE '2026-09-28', 'call', 3, 2.40, false), (DATE '2026-09-28', 'sms', 1000, 0.01, false),
        (DATE '2026-09-28', 'email', 1000, 0.001, false), (DATE '2026-09-28', 'letter', 100, 1.10, false))
        t(date, channel, capacity_units, unit_cost_cad, outage_flag)""")

    monkeypatch.setattr(M, "MODEL_DIR", tmp_path)
    cols = list(M.FEATURE_COLUMNS)
    for name in ("self_cure_30d", "payment_7d"):
        tr, va = synthetic(1500, 11), synthetic(500, 12)
        booster = M._fit(tr, va, cols, name)
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(
            booster.predict(M._matrix(va, cols)), va["label"])
        with open(tmp_path / f"{name}.pkl", "wb") as fh:
            pickle.dump({"booster": booster, "calibrator": iso, "feature_cols": cols,
                         "meta": {"model_version": "test"}}, fh)

    routed = route_cases(con, snap)
    rec = build_recommendations(con, routed, snap).set_index("case_id")
    assert len(rec) == n
    hardship = set(cases.loc[cases["hardship_flag"], "case_id"])
    assert set(rec.index[rec["action"] == "hardship_referral"]) == hardship        # hardship only, all of it
    assert (rec["action"] == "call").sum() <= 3                                     # call capacity
    for cid, r in rec.iterrows():
        assert r["action"] not in str(r["blocked_actions"] or "").split(", ")       # never a blocked action
        assert r["channel"] and r["reason_1"] and r["reason_2"] and r["reason_3"]  # channel and 3 reasons
    cease = cases.loc[cases["cease_contact_flag"], "case_id"]
    assert not rec.loc[cease, "action"].isin(["call", "sms", "email", "push_notification", "reminder_letter",
                                               "specialist_agent"]).any()          # cease: no outbound at all
    assert rec["needs_human_review"][list(hardship)].all()
    assert sorted(rec["model_risk_rank"]) == list(range(1, n + 1))
    both = rec["p_roll_forward"].notna() & rec["p_charge_off_risk"].notna()
    assert not both.any() and (rec["p_roll_forward"].notna() | rec["p_charge_off_risk"].notna()).all()
