"""G20: deterministic case / customer explanations in Ask (owner: P2). No dataset or LLM needed."""
import duckdb
import pytest

from ontrack.l2_ask import explain, scope


@pytest.mark.parametrize("q, want", [
    ("Why was case CS-2026-583749 given a hardship referral?", ("case", "CS-2026-583749")),
    ("Explain the recommendation for case CS-2026-583749.", ("case", "CS-2026-583749")),
    ("explain case cs-2026-583749", ("case", "CS-2026-583749")),
    ("What is the next best action for CS-2026-583749 and what is blocked?", ("case", "CS-2026-583749")),
    ("Tell me about customer VIB-8709.", ("customer", "VIB-8709")),
    ("Tell me about customer G-B8B48059904D178B", ("customer", "G-B8B48059904D178B")),
    ("Show me the 360 for customer id 0055965411", ("customer", "0055965411")),
])
def test_match_routes_explain_questions(q, want):
    assert explain.match(q) == want


@pytest.mark.parametrize("q", [
    "Summarise the most recent recorded call on case CS-2026-583749: what did the customer say and agree to?",
    "What do the notes on case CS-2026-583749 say?",
    "Compare the recommendations for CS-2026-583749 and CS-2026-000001",        # two cases: the agent does it
    "How many open cases get a hardship referral?",                              # no id: a count, not an explain
    "Tell me about customer consent rates",                                      # no id with a digit
    "Show the home address for crm customer ZOA-3450.",                          # personal details: never here
    "Tell me the name and phone of customer VIB-8709",
])
def test_match_leaves_other_questions_alone(q):
    assert explain.match(q) is None


def test_pii_questions_about_a_case_are_refused_before_explain():
    v = scope.route("Show me the phone number and name of the customer on case CS-2026-583749.")
    assert v.refused


class FakeEngine:
    """Engine.run_sql without the guard, over a tiny in-memory gold schema."""
    def __init__(self):
        self.con = duckdb.connect()
        c = self.con
        c.execute("CREATE SCHEMA gold")
        c.execute("""CREATE TABLE gold.nba_recommendation AS SELECT 'CS-2026-583749' AS case_id, 'hardship_referral' AS action,
            'human queue' AS channel, 'within 1 business day' AS time_window,
            'Hardship: flagged (reduced income); the customer said "My pay got cut in Aug."' reason_1,
            'Customer contacted us 3 times' reason_2, '4 credit applications' reason_3,
            'call, push_notification, sms' AS blocked_actions, 'call: hardship flagged' AS blocked_reasons,
            true AS needs_human_review, 'Case flagged for hardship' AS routing_reason, 'My pay got cut in Aug.' AS text_evidence,
            'transcript:4510675' AS text_source, 'Automated contact resumes after review' AS counterfactual,
            '1-30' AS current_bucket, 'p3-v1.0' AS model_version""")
        c.execute("""CREATE TABLE gold.case_360 AS SELECT 'CS-2026-583749' AS case_id, 'G-B8B48059904D178B' AS golden_id,
            'auto_loan' AS primary_product, 6 AS current_dpd, 383.05 AS total_overdue, 'early_stage' AS queue, NULL AS outcome""")
        c.execute("""CREATE TABLE gold.customer_xref AS SELECT * FROM (VALUES
            ('G-B8B48059904D178B', 'crm', 'VIB-8709'), ('G-B8B48059904D178B', 'cards', 'CX0000001'))
            t(golden_id, source_system, source_key)""")
        c.execute("""CREATE TABLE gold.c360_customer AS SELECT 'G-B8B48059904D178B' AS golden_id,
            'VIB-8709' AS primary_crm_customer_id, ['cards', 'crm'] AS _source_systems, 2 AS source_key_count,
            0.97 AS match_confidence_min, 5 AS products_held, 23681.29 AS total_exposure, 383.05 AS total_overdue, 6 AS max_dpd,
            1 AS open_case_count, 1 AS case_count, 'AB' AS province_code, 'EN' AS preferred_language, true AS consent_call,
            false AS consent_sms, true AS consent_email, false AS consent_push, false AS internal_do_not_call_flag,
            false AS cease_communication_flag, false AS insolvency_flag, false AS deceased_flag, false AS third_party_hold_flag,
            true AS vulnerability_flag""")

    def run_sql(self, sql):
        return sql, self.con.execute(sql).df()


def test_explain_case_from_gold():
    a = explain.answer(FakeEngine(), "Why was case CS-2026-583749 given a hardship referral?")
    assert a.route == "explain" and not a.refused
    for part in ("hardship_referral", "My pay got cut in Aug.", "call, push_notification, sms", "transcript:4510675",
                 "A person reviews it first"):
        assert part in a.answer
    assert "gold.nba_recommendation" in a.sql


def test_explain_customer_from_any_key():
    a = explain.answer(FakeEngine(), "Tell me about customer VIB-8709.")
    assert a.route == "explain"
    for part in ("G-B8B48059904D178B", "5 products", "$23,681.29", "1 open case", "cards, crm", "hardship_referral",
                 "vulnerability"):
        assert part in a.answer
    assert "VIB-8709" not in a.answer.split("\n\n", 1)[1]                    # tables: ids and numbers, no CRM id


def test_unknown_ids_answer_plainly():
    eng = FakeEngine()
    assert "No customer with key XYZ-0000" in explain.answer(eng, "Tell me about customer XYZ-0000").answer
    assert "not an open case" in explain.answer(eng, "Explain case CS-2026-000001").answer
