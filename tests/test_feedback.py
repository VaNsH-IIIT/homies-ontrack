"""Feedback loop: decisions joined to later outcomes become labels (owner: P1)."""
from datetime import date, datetime

import duckdb
import pytest

from ontrack import feedback

SNAPSHOT = "2026-09-28"


@pytest.fixture()
def con():
    c = duckdb.connect()
    c.execute("CREATE SCHEMA gold")
    c.execute("""CREATE TABLE gold.case_360 (case_id VARCHAR, golden_id VARCHAR, case_open_date DATE,
                 nba_recommendation_last VARCHAR, nba_accepted_flag BOOLEAN, human_override_flag BOOLEAN,
                 override_reason VARCHAR, cure_flag BOOLEAN, cure_date DATE, days_to_cure INTEGER, outcome VARCHAR)""")
    c.executemany("INSERT INTO gold.case_360 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [
        # accepted, cured on day 12
        ("C1", "G1", date(2026, 6, 1), "sms_payment_link", True, False, None, True, date(2026, 6, 13), 12, "cured"),
        # overridden with a reason, cured on day 45: not within 30 days
        ("C2", "G2", date(2026, 6, 1), "call_evening", False, True, "Hardship disclosed - paused calls", True, date(2026, 7, 16), 45, "cured"),
        # opened 10 days before the snapshot: too early to know
        ("C3", "G3", date(2026, 9, 18), "call_daytime", True, False, None, None, None, None, None),
        # no recommendation: not a decision
        ("C4", "G4", date(2026, 6, 1), None, None, None, None, False, None, None, None),
    ])
    yield c
    c.close()


def rows(con):
    return {r[0]: r[1:] for r in con.execute(
        "SELECT case_id, source, agent_action, reason, label_status, cured_30d FROM features.decision_feedback").fetchall()}


def test_history_becomes_labelled_decisions(con, tmp_path):
    counts = feedback.build(con, SNAPSHOT, tmp_path / "none.duckdb")
    r = rows(con)
    assert counts == {"bank_history": 3}
    assert r["C1"] == ("bank_history", "accept", None, "known", True)
    assert r["C2"] == ("bank_history", "override", "Hardship disclosed - paused calls", "known", False)  # cured too late
    assert r["C3"][3:] == ("pending", None)  # outcome window not over yet
    assert "C4" not in r


def test_ontrack_decisions_wait_for_their_outcome(con, tmp_path):
    db = tmp_path / "decisions.duckdb"
    d = duckdb.connect(str(db))
    d.execute("""CREATE TABLE decision_log (decision_id VARCHAR, case_id VARCHAR, golden_id VARCHAR, agent_id VARCHAR,
                 recommended_action VARCHAR, agent_action VARCHAR, final_action VARCHAR, reason_code VARCHAR,
                 note VARCHAR, model_version VARCHAR, ts TIMESTAMP)""")
    d.executemany("INSERT INTO decision_log VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [
        ("d1", "C1", "G1", "a1", "call", "edit", "sms", "customer_requested_other_channel", "", "v1", datetime(2026, 6, 2, 10)),
        ("d2", "C3", "G3", "a1", "sms", "accept", "sms", "agrees", "", "v1", datetime(2026, 9, 20, 10)),
    ])
    d.close()
    counts = feedback.build(con, SNAPSHOT, db)
    got = {r[0]: r[1:] for r in con.execute("""SELECT case_id, agent_action, label_status, cured_30d
                                               FROM features.decision_feedback WHERE source = 'ontrack'""").fetchall()}
    assert counts["ontrack"] == 2
    assert got["C1"] == ("edit", "known", True)       # cured 11 days after the decision
    assert got["C3"] == ("accept", "pending", None)   # decided 8 days before the snapshot


def test_summary_shares_add_up(con, tmp_path):
    feedback.build(con, SNAPSHOT, tmp_path / "none.duckdb")
    total = con.execute("""SELECT sum(share_of_recommendation) FROM features.override_summary
                           WHERE source = 'bank_history' AND recommended_action = 'call_evening'""").fetchone()[0]
    assert total == pytest.approx(1.0)
