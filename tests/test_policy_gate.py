"""Unit tests for the Layer 4 policy gate (owner: P3)."""
import datetime as dt

import pytest

from ontrack.l4_nba.policy_gate import (
    ACTIONS,
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
        assert blocked_actions == {"call", "sms", "email", "push_notification", "reminder_letter",
                                   "specialist_agent"}

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


# --- K19: branches that matter, and the summary over a database ---

OUTBOUND = {"call", "sms", "email", "push_notification", "reminder_letter"}


def _blocked(row, ts=None) -> set[str]:
    return set(get_allowed_actions(row, ts)[1])


class TestMissingValues:
    """289 open cases on the full data have no consent or hold values (no CRM record): the ranker passes None."""

    def test_missing_consent_means_no_consent(self):
        assert _blocked({}) == {"call", "sms", "email", "push_notification"}
        assert _blocked(base_row(consent_call=None, consent_sms=None)) == {"call", "sms"}

    def test_missing_flags_do_not_block(self):
        row = base_row(**{k: None for k in ("cease_communication_flag", "insolvency_flag", "deceased_flag",
                                            "third_party_hold_flag", "dispute_flag", "hardship_flag",
                                            "contacts_last_7d", "contact_cap_7d")})
        assert _blocked(row) == set()
        assert needs_human_review(row) == (False, None)

    def test_missing_language_and_autodialer_notes(self):
        assert service_notes(base_row(preferred_language=None)) == []
        assert service_notes(base_row(consent_autodialer=None)) == ["No autodialer consent: agent dials manually"]
        assert service_notes(base_row(preferred_language="fr-CA"))[0].startswith("Serve in French")


class TestWhatEachHoldBlocks:
    def test_cease_blocks_every_outbound_action_and_the_specialist(self):
        assert _blocked(base_row(cease_communication_flag=True)) == OUTBOUND | {"specialist_agent"}

    def test_insolvency_blocks_the_same_set_with_a_trustee_reason(self):
        allowed, blocked, reasons = get_allowed_actions(base_row(insolvency_flag=True))
        assert set(blocked) == OUTBOUND | {"specialist_agent"}
        assert "trustee" in reasons["call"][0]

    def test_deceased_blocks_hardship_referral_too(self):
        assert _blocked(base_row(deceased_flag=True)) == set(ACTIONS) - {"do_nothing"}

    def test_dispute_or_counselling_blocks_outbound_but_not_a_person(self):
        for flag in ("dispute_flag", "credit_counselling_agency_flag"):
            assert _blocked(base_row(**{flag: True})) == OUTBOUND

    def test_hardship_or_vulnerability_blocks_call_and_sms_only(self):
        for flag in ("hardship_flag", "vulnerability_flag"):
            assert _blocked(base_row(**{flag: True})) == {"call", "sms"}


class TestContactCap:
    def test_default_cap_is_7(self):
        row = base_row(contacts_last_7d=6)
        del row["contact_cap_7d"]
        assert _blocked(row) == set()
        assert _blocked({**row, "contacts_last_7d": 7}) == OUTBOUND

    def test_case_specific_cap(self):
        assert _blocked(base_row(contacts_last_7d=3, contact_cap_7d=3)) == OUTBOUND
        assert _blocked(base_row(contacts_last_7d=2, contact_cap_7d=3)) == set()

    def test_cap_reason_says_how_many(self):
        reasons = get_allowed_actions(base_row(contacts_last_7d=9))[2]
        assert reasons["sms"] == ["Contact cap reached (9/7 contacts in last 7 days)"]


class TestTimeRules:
    def test_start_hour_is_inclusive_end_hour_exclusive(self):
        assert check_permitted_hours(base_row(), dt.datetime(2026, 10, 1, 8, 0)) == []
        assert check_permitted_hours(base_row(), dt.datetime(2026, 10, 1, 20, 59)) == []
        assert [b[0] for b in check_permitted_hours(base_row(), dt.datetime(2026, 10, 1, 21, 0))] == ["call"]

    def test_only_calls_are_time_restricted(self):
        sunday_night = dt.datetime(2026, 10, 4, 23, 0)
        assert _blocked(base_row(sunday_contact_permitted=False), sunday_night) == {"call"}

    def test_holiday_accepts_a_plain_date(self):
        assert [b[0] for b in check_stat_holidays(base_row(), dt.date(2026, 10, 12))] == ["call"]   # Thanksgiving

    def test_holiday_on_a_sunday_gives_both_reasons(self, monkeypatch):
        import ontrack.l4_nba.policy_gate as pg
        monkeypatch.setattr(pg, "CANADA_STAT_HOLIDAYS_2026", {dt.date(2026, 10, 4)})   # no 2026 holiday is a Sunday
        reasons = [b[1] for b in pg.check_stat_holidays(base_row(sunday_contact_permitted=False),
                                                        dt.datetime(2026, 10, 4, 12))]
        assert reasons == ["Statutory holiday (2026-10-04) — no outbound calls",
                           "Sunday contact not permitted for this customer"]


class TestEvaluateMechanics:
    def test_duplicate_reasons_kept_once_and_unknown_actions_ignored(self, monkeypatch):
        import ontrack.l4_nba.policy_gate as pg
        monkeypatch.setattr(pg, "ALL_RULES", [lambda r: [("call", "X"), ("call", "X"), ("teleport", "Y")]])
        results = pg.evaluate(base_row())
        assert results["call"].reasons == ["X"] and not results["call"].allowed
        assert set(results) == set(ACTIONS)

    def test_time_rules_are_skipped_without_a_timestamp(self):
        assert _blocked(base_row(sunday_contact_permitted=False, permitted_call_start_local="23:00")) == set()

    def test_first_matching_rule_gives_the_review_reason(self):
        flag, reason = needs_human_review(base_row(cease_communication_flag=True, hardship_flag=True))
        assert flag and reason.startswith("Hardship")
        assert needs_human_review(base_row(complaint_flag=True))[1].startswith("Complaint")


def test_build_gate_for_cases_summary(capsys):
    import duckdb

    from ontrack import config
    from ontrack.l4_nba.policy_gate import build_gate_for_cases

    con = duckdb.connect()
    con.execute("CREATE SCHEMA gold")
    flags = ("internal_do_not_call_flag", "cease_communication_flag", "insolvency_flag", "deceased_flag",
             "third_party_hold_flag", "vulnerability_flag")
    con.execute(f"""CREATE TABLE gold.c360_customer AS SELECT golden_id,
        true AS consent_call, true AS consent_sms, true AS consent_email, true AS consent_push,
        true AS consent_autodialer, {", ".join(f"false AS {f}" for f in flags)},
        'EN' AS preferred_language, 'ON' AS province_code, 'America/Toronto' AS time_zone
        FROM (VALUES ('G1'), ('G2')) t(golden_id)""")
    con.execute("""CREATE TABLE gold.case_360 AS SELECT * FROM (VALUES
        ('K1', 'G1', NULL::BOOLEAN, false, NULL),     -- fully permissive: 8 of 8 allowed
        ('K2', 'G2', false, false, NULL),             -- 7 contacts this week: outbound blocked, 3 allowed
        ('K3', 'G9', false, false, NULL),             -- no customer record: no consent, 4 allowed
        ('K4', 'G1', false, false, 'paid')            -- closed: not counted
    ) t(case_id, golden_id, hardship_flag, complaint_flag, outcome)""")
    snap = dt.date.fromisoformat(config.SNAPSHOT_DATE)
    con.execute("CREATE TABLE gold.contact_timeline (case_id VARCHAR, contact_ts_utc TIMESTAMP)")
    for d in range(7):
        con.execute("INSERT INTO gold.contact_timeline VALUES ('K2', ?)", [dt.datetime.combine(snap, dt.time(9)) - dt.timedelta(days=d)])
    con.execute("INSERT INTO gold.contact_timeline VALUES ('K1', ?)", [dt.datetime.combine(snap, dt.time(9)) - dt.timedelta(days=8)])

    build_gate_for_cases(con)
    out = capsys.readouterr().out
    assert "Policy gate: 3 open cases" in out
    assert "Average allowed actions: 5.0 / 8" in out and "Average blocked actions: 3.0 / 8" in out
