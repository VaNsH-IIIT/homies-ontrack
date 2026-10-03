"""Tests for the hardship routing module (owner: P3)."""
from ontrack.l4_nba.hardship import _check_income, _check_structured, _check_text, assess_hardship


def base(**overrides):
    row = {
        "case_id": "CS0001",
        "hardship_flag": False,
        "hardship_reason": None,
        "vulnerability_flag": False,
        "dispute_flag": False,
        "complaint_flag": False,
        "insolvency_flag": False,
        "deceased_flag": False,
        "third_party_hold_flag": False,
        "cease_communication_flag": False,
        "has_payroll": 1,
        "salary_gap_months_3m": 0,
        "salary_drop_pct": None,
        "dispute_raised_any": 0,
        "text_hardship_90d": None,
        "text_hardship_evidence": None,
        "text_dispute_any": None,
    }
    row.update(overrides)
    return row


class TestStructuredSignals:
    def test_no_flags(self):
        assert _check_structured(base()) == []

    def test_hardship_flag_with_reason(self):
        out = _check_structured(base(hardship_flag=True, hardship_reason="job_loss"))
        assert out == [("hardship_case_flag", "Case flagged for hardship (job loss)")]

    def test_each_flag_has_its_category(self):
        cases = {"vulnerability_flag": "vulnerability", "dispute_flag": "dispute", "complaint_flag": "complaint",
                 "insolvency_flag": "hold", "deceased_flag": "hold", "third_party_hold_flag": "hold",
                 "cease_communication_flag": "cease"}
        for col, cat in cases.items():
            out = _check_structured(base(**{col: True}))
            assert len(out) == 1 and out[0][0] == cat, col

    def test_null_values_are_not_true(self):
        assert _check_structured(base(hardship_flag=float("nan"), dispute_flag=None)) == []


class TestIncome:
    def test_two_missing_salary_months(self):
        out = _check_income(base(salary_gap_months_3m=2))
        assert out and "2 of the last 3 months" in out[0][1]

    def test_one_missing_month_is_not_hardship(self):
        assert _check_income(base(salary_gap_months_3m=1)) == []

    def test_income_drop(self):
        out = _check_income(base(salary_drop_pct=-0.55))
        assert out and "55%" in out[0][1]

    def test_small_drop_ignored(self):
        assert _check_income(base(salary_drop_pct=-0.30)) == []

    def test_no_payroll_means_no_salary_judgement(self):
        assert _check_income(base(has_payroll=0, salary_gap_months_3m=3)) == []


class TestText:
    def test_text_hardship_quotes_evidence(self):
        out = _check_text(base(text_hardship_90d=True, text_hardship_evidence="My pay got cut in Aug."))
        assert out == [("hardship_text",
                        'Customer described hardship in the last 90 days: "My pay got cut in Aug."')]

    def test_dispute_without_hardship_is_routed(self):
        # issue #5: disputes mentioned in notes/calls must reach the human queue without hardship
        r = assess_hardship(base(text_dispute_any=True))
        assert r["needs_human_review"] and not r["hardship_flag"]
        assert r["routing_category"] == "dispute"

    def test_long_quote_is_shortened(self):
        out = _check_text(base(text_hardship_90d=True, text_hardship_evidence="x" * 500))
        assert len(out[0][1]) < 220


class TestAssessHardship:
    def test_clean_case(self):
        r = assess_hardship(base())
        assert r == {"hardship_flag": False, "needs_human_review": False, "routing_category": None,
                     "routing_reason": None, "routing_reasons": None}

    def test_hardship_case(self):
        r = assess_hardship(base(hardship_flag=True))
        assert r["hardship_flag"] and r["needs_human_review"]
        assert r["routing_category"] == "hardship_case_flag"

    def test_vulnerability_needs_human_but_is_not_hardship(self):
        r = assess_hardship(base(vulnerability_flag=True))
        assert r["needs_human_review"] and not r["hardship_flag"]

    def test_priority_and_all_reasons_kept(self):
        r = assess_hardship(base(complaint_flag=True, text_hardship_90d=True, text_hardship_evidence="lost my job"))
        assert r["routing_category"] == "hardship_text"
        assert "complaint" in r["routing_reasons"].lower() and "lost my job" in r["routing_reasons"]

    def test_no_delinquency_is_not_hardship(self):
        # v0 treated "no delinquency" as hardship; it is not
        assert not assess_hardship(base(entry_overdue=0))["needs_human_review"]


