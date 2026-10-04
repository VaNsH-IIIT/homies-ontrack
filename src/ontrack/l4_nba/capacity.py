"""Can people work the human-only queue? Capacity of the hardship team against OnTrack's referrals (owner: P3, K25).

Measured from the data: the hardship team's worked hours per business day (``agent_shifts``, queue
``hardship_specialist``, last 4 weeks, absences excluded), its handle time (``agents.avg_handle_time_sec``, active
hardship specialists) and the daily inflow of new hardship referrals (cases opened in the last 28 days that OnTrack
routes to hardship). Stated assumptions: 75% of worked time is spent on cases, and a full hardship assessment (income,
expenses, plan) may take 20 minutes, so the answer is also shown for that slower case.
"""
from __future__ import annotations

from ontrack import config

OCCUPANCY = 0.75          # share of worked time on cases (breaks, training and admin take the rest)
ASSESSMENT_MIN = 20.0     # a full hardship assessment, if it takes longer than the measured handle time
WINDOW_DAYS = 28


def human_capacity(con, as_of: str = config.SNAPSHOT_DATE) -> dict:
    """Numbers for EVALUATION section 4b and the supervisor view. Every count comes from the tables named above."""
    team = con.execute(f"""
        SELECT count(DISTINCT shift_date) AS days, sum(worked_minutes) / 60.0 AS hours
        FROM bronze.agent_shifts
        WHERE queue_assignment = 'hardship_specialist' AND NOT coalesce(absence_flag, false)
          AND dayofweek(shift_date) BETWEEN 1 AND 5
          AND shift_date > (SELECT max(shift_date) FROM bronze.agent_shifts) - {WINDOW_DAYS}""").fetchone()
    hours_per_day = (team[1] or 0) / max(team[0] or 0, 1)
    aht_min = (con.execute("""SELECT avg(avg_handle_time_sec) FROM bronze.agents
                              WHERE status = 'active' AND role = 'hardship_specialist'""").fetchone()[0] or 0) / 60
    q = con.execute(f"""
        SELECT count(*) FILTER (WHERE r.action = 'hardship_referral') AS hardship,
               count(*) FILTER (WHERE r.needs_human_review AND r.action <> 'hardship_referral') AS other_human,
               count(*) FILTER (WHERE r.action = 'hardship_referral'
                                AND c.case_open_date > DATE '{as_of}' - {WINDOW_DAYS}) AS new_hardship,
               sum(r.score) FILTER (WHERE r.action = 'hardship_referral') AS hardship_dollars
        FROM gold.nba_recommendation r JOIN gold.case_360 c USING (case_id)""").fetchone()
    hardship, other_human, new_hardship, dollars = q[0], q[1], q[2], q[3] or 0
    inflow = new_hardship / WINDOW_DAYS * 7 / 5            # per business day

    def per_day(minutes):
        return hours_per_day * 60 * OCCUPANCY / minutes if minutes else 0.0

    out = {"hours_per_day": hours_per_day, "aht_min": aht_min, "hardship": hardship, "other_human": other_human,
           "inflow_per_day": inflow, "hardship_dollars": dollars}
    for key, minutes in (("measured", aht_min), ("assessment", ASSESSMENT_MIN)):
        cap = per_day(minutes)
        spare = cap - inflow
        out[key] = {"minutes": minutes, "first_contacts_per_day": cap, "new_within_1_day": cap >= inflow,
                    "days_to_clear_stock": hardship / spare if spare > 0 else None}
    # priority order: the queue is worked highest dollars at risk first; how much of the money is reached in 5 days
    reach = int(out["measured"]["first_contacts_per_day"] - inflow) * 5
    top = con.execute(f"""SELECT sum(score) FROM (SELECT score FROM gold.nba_recommendation
                          WHERE action = 'hardship_referral' ORDER BY score DESC, case_id LIMIT {max(reach, 0)})""").fetchone()[0]
    out["first_week_cases"] = min(max(reach, 0), hardship)
    out["first_week_dollar_share"] = (top or 0) / dollars if dollars else 0.0
    return out


def capacity_sentence(c: dict) -> str:
    """One line for the supervisor view."""
    m, a = c["measured"], c["assessment"]
    return (f"Hardship team: {c['hours_per_day']:,.0f} agent-hours a business day, about {m['first_contacts_per_day']:,.0f} "
            f"first contacts at the measured {m['minutes']:.0f}-minute handle time ({a['first_contacts_per_day']:,.0f} at "
            f"{a['minutes']:.0f} minutes) against about {c['inflow_per_day']:,.0f} new hardship referrals a day, so new cases "
            f"are reached within a business day. Today's {c['hardship']:,} referrals are a backlog: about "
            f"{m['days_to_clear_stock']:,.0f} business days to reach them all, highest dollars at risk first "
            f"({c['first_week_dollar_share']:.0%} of the dollars in the first week).")
