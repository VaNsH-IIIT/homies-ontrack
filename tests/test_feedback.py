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


# ---- K20 (tests by P3): the remaining branches ----

def test_not_followed_and_unknown_agent_actions(con, tmp_path):
    con.execute("""INSERT INTO gold.case_360 VALUES
        ('C5', 'G5', DATE '2026-06-01', 'sms_payment_link', false, false, NULL, false, NULL, NULL, 'charged_off'),
        ('C6', 'G6', DATE '2026-06-01', 'sms_payment_link', NULL, NULL, NULL, true, DATE '2026-06-05', 4, 'cured')""")
    feedback.build(con, SNAPSHOT, tmp_path / "none.duckdb")
    r = rows(con)
    assert r["C5"][1] == "not_followed" and r["C5"][4] is False
    assert r["C6"][1] == "unknown" and r["C6"][4] is True


def test_unreadable_decision_log_is_skipped_not_fatal(con, tmp_path, capsys):
    bad = tmp_path / "decisions.duckdb"
    bad.write_bytes(b"not a duckdb file")
    counts = feedback.build(con, SNAPSHOT, bad)
    assert counts == {"bank_history": 3}                       # history still written
    assert "decision log not read" in capsys.readouterr().out


def test_decision_file_without_a_log_table(con, tmp_path):
    db = tmp_path / "decisions.duckdb"
    d = duckdb.connect(str(db))
    d.execute("CREATE TABLE steward_log (x INTEGER)")          # the app wrote only steward decisions so far
    d.close()
    assert feedback.build(con, SNAPSHOT, db) == {"bank_history": 3}
    assert con.execute("SELECT count(*) FROM duckdb_databases() WHERE database_name = 'dec'").fetchone()[0] == 0


def test_cure_before_the_decision_does_not_count(con, tmp_path):
    db = tmp_path / "decisions.duckdb"
    d = duckdb.connect(str(db))
    d.execute("""CREATE TABLE decision_log (decision_id VARCHAR, case_id VARCHAR, golden_id VARCHAR, agent_id VARCHAR,
                 recommended_action VARCHAR, agent_action VARCHAR, final_action VARCHAR, reason_code VARCHAR,
                 note VARCHAR, model_version VARCHAR, ts TIMESTAMP)""")
    # C1 cured on 13 Jun; a decision on 13 Jun (same day) or later did not cause it
    d.execute("INSERT INTO decision_log VALUES ('d1', 'C1', 'G1', 'a1', 'call', 'accept', 'call', 'agrees', '', 'v1', "
              "TIMESTAMP '2026-06-13 09:00')")
    d.close()
    feedback.build(con, SNAPSHOT, db)
    assert con.execute("SELECT cured_30d FROM features.decision_feedback WHERE source = 'ontrack'").fetchone()[0] is False


def test_main_prints_counts_per_source(tmp_path, monkeypatch, capsys):
    path = tmp_path / "fb.duckdb"
    c = duckdb.connect(str(path))
    c.execute("CREATE SCHEMA gold")
    c.execute("""CREATE TABLE gold.case_360 AS SELECT 'C1' AS case_id, 'G1' AS golden_id, DATE '2026-06-01' AS case_open_date,
                 'call' AS nba_recommendation_last, true AS nba_accepted_flag, false AS human_override_flag,
                 NULL::VARCHAR AS override_reason, true AS cure_flag, DATE '2026-06-05' AS cure_date, 4 AS days_to_cure,
                 'cured' AS outcome""")
    c.close()
    monkeypatch.setattr(feedback, "connect", lambda: duckdb.connect(str(path)))
    monkeypatch.setattr(feedback, "DECISIONS_DB", tmp_path / "none.duckdb")
    feedback.main()
    out = capsys.readouterr().out
    assert "bank_history          1 decisions,         1 with a known 30-day outcome" in out
    assert "cured within 30 days: 1.0" in out
