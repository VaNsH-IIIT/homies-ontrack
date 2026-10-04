"""G24: BQ-006-style "disputes raised between <dates>" answered deterministically (owner: P2). No LLM."""
import csv
from datetime import date
from pathlib import Path

import duckdb
import pytest

from ontrack import config
from ontrack.l2_ask import dispute_window as D
from ontrack.l2_ask import redteam, rehearsal, rehearsal_hard

BQ006 = "How many late-fee disputes were raised between 15 and 22 September 2026, compared with the 8 days before?"


@pytest.mark.parametrize("q, start, end, n, qual", [
    (BQ006, date(2026, 9, 15), date(2026, 9, 22), 8, "late-fee"),
    ("How many disputes were raised from 15 to 22 Sep 2026 compared to the week before?",
     date(2026, 9, 15), date(2026, 9, 22), 7, ""),
    ("How many billing disputes were raised between 1 and 10 September?", date(2026, 9, 1), date(2026, 9, 10), None,
     "billing"),
    ("How many disputes were raised between 28 August and 3 September 2026, versus the same period before?",
     date(2026, 8, 28), date(2026, 9, 3), 7, ""),
    ("how many disputes were raised on 15–22 September 2026 vs the eight days before",
     date(2026, 9, 15), date(2026, 9, 22), 8, ""),
])
def test_parse(q, start, end, n, qual):
    assert D.parse(q) == {"start": start, "end": end, "n": n, "qualifier": qual}


@pytest.mark.parametrize("q", [
    "How many open cases have an open dispute?",                                    # case-level: not "raised"
    "How many late-fee disputes were raised last week by agent site?",              # richer: the agent does it
    "How many disputes were raised between 22 and 15 September 2026?",              # end before start
    "Why did disputes spike between 15 and 22 September 2026?",
])
def test_other_questions_are_left_alone(q):
    assert D.parse(q) is None


def test_sql_matches_the_dev_gold_shape():
    """Same definition as the release's dev gold for BQ-006: contacts with dispute_raised_flag by contact_ts_local."""
    con = duckdb.connect()
    con.execute("CREATE SCHEMA bronze")
    con.execute("""CREATE TABLE bronze.contact_history AS SELECT * FROM (VALUES
        (TIMESTAMP '2026-09-06 23:59:00', true), (TIMESTAMP '2026-09-07 00:00:00', true),
        (TIMESTAMP '2026-09-14 23:00:00', true), (TIMESTAMP '2026-09-15 08:00:00', true),
        (TIMESTAMP '2026-09-22 23:59:59', true), (TIMESTAMP '2026-09-23 00:00:00', true),
        (TIMESTAMP '2026-09-16 10:00:00', false)) t(contact_ts_local, dispute_raised_flag)""")
    sql, cur, prev = D.sql(D.parse(BQ006))
    assert (cur, prev) == ("15-22 Sep", "7-14 Sep")
    assert con.execute(sql).fetchall() == [("15-22 Sep", 2), ("7-14 Sep", 2)]       # gold: ORDER BY 1


def test_guardrail_only_bq006_takes_the_route():
    qs = [d["q"] for d in rehearsal.REHEARSAL + rehearsal_hard.HARD + rehearsal_hard.L1SET]
    root = Path(__file__).parent / "fixtures" / "rehearsal"
    for name in ("c360_questions.csv", "live_questions.csv"):
        qs += [r["question_text"] for r in csv.DictReader(open(root / name, encoding="utf-8"))]
    qs += [q for q, _ in redteam.RED_TEAM]
    assert [q for q in qs if D.parse(q)] == []
    path = config.DATA_DIR / "data" / "benchmark_questions.csv"
    if path.exists():
        rel = {r["question_id"]: r["question_text"] for r in csv.DictReader(open(path, encoding="utf-8"))}
        assert [i for i, q in rel.items() if D.parse(q)] == ["BQ-006"]
