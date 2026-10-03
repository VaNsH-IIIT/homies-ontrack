"""Unit tests for the Layer 4 policy gate (owner: P3)."""
import datetime as dt

import pytest

from ontrack.l4_nba.policy_gate import (
    ActionResult,
    check_cease_communication,
    check_consent,
    check_contact_cap,
    check_dispute,
    check_do_not_call,
    check_hardship,
    check_holds,
    check_permitted_hours,
    check_stat_holidays,
    evaluate,
    get_allowed_actions,
    needs_human_review,
    service_notes,
)


def base_row(**overrides) -> dict:
    """A customer+case row with all flags set to 'fully permissive'."""
    row = {
        "consent_call": True,
        "consent_sms": True,
        "consent_email": True,
        "consent_push": True,
        "consent_autodialer": True,
        "internal_do_not_call_flag": False,
        "national_dncl_flag": False,
        "cease_communication_flag": False,
        "insolvency_flag": False,
        "deceased_flag": False,
        "third_party_hold_flag": False,
        "vulnerability_flag": False,
        "hardship_flag": False,
        "dispute_flag": False,
        "complaint_flag": False,
        "credit_counselling_agency_flag": False,
        "contacts_last_7d": 0,
        "contact_cap_7d": 7,
        "permitted_call_start_local": "08:00",
        "permitted_call_end_local": "21:00",
        "sunday_contact_permitted": True,
        "preferred_language": "EN",
        "province_code": "ON",
    }
    row.update(overrides)
    return row


# --- Consent rules ---

class TestConsent:
    def test_all_consent_given(self):
        blocks = check_consent(base_row())
        assert blocks == []

    @pytest.mark.parametrize("consent_col,action", [
        ("consent_call", "call"),
        ("consent_sms", "sms"),
        ("consent_email", "email"),
        ("consent_push", "push_notification"),
    ])
    def test_missing_consent_blocks_channel(self, consent_col, action):
        blocks = check_consent(base_row(**{consent_col: False}))
        blocked_actions = [b[0] for b in blocks]
        assert action in blocked_actions

    def test_no_autodialer_does_not_block_manual_call(self):
        blocks = check_consent(base_row(consent_autodialer=False))
        assert "call" not in [b[0] for b in blocks]
        assert any("manually" in n for n in service_notes(base_row(consent_autodialer=False)))


# --- Cease communication ---

class TestCeaseComm:
    def test_cease_blocks_all_outbound(self):
        blocks = check_cease_communication(base_row(cease_communication_flag=True))
        blocked_actions = {b[0] for b in blocks}
        assert blocked_actions == {"call", "sms", "email", "push_notification", "reminder_letter"}

    def test_no_cease_no_blocks(self):
        assert check_cease_communication(base_row()) == []


# --- Do not call ---

class TestDoNotCall:
    def test_internal_dnc_blocks_call(self):
        blocks = check_do_not_call(base_row(internal_do_not_call_flag=True))
        blocked_actions = [b[0] for b in blocks]
        assert "call" in blocked_actions
        assert "sms" not in blocked_actions

    def test_national_dncl_blocks_call(self):
        blocks = check_do_not_call(base_row(national_dncl_flag=True))
        blocked_actions = [b[0] for b in blocks]
        assert "call" in blocked_actions


# --- Holds ---

class TestHolds:
    def test_insolvency_blocks_outbound(self):
        blocks = check_holds(base_row(insolvency_flag=True))
        blocked_actions = {b[0] for b in blocks}
        assert "call" in blocked_actions
        assert "sms" in blocked_actions
        assert "email" in blocked_actions

    def test_deceased_blocks_everything_except_do_nothing(self):
        blocks = check_holds(base_row(deceased_flag=True))
        blocked_actions = {b[0] for b in blocks}
        assert "do_nothing" not in blocked_actions
        assert len(blocked_actions) == 7

    def test_third_party_blocks_direct_contact(self):
        blocks = check_holds(base_row(third_party_hold_flag=True))
        blocked_actions = {b[0] for b in blocks}
        assert "call" in blocked_actions
        assert "sms" in blocked_actions
        assert "push_notification" in blocked_actions
        assert "email" not in blocked_actions


# --- Dispute ---

class TestDispute:
    def test_dispute_blocks_outbound(self):
        blocks = check_dispute(base_row(dispute_flag=True))
        blocked_actions = {b[0] for b in blocks}
        assert "call" in blocked_actions

    def test_credit_counselling_blocks_outbound(self):
        blocks = check_dispute(base_row(credit_counselling_agency_flag=True))
        assert len(blocks) > 0


# --- Contact cap ---

class TestContactCap:
    def test_under_cap_no_blocks(self):
        blocks = check_contact_cap(base_row(contacts_last_7d=3, contact_cap_7d=7))
        assert blocks == []

    def test_at_cap_blocks_outbound(self):
        blocks = check_contact_cap(base_row(contacts_last_7d=7, contact_cap_7d=7))
        blocked_actions = {b[0] for b in blocks}
        assert "call" in blocked_actions
        assert "sms" in blocked_actions

    def test_over_cap_blocks(self):
        blocks = check_contact_cap(base_row(contacts_last_7d=10, contact_cap_7d=7))
        assert len(blocks) > 0


