"""G23: strict live-question templates over gold (owner: P2). No LLM; only the released-35 check needs the dataset."""
import csv
from pathlib import Path

import duckdb
import pytest

from ontrack import config
from ontrack.l2_ask import live_templates as T
from ontrack.l2_ask import metrics, redteam, rehearsal, rehearsal_hard, understand

LIVE = {   # P1's live set (docs/rehearsal/live_questions.csv): question -> (entity, measure, filters, group)
    "How many golden customers are in the customer 360?": ("customers", "count", [], None),
    "On average, how many products does a golden customer hold?": ("customers", "avg_products", [], None),
    "How many customers have not given consent to be called?": ("customers", "count", ["no call consent"], None),
    "How many golden customers have an open collections case in Quebec?":
        ("customers", "count", ["province", "with an open case"], None),
    "How many open collections cases are there?": ("cases", "count", [], None),
    "How many open cases are in each queue?": ("cases", "count", [], "queue"),
    "Which province has the highest total overdue on open cases?": ("cases", "total_overdue", [], "province"),
    "What share of open cases carry a hardship flag?": ("cases", "share", ["hardship flag"], None),
    "How many open cases have an open dispute?": ("cases", "count", ["dispute"], None),
    "how mnay open cases are there in ontario": ("cases", "count", ["province"], None),
    "Combien de dossiers ouverts ont un indicateur de difficulté financière ?": ("cases", "count", ["hardship flag"],
                                                                                None),
    "How many open cases does OnTrack send to a person first?": ("recs", "count", ["to a person"], None),
    "How many open cases get a hardship referral?": ("recs", "count", ["action"], None),
    "How many calls does OnTrack recommend today?": ("recs", "count", ["action"], None),
    "What is the most common recommended action, and for how many cases?": ("recs", "top_action", [], None),
    "How many open cases show hardship in notes or calls that the case flag missed?":
        ("recs", "count", ["hardship in text, flag missed"], None),
    "How many open cases have a complaint flag?": ("cases", "count", ["complaint"], None),
    "How many customers are flagged as vulnerable, and how does OnTrack treat them?":
        ("customers", "count", ["vulnerable"], None),
}


@pytest.mark.parametrize("q, want", LIVE.items())
def test_live_questions_parse(q, want):
    sp = T.parse(q)
    assert sp is not None, q
    assert (sp.entity, sp.measure, [f[0] for f in sp.filters], sp.group) == want


@pytest.mark.parametrize("q", [
    "How many customers hold three or more products?",                     # unknown words: not ours
    "What share of customers with an open case have consented to SMS?",
    "How many open cases were opened in August 2026 by queue?",
    "How many open cases in Ontario have a promise to pay due next week?",
    "Which queue has the highest cure rate?",
    "What share of open cases?",                                            # a share of nothing
    "How many open cases does each agent have?",
    "How many cases are there?",                                            # open or closed: let the agent ask
])
def test_richer_questions_are_left_to_the_normal_path(q):
    assert T.parse(q) is None


def _certified_first(q: str) -> bool:
    u = understand.understand(q)
    return bool(u.metric) and not u.unresolved and u.metric in metrics.METRICS


def _guarded():
    qs = [d["q"] for d in rehearsal.REHEARSAL + rehearsal_hard.HARD + rehearsal_hard.L1SET]
    qs += [r["question_text"] for r in csv.DictReader(open(Path(__file__).parents[1] / "docs" / "rehearsal" /
                                                           "c360_questions.csv", encoding="utf-8"))]
    qs += [q for q, refuse in redteam.RED_TEAM if not refuse]
    return qs


def test_guardrail_rehearsal_hard_l1_c360_and_redteam_routes_unchanged():
    """A template may only see a question the certified path already answers first (Engine.answer order)."""
    qs = _guarded()
    assert len(qs) >= 21 + 29 + 8 + 15
    changed = [q for q in qs if T.parse(q) and not _certified_first(q)]
    assert changed == []


def test_guardrail_released_35_routes_unchanged():
    path = config.DATA_DIR / "data" / "benchmark_questions.csv"
    if not path.exists():
        pytest.skip("released questions not available (dataset not downloaded)")
    from ontrack.l2_ask import run_benchmark
    qs = [q["question_text"] for q in run_benchmark.read_questions(path)]
    assert len(qs) == 35
    assert [q for q in qs if T.parse(q) and not _certified_first(q)] == []


@pytest.fixture
def con():
    c = duckdb.connect()
    c.execute("CREATE SCHEMA gold")
    c.execute("""CREATE TABLE gold.case_360 AS SELECT * FROM (VALUES
        ('mid_stage', 'ON', 'card', '1-30', 100.0, true, false, false, false, NULL),
        ('mid_stage', 'QC', 'card', '1-30', 50.0, false, true, false, false, NULL),
        ('early_stage', 'ON', 'auto_loan', '31-60', 25.5, false, false, true, false, NULL),
        ('early_stage', 'ON', 'card', '31-60', 999.0, true, false, false, false, 'cured'))
        t(queue, province_code, primary_product, current_bucket, total_overdue, hardship_flag, dispute_flag,
          complaint_flag, vulnerable_customer_flag, outcome)""")
    c.execute("""CREATE TABLE gold.nba_recommendation AS SELECT * FROM (VALUES
        ('G1', 'hardship_referral', 'human queue', true, 'hardship_text', '1-30'),
        ('G2', 'hardship_referral', 'human queue', true, NULL, '1-30'),
        ('G3', 'call', 'phone', false, NULL, '31-60'))
        t(golden_id, action, channel, needs_human_review, routing_category, current_bucket)""")
    c.execute("""CREATE TABLE gold.c360_customer AS SELECT * FROM (VALUES
        ('G1', 3, 'ON', true, true, 1, 100.0), ('G2', 1, 'QC', false, false, 1, 50.0),
        ('G3', 2, 'QC', true, false, 0, 0.0)) t(golden_id, products_held, province_code, consent_call,
        vulnerability_flag, open_case_count, total_overdue)""")
    return c


@pytest.mark.parametrize("q, rows", [
    ("How many open cases are in each queue?", [("mid_stage", 2), ("early_stage", 1)]),
    ("Which province has the highest total overdue on open cases?", [("ON", 125.5)]),
    ("What share of open cases carry a hardship flag?", [(33.3,)]),
    ("How many open auto loan cases have a complaint flag?", [(1,)]),
    ("how mnay open cases are there in ontario", [(2,)]),
    ("How many open cases does OnTrack send to a person first?", [(2,)]),
    ("What is the most common recommended action, and for how many cases?", [("hardship_referral", 2)]),
    ("How many open cases show hardship in notes or calls that the case flag missed?", [(1,)]),
    ("How many golden customers have an open collections case in Quebec?", [(1,)]),
    ("How many customers have not given consent to be called?", [(1,)]),
    ("On average, how many products does a golden customer hold?", [(2.0,)]),
])
def test_template_sql_on_a_tiny_gold(con, q, rows):
    assert con.execute(T.to_sql(T.parse(q))).fetchall() == rows


def test_vulnerable_treatment_answer(con):
    class Eng:
        def run_sql(self, sql):
            return sql, con.execute(sql).df()
    a = T.answer(Eng(), "How many customers are flagged as vulnerable, and how does OnTrack treat them?")
    assert a.route == "explain" and a.answer.startswith("1 customer is flagged as vulnerable")
    assert "1 of their 1 open cases (100%) to a person first" in a.answer