class TestRouteCasesSQL:
    """The SQL path of route_cases on a small synthetic database (one join on the text roll-up)."""

    @staticmethod
    def _db(with_text: bool):
        import duckdb
        con = duckdb.connect()
        for s in ("gold", "features"):
            con.execute(f"CREATE SCHEMA {s}")
        con.execute("""CREATE TABLE features.case_features AS SELECT * FROM (VALUES
            ('C1', 'G1', DATE '2026-09-28', 0, 0, NULL::DOUBLE, 0),   -- clean
            ('C2', 'G2', DATE '2026-09-28', 0, 0, NULL, 0),           -- dispute only in a note
            ('C3', 'G3', DATE '2026-09-28', 0, 0, NULL, 0),           -- hardship in a call
            ('C4', 'G4', DATE '2026-09-28', 1, 3, -0.6, 0),           -- income shock
            ('C5', 'G5', DATE '2026-09-28', 0, 0, NULL, 0),           -- vulnerable (customer flag)
            ('C1', 'G1', DATE '2026-05-01', 0, 0, NULL, 0)            -- other as_of: ignored
        ) t(case_id, golden_id, as_of_date, has_payroll, salary_gap_months_3m, salary_drop_pct, dispute_raised_any)""")
        con.execute("""CREATE TABLE gold.case_360 AS SELECT case_id, false AS hardship_flag, NULL AS hardship_reason,
            false AS dispute_flag, false AS complaint_flag, false AS vulnerable_customer_flag,
            false AS insolvency_hold_flag, false AS deceased_hold_flag, false AS third_party_rep_flag,
            false AS cease_contact_flag FROM (VALUES ('C1'), ('C2'), ('C3'), ('C4'), ('C5')) t(case_id)""")
        con.execute("""CREATE TABLE gold.c360_customer AS SELECT golden_id, golden_id = 'G5' AS vulnerability_flag,
            false AS insolvency_flag, false AS deceased_flag, false AS third_party_hold_flag,
            false AS cease_communication_flag FROM (VALUES ('G1'), ('G2'), ('G3'), ('G4'), ('G5')) t(golden_id)""")
        if with_text:
            con.execute("""CREATE TABLE features.text_signals_case AS SELECT * FROM (VALUES
                ('C2', false, NULL, NULL, NULL::DOUBLE, true),
                ('C3', true, 'My pay got cut in Aug.', 'transcript:1', 0.9, false)
            ) t(case_id, text_hardship_90d, text_hardship_evidence, text_hardship_source, text_hardship_confidence,
                text_dispute_any)""")
        return con

    def test_routes_every_case_once_with_text(self):
        from ontrack.l4_nba.hardship import route_cases
        r = route_cases(self._db(True), "2026-09-28").set_index("case_id")
        assert sorted(r.index) == ["C1", "C2", "C3", "C4", "C5"]
        assert r.loc["C1", "needs_human_review"] == False  # noqa: E712
        assert r.loc["C2", "routing_category"] == "dispute" and not r.loc["C2", "hardship_flag"]
        assert r.loc["C3", "routing_category"] == "hardship_text"
        assert r.loc["C3", "text_evidence"] == "My pay got cut in Aug." and r.loc["C3", "text_source"] == "transcript:1"
        assert r.loc["C4", "routing_category"] == "hardship_income"
        assert r.loc["C5", "routing_category"] == "vulnerability" and not r.loc["C5", "hardship_flag"]

    def test_works_without_text_signals(self):
        from ontrack.l4_nba.hardship import route_cases
        r = route_cases(self._db(False), "2026-09-28").set_index("case_id")
        assert r.loc["C3", "needs_human_review"] == False  # noqa: E712  (no text table: no text hardship)
        assert r.loc["C4", "routing_category"] == "hardship_income"
