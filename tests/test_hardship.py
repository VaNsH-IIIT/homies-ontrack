"""Tests for the hardship routing module (owner: P3)."""
import pytest
from ontrack.l4_nba.hardship import (
    _check_structured,
    _check_payment_distress,
    assess_hardship,
)


def base(**overrides):
    row = {
        "case_id": "CS0001",
        "golden_id": "G001",
        "hardship_flag": False,
        "vulnerability_flag": False,
        "dispute_flag": False,
        "complaint_flag": False,
        "insolvency_flag": False,
        "deceased_flag": False,
        "dpd_at_entry": 30,
        "total_past_due": 1000,
        "payments_90d": 0,
        "payments_30d": 0,
        "days_since_last_payment": 60,
    }
    row.update(overrides)
    return row


class TestStructuredSignals:
    def test_no_flags(self):
        assert _check_structured(base()) == []

    def test_hardship_flag(self):
        reasons = _check_structured(base(hardship_flag=True))
        assert len(reasons) == 1
        assert "hardship" in reasons[0].lower()

    def test_vulnerability_flag(self):
        reasons = _check_structured(base(vulnerability_flag=True))
        assert len(reasons) == 1
        assert "vulnerability" in reasons[0].lower()

    def test_dispute_flag(self):
        reasons = _check_structured(base(dispute_flag=True))
        assert len(reasons) == 1
        assert "dispute" in reasons[0].lower()

    def test_complaint_flag(self):
        reasons = _check_structured(base(complaint_flag=True))
        assert len(reasons) == 1
        assert "complaint" in reasons[0].lower()

    def test_insolvency_flag(self):
        reasons = _check_structured(base(insolvency_flag=True))
        assert len(reasons) == 1
        assert "insolvency" in reasons[0].lower() or "bankruptcy" in reasons[0].lower()

    def test_deceased_flag(self):
        reasons = _check_structured(base(deceased_flag=True))
        assert len(reasons) == 1
        assert "deceased" in reasons[0].lower()

    def test_multiple_flags(self):
        reasons = _check_structured(base(hardship_flag=True, vulnerability_flag=True))
        assert len(reasons) == 2

    def test_no_delinquency(self):
        reasons = _check_structured(base(dpd_at_entry=0, total_past_due=0))
        assert len(reasons) == 1
        assert "no delinquency" in reasons[0].lower()


class TestPaymentDistress:
    def test_no_distress(self):
        assert _check_payment_distress(base(payments_90d=0, payments_30d=0)) == []

    def test_sudden_stop(self):
        reasons = _check_payment_distress(base(
            payments_90d=3, payments_30d=0, days_since_last_payment=50,
        ))
        assert len(reasons) == 1
        assert "sudden" in reasons[0].lower() or "stopped" in reasons[0].lower()

    def test_still_paying(self):
        reasons = _check_payment_distress(base(
            payments_90d=3, payments_30d=1, days_since_last_payment=10,
        ))
        assert reasons == []

    def test_never_paid(self):
        reasons = _check_payment_distress(base(
            payments_90d=0, payments_30d=0, days_since_last_payment=999,
        ))
        assert reasons == []


class TestAssessHardship:
    def test_clean_case(self):
        hardship, needs_human, reasons = assess_hardship(base())
        assert not hardship
        assert not needs_human
        assert reasons == []

    def test_hardship_case(self):
        hardship, needs_human, reasons = assess_hardship(base(hardship_flag=True))
        assert hardship
        assert needs_human
        assert len(reasons) >= 1

    def test_combined_signals(self):
        hardship, needs_human, reasons = assess_hardship(base(
            hardship_flag=True,
            payments_90d=4,
            payments_30d=0,
            days_since_last_payment=50,
        ))
        assert hardship
        assert needs_human
        assert len(reasons) >= 2

    def test_no_con_still_works(self):
        hardship, needs_human, reasons = assess_hardship(base(vulnerability_flag=True), con=None)
        assert hardship
        assert needs_human