# --- Permitted hours ---

class TestPermittedHours:
    def test_within_hours_no_block(self):
        ts = dt.datetime(2026, 10, 1, 14, 0)
        blocks = check_permitted_hours(base_row(), ts)
        assert blocks == []

    def test_before_hours_blocks_call(self):
        ts = dt.datetime(2026, 10, 1, 6, 0)
        blocks = check_permitted_hours(base_row(), ts)
        blocked_actions = [b[0] for b in blocks]
        assert "call" in blocked_actions

    def test_after_hours_blocks_call(self):
        ts = dt.datetime(2026, 10, 1, 22, 0)
        blocks = check_permitted_hours(base_row(), ts)
        blocked_actions = [b[0] for b in blocks]
        assert "call" in blocked_actions

    def test_no_timestamp_no_block(self):
        blocks = check_permitted_hours(base_row(), None)
        assert blocks == []


# --- Stat holidays ---

class TestStatHolidays:
    def test_holiday_blocks_call(self):
        ts = dt.datetime(2026, 9, 30, 14, 0)  # National Day for Truth and Reconciliation
        blocks = check_stat_holidays(base_row(), ts)
        blocked_actions = [b[0] for b in blocks]
        assert "call" in blocked_actions

    def test_normal_day_no_block(self):
        ts = dt.datetime(2026, 10, 1, 14, 0)  # Thursday
        blocks = check_stat_holidays(base_row(), ts)
        assert blocks == []

    def test_sunday_not_permitted(self):
        ts = dt.datetime(2026, 10, 4, 14, 0)  # Sunday
        blocks = check_stat_holidays(base_row(sunday_contact_permitted=False), ts)
        blocked_actions = [b[0] for b in blocks]
        assert "call" in blocked_actions

    def test_sunday_permitted(self):
        ts = dt.datetime(2026, 10, 4, 14, 0)  # Sunday
        blocks = check_stat_holidays(base_row(sunday_contact_permitted=True), ts)
        assert blocks == []


# --- Hardship ---

class TestHardship:
    def test_hardship_flags_specialist_routing(self):
        blocks = check_hardship(base_row(hardship_flag=True))
        assert len(blocks) > 0
        assert all("specialist" in b[1].lower() or "hardship" in b[1].lower() for b in blocks)

    def test_vulnerability_flags_specialist_routing(self):
        blocks = check_hardship(base_row(vulnerability_flag=True))
        assert len(blocks) > 0


# --- Language ---

class TestLanguage:
    def test_french_routes_to_french_agent_without_blocking(self):
        row = base_row(preferred_language="FR")
        assert any("French" in n for n in service_notes(row))
        assert evaluate(row)["call"].allowed

    def test_english_no_note(self):
        assert service_notes(base_row(preferred_language="EN")) == []


# --- Full evaluate ---

class TestEvaluate:
    def test_permissive_row_all_allowed(self):
        results = evaluate(base_row())
        for action, r in results.items():
            assert r.allowed, f"{action} should be allowed for a permissive row"

    def test_do_nothing_always_allowed(self):
        results = evaluate(base_row(
            deceased_flag=True,
            cease_communication_flag=True,
            insolvency_flag=True,
        ))
        assert results["do_nothing"].allowed

    def test_multiple_blocks_accumulate_reasons(self):
        row = base_row(consent_call=False, internal_do_not_call_flag=True)
        results = evaluate(row)
        assert not results["call"].allowed
        assert len(results["call"].reasons) >= 2


# --- Convenience helpers ---

class TestGetAllowedActions:
    def test_returns_three_values(self):
        allowed, blocked, reasons = get_allowed_actions(base_row())
        assert isinstance(allowed, list)
        assert isinstance(blocked, list)
        assert isinstance(reasons, dict)

    def test_all_allowed_for_permissive(self):
        allowed, blocked, _ = get_allowed_actions(base_row())
        assert len(blocked) == 0
        assert "do_nothing" in allowed
        assert "call" in allowed


class TestNeedsHumanReview:
    def test_hardship_needs_review(self):
        flag, reason = needs_human_review(base_row(hardship_flag=True))
        assert flag is True
        assert reason is not None

    def test_dispute_needs_review(self):
        flag, reason = needs_human_review(base_row(dispute_flag=True))
        assert flag is True

    def test_holds_need_review(self):
        for col in ("insolvency_flag", "deceased_flag", "third_party_hold_flag", "cease_communication_flag"):
            flag, reason = needs_human_review(base_row(**{col: True}))
            assert flag is True and reason

    def test_clean_case_no_review(self):
        flag, reason = needs_human_review(base_row())
        assert flag is False
        assert reason is None
