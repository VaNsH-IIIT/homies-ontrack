"""Can people work the human queue? (K25) Capacity maths on a hand-made team and queue (owner: P3). No dataset needed.

Team: 2 hardship specialists x 480 worked minutes on each of 10 weekdays (16 agent-hours a business day); weekend,
absent and other-queue shifts don't count. Handle time 600 s (10 min), occupancy 75% -> 72 first contacts a day
(36 at a 20-minute assessment). Queue: 1,000 hardship referrals, 100 of them opened in the last 28 days
(100 / 28 x 7 / 5 = 5 a business day), plus 3 other human-only cases.
"""
import datetime as dt

import duckdb
import pandas as pd
import pytest

from ontrack.l4_nba.capacity import capacity_sentence, human_capacity

AS_OF = "2026-09-28"


@pytest.fixture()
def con():
    c = duckdb.connect()
    c.execute("CREATE SCHEMA gold; CREATE SCHEMA bronze")
    shifts = []
    for d in pd.date_range("2026-09-14", "2026-09-27"):              # Mon 14 Sep .. Sun 27 Sep
        for agent in ("A1", "A2"):
            shifts.append((d.date(), agent, "hardship_specialist", 480, False))
        shifts.append((d.date(), "A3", "early_stage", 480, False))        # other queue
    shifts.append((dt.date(2026, 9, 15), "A4", "hardship_specialist", 480, True))   # absent
    c.execute("CREATE TABLE bronze.agent_shifts (shift_date DATE, agent_id VARCHAR, queue_assignment VARCHAR, "
              "worked_minutes BIGINT, absence_flag BOOLEAN)")
    c.executemany("INSERT INTO bronze.agent_shifts VALUES (?, ?, ?, ?, ?)", shifts)
    c.execute("""CREATE TABLE bronze.agents AS SELECT * FROM (VALUES
        ('A1', 'hardship_specialist', 'active', 600), ('A2', 'hardship_specialist', 'active', 600),
        ('A9', 'hardship_specialist', 'terminated', 9999), ('A3', 'agent', 'active', 300)
    ) t(agent_id, role, status, avg_handle_time_sec)""")
    rows = [(f"H{i:04d}", "hardship_referral", True, float(1000 - i),
             dt.date(2026, 9, 10) if i < 100 else dt.date(2026, 6, 1)) for i in range(1000)]
    rows += [(f"O{i}", "specialist_agent", True, 50.0, dt.date(2026, 6, 1)) for i in range(3)]
    rows += [("E1", "email", False, 70.0, dt.date(2026, 9, 20))]
    df = pd.DataFrame(rows, columns=["case_id", "action", "needs_human_review", "score", "case_open_date"])
    c.register("df", df)
    c.execute("CREATE TABLE gold.nba_recommendation AS SELECT case_id, action, needs_human_review, score FROM df")
    c.execute("CREATE TABLE gold.case_360 AS SELECT case_id, case_open_date FROM df")
    yield c
    c.close()


def test_team_hours_handle_time_and_inflow(con):
    c = human_capacity(con, AS_OF)
    assert c["hours_per_day"] == pytest.approx(16.0)          # weekdays only; absent and other-queue shifts excluded
    assert c["aht_min"] == pytest.approx(10.0)                # active hardship specialists only
    assert c["inflow_per_day"] == pytest.approx(5.0)          # 100 new in 28 days, per business day
    assert (c["hardship"], c["other_human"]) == (1000, 3)


def test_first_contacts_and_backlog(con):
    c = human_capacity(con, AS_OF)
    m, a = c["measured"], c["assessment"]
    assert m["first_contacts_per_day"] == pytest.approx(72.0) and a["first_contacts_per_day"] == pytest.approx(36.0)
    assert m["new_within_1_day"] and a["new_within_1_day"]
    assert m["days_to_clear_stock"] == pytest.approx(1000 / 67) and a["days_to_clear_stock"] == pytest.approx(1000 / 31)


def test_backlog_is_worked_highest_dollars_first(con):
    c = human_capacity(con, AS_OF)
    reach = 67 * 5                                             # (72 - 5) a day for a week
    assert c["first_week_cases"] == reach
    scores = [1000 - i for i in range(1000)]
    assert c["first_week_dollar_share"] == pytest.approx(sum(scores[:reach]) / sum(scores))


def test_no_spare_capacity_means_no_clear_date(con):
    con.execute("UPDATE bronze.agent_shifts SET worked_minutes = 10 WHERE queue_assignment = 'hardship_specialist'")
    c = human_capacity(con, AS_OF)
    assert not c["measured"]["new_within_1_day"] and c["measured"]["days_to_clear_stock"] is None
    assert c["first_week_cases"] == 0


def test_sentence_states_the_numbers(con):
    s = capacity_sentence(human_capacity(con, AS_OF))
    assert "16 agent-hours" in s and "about 72 first contacts" in s and "about 5 new hardship referrals" in s
    assert "1,000 referrals are a backlog" in s and "15 business days" in s
