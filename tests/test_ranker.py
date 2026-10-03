"""Tests for the ranker's decision rules and reason wording (owner: P3)."""
import datetime as dt

import numpy as np

from ontrack.l4_nba.ranker import (
    SELF_CURE_THRESHOLD,
    _fact,
    _why,
    choose_action,
    contact_values,
    counterfactual,
    driver_reasons,
    wants_call,
)

ECON = {
    "call": {"rate": 0.03, "unit_cost": 2.40, "capacity": 10},
    "sms": {"rate": 0.12, "unit_cost": 0.01, "capacity": 100},
    "email": {"rate": 0.12, "unit_cost": 0.001, "capacity": 100},
    "push_notification": {"rate": 0.08, "unit_cost": 0.001, "capacity": 100},
    "reminder_letter": {"rate": 0.02, "unit_cost": 1.10, "capacity": 100},
    "specialist_agent": {"rate": 0.03, "unit_cost": 7.20, "capacity": 0},
}
ALL = ["do_nothing", "call", "sms", "email", "push_notification", "reminder_letter", "specialist_agent"]


def row(**kw):
    r = {"hardship_flag": False, "needs_human_review": False, "p_cure": 0.1, "contacts_30d": 0,
         "payments_30d": 0, "link_clicks_30d": 0}
    r.update(kw)
    return r


class TestChooseAction:
    def test_hardship_gets_referral(self):
        assert choose_action(row(hardship_flag=True, needs_human_review=True), ALL, {})[0] == "hardship_referral"

    def test_non_hardship_never_gets_referral(self):
        # issue #7: hardship_referral (cost 0) used to win for 92% of cases
        values = contact_values(500, 0.1, 1.0, ALL, ECON)
        action, _ = choose_action(row(), ALL + ["hardship_referral"], values)
        assert action != "hardship_referral"

    def test_human_review_goes_to_specialist_or_waits(self):
        assert choose_action(row(needs_human_review=True), ALL, {})[0] == "specialist_agent"
        assert choose_action(row(needs_human_review=True), ["do_nothing"], {})[0] == "do_nothing"

    def test_likely_self_cure_waits(self):
        values = contact_values(500, SELF_CURE_THRESHOLD, 1.0, ALL, ECON)
        assert choose_action(row(p_cure=SELF_CURE_THRESHOLD), ALL, values) == ("do_nothing", "self_cure")

    def test_best_value_channel_wins(self):
        values = contact_values(500, 0.1, 1.0, ALL, ECON)
        assert choose_action(row(), ALL, values) == ("email", "value")

    def test_tiny_balance_not_worth_a_letter(self):
        values = contact_values(5, 0.1, 1.0, ["do_nothing", "reminder_letter"], ECON)
        assert choose_action(row(), ["do_nothing", "reminder_letter"], values) == ("do_nothing", "not_worth_contact")


class TestCalls:
    def test_no_response_makes_a_call_candidate(self):
        r = row(contacts_30d=3, path="value", action="email")
        assert wants_call(r, ALL, contact_values(500, 0.1, 1.0, ALL, ECON))

    def test_responsive_customer_is_not_called(self):
        r = row(contacts_30d=3, link_clicks_30d=1, path="value", action="email")
        assert not wants_call(r, ALL, contact_values(500, 0.1, 1.0, ALL, ECON))

    def test_call_blocked_means_no_call(self):
        r = row(contacts_30d=3, path="value", action="email")
        assert not wants_call(r, ["do_nothing", "email"], {})


class TestReasons:
    def test_whole_numbers(self):
        assert _fact("contacts_total", 2.0) == "2 contacts on this case so far"
        assert _fact("days_since_last_payment", 999) == "No payment on this case yet"

    def test_why_never_contradicts_the_value(self):
        # v1 said "Income up 16%: less money coming in"
        assert _why("salary_drop_pct", up=False, v=0.16) == "points away from paying on its own"
        assert _why("salary_drop_pct", up=False, v=-0.4) == "less money coming in"

    def test_driver_reasons_skip_hidden_and_missing(self):
        cols = ["bureau_age_days", "bureau_score", "overdue_now"]
        out = driver_reasons(np.array([5.0, -1.0, 0.5]), {"bureau_age_days": 10, "bureau_score": None,
                                                          "overdue_now": 120.0}, cols)
        assert [f for f, _, _ in out] == ["overdue_now"]

    def test_counterfactuals(self):
        d = dt.date(2026, 9, 28)
        assert "2026-10-05" in counterfactual("do_nothing", [], 0.4, d)
        drivers = [("days_since_last_payment", "x", False)]
        assert "a payment arrives" in counterfactual("email", drivers, 0.1, d)
