"""Layer 2 guards: SQL guard, scope guard, certified-metric templates (owner: P2).

No dataset or LLM needed: the SQL guard runs on a hand-made allow-list, templates are checked by parsing.
"""
import pytest
import sqlglot

from ontrack.l2_ask import metrics, scope, understand
from ontrack.l2_ask.redteam import RED_TEAM
from ontrack.l2_ask.sql_guard import GuardError, Schema, check

SCHEMA = Schema({
    "bronze.collections_cases": {"case_id", "queue", "current_dpd", "outcome", "province_code", "hardship_flag"},
    "bronze.customers": {"crm_customer_id", "first_name", "primary_phone_e164", "gender_code", "citizenship_status",
                         "fsa", "age", "consent_email", "province_code"},
    "bronze.promises_to_pay": {"ptp_id", "ptp_status", "ptp_due_date"},
})


# ---- SQL guard (check 3: after SQL) --------------------------------------------------------------------------

@pytest.mark.parametrize("sql", [
    "DELETE FROM bronze.collections_cases",
    "UPDATE bronze.collections_cases SET queue = 'x'",
    "DROP TABLE bronze.collections_cases",
    "CREATE TABLE x AS SELECT 1",
    "SELECT 1; SELECT 2",
    "SELECT * FROM read_csv('secret.csv')",
    "SELECT gender_code, count(*) FROM bronze.customers GROUP BY 1",
    "SELECT citizenship_status FROM bronze.customers",
    "SELECT first_name, primary_phone_e164 FROM bronze.customers",
    "SELECT fsa, count(*) FROM bronze.customers GROUP BY 1",
    "SELECT age FROM bronze.customers",
    "SELECT * FROM bronze.customers",
    "SELECT * FROM bronze.agents",
    "SELECT nope FROM bronze.collections_cases",
])
def test_guard_blocks(sql):
    with pytest.raises(GuardError):
        check(sql, SCHEMA)


def test_guard_allows_and_caps_rows():
    out = check("SELECT queue, avg(current_dpd) AS d FROM bronze.collections_cases WHERE outcome IS NULL "
                "GROUP BY 1 LIMIT 5000", SCHEMA)
    tree = sqlglot.parse_one(out, read="duckdb")
    assert int(tree.args["limit"].expression.name) == 1000
    assert "HAVING" in out.upper()                     # minimum group size added


def test_guard_allows_harmless_columns_with_pii_like_names():
    check("SELECT count(*) FROM bronze.customers WHERE consent_email", SCHEMA, min_group=0)


def test_guard_allows_ctes_and_subqueries():
    check("WITH t AS (SELECT case_id, current_dpd AS d FROM bronze.collections_cases) SELECT avg(d) FROM t", SCHEMA)


# ---- Scope guard (check 1: before SQL) -----------------------------------------------------------------------

@pytest.mark.parametrize("q,should_refuse", RED_TEAM)
def test_red_team(q, should_refuse):
    assert scope.route(q).refused == should_refuse, q


@pytest.mark.parametrize("q", [
    "Can we sue a customer who missed two payments?",                 # policy question (BQ-020 style)
    "Can we send a customer to a collection agency?",
    "What does our policy say about legal action?",
    "What is the RPC rate by agent site?",                            # 'by agent' is not 'by age'
    "How many cases are over 90 days past due?",
    "Is CASL consent needed for a reminder by email?",
])
def test_policy_and_ordinary_questions_not_refused(q):
    assert not scope.route(q).refused, q


# ---- Certified metrics and 'understood as' --------------------------------------------------------------------

@pytest.mark.parametrize("metric_id", sorted(metrics.METRICS))
def test_every_template_parses(metric_id):
    m = metrics.METRICS[metric_id]
    sql = metrics.certified_sql(metric_id, "2026-09-01", "2026-09-27", next(iter(m.dims), None))
    assert sqlglot.parse_one(sql, read="duckdb") is not None


def test_understood_as_resolves_relative_dates_to_snapshot():
    u = understand.understand("What was the promise-kept rate last month?")
    assert (u.metric, u.start, u.end) == ("promise_kept_rate", "2026-08-01", "2026-08-31")


def test_understood_as_window_and_grouping():
    u = understand.understand("What was the broken-promise rate by agent site for promises due in "
                              "July-September 2026?")
    assert (u.metric, u.group_by, u.start, u.end) == ("broken_promise_rate", "site", "2026-07-01", "2026-09-28")
    assert not u.unresolved


# ---- R5: roll-forward questions route to gold.nba_recommendation, historical roll-rate questions don't --------

def test_roll_forward_routing():
    import re
    from ontrack.l2_ask.nba_questions import ROLL_FORWARD_RE
    assert re.search(ROLL_FORWARD_RE, "which open cases are most likely to roll to a worse bucket in the next 30 days?")
    assert re.search(ROLL_FORWARD_RE, "show the top 5 cases at highest risk of rolling forward")
    assert not re.search(ROLL_FORWARD_RE, "of accounts that were 1-30 days past due at the end of march 2026, what "
                                          "share had rolled to a worse bucket by the end of june 2026, by product?")
    assert not re.search(ROLL_FORWARD_RE, "roll rate from 1-30 to 31-60 this month by product?")


def test_charge_off_routing():
    import re
    from ontrack.l2_ask.nba_questions import CHARGE_OFF_RE, chargeoff_sql, rollforward_sql
    assert re.search(CHARGE_OFF_RE, "which open cases are closest to charge-off?")
    assert re.search(CHARGE_OFF_RE, "show the top 10 cases most likely to be charged off")
    assert not re.search(CHARGE_OFF_RE, "how many card and loan accounts were charged off in the 12 months to 28 "
                                        "september 2026, and for how much, by product?")      # BQ-015: history
    for sql in (chargeoff_sql(5), rollforward_sql("p_roll_forward", 5)):
        assert "NULLS LAST" in sql and "IS NOT NULL" in sql


def test_risk_list_tie_break():
    from ontrack.l2_ask.nba_questions import chargeoff_sql, rollforward_sql
    with_rank = rollforward_sql("p_roll_forward", 5, ["model_risk_rank", "overdue_now"])
    assert "ORDER BY r.p_roll_forward DESC NULLS LAST, r.model_risk_rank ASC, r.case_id" in with_rank
    before_k7 = chargeoff_sql(5, ["overdue_now"])
    assert "ORDER BY r.p_charge_off_risk DESC NULLS LAST, r.overdue_now DESC NULLS LAST, r.case_id" in before_k7
