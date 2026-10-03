"""Data steward loop: decisions are validated, logged, and fed back into identity resolution (owner: P1)."""
import duckdb
import pandas as pd
import pytest

from ontrack.app import common
from ontrack.l1_factory import probabilistic


@pytest.fixture()
def steward_db(tmp_path, monkeypatch):
    path = tmp_path / "decisions.duckdb"
    monkeypatch.setattr(common, "DECISIONS_PATH", path)
    monkeypatch.setattr(probabilistic, "STEWARD_DB", path)
    return path


def queue_con(rows):
    con = duckdb.connect()
    con.execute("CREATE SCHEMA gold; CREATE SCHEMA silver")
    q = pd.DataFrame(rows, columns=["source_system", "source_key", "candidate_crm_customer_id", "match_probability"])
    q["steward_status"] = "pending"
    con.register("q", q)
    con.execute("CREATE TABLE gold.match_review_queue AS SELECT * FROM q")
    con.execute("CREATE TABLE silver.splink_edges (a VARCHAR, b VARCHAR, conf DOUBLE, method VARCHAR)")
    return con


def test_reason_code_must_match_the_decision(steward_db):
    with pytest.raises(ValueError):
        common.record_steward_decision("card", "CX1", "AAA-1", 0.9, "approved", "different_person")
    with pytest.raises(ValueError):
        common.record_steward_decision("card", "CX1", "AAA-1", 0.9, "maybe", "other")


def test_latest_decision_wins_and_feeds_the_next_build(steward_db):
    common.record_steward_decision("loan", "B1", "AAA-1", 0.93, "rejected", "insufficient_evidence")
    common.record_steward_decision("loan", "B1", "AAA-1", 0.93, "approved", "same_person_evidence")  # changed mind
    common.record_steward_decision("card", "CX2", "BBB-2", 0.85, "rejected", "different_person")
    con = queue_con([("loan", "B1", "AAA-1", 0.93), ("card", "CX2", "BBB-2", 0.85), ("cif", "0000000003", "CCC-3", 0.81)])

    probabilistic.apply_steward_decisions(con)

    status = dict(con.execute("SELECT source_key, steward_status FROM gold.match_review_queue").fetchall())
    assert status == {"B1": "approved", "CX2": "rejected", "0000000003": "pending"}
    # Only the approved pair becomes a link, as a human-verified edge.
    assert con.execute("SELECT * FROM silver.splink_edges").fetchall() == [
        ("crm:AAA-1", "loan:B1", probabilistic.STEWARD_CONF, "steward_approved")]


def test_no_decision_file_means_nothing_changes(steward_db):
    con = queue_con([("loan", "B1", "AAA-1", 0.93)])
    probabilistic.apply_steward_decisions(con)
    assert con.execute("SELECT steward_status FROM gold.match_review_queue").fetchone()[0] == "pending"
    assert con.execute("SELECT count(*) FROM silver.splink_edges").fetchone()[0] == 0
