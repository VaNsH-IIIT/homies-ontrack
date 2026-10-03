"""Agent card: NBA recommendations with accept / edit / reject (owner: P3).

Shows the recommended action for each open case with reasons, blocked
actions, and hardship flags.  The agent can accept, edit, or reject the
recommendation; every decision is persisted via common.record_decision().
"""
import streamlit as st

from ontrack.app.common import (
    REASON_CODES,
    header,
    query,
    record_decision,
    table_exists,
)

header("Agent Card", "Next best action for open collection cases")

if not table_exists("gold", "nba_recommendation"):
    st.warning("No recommendations found. Run `python -m ontrack.l4_nba.run` first.")
    st.stop()

recs = query("""
    SELECT r.case_id, r.golden_id, r.action, r.channel, r.time_window,
           r.score, r.reason_1, r.reason_2, r.reason_3,
           r.blocked_actions, r.hardship_flag, r.needs_human_review,
           r.model_version, r.p_cure_30d, r.p_payment_7d,
           cu.total_overdue, cu.max_dpd, cu.products_held,
           cu.province_code, cu.preferred_language
    FROM gold.nba_recommendation r
    LEFT JOIN gold.c360_customer cu ON cu.golden_id = r.golden_id
    ORDER BY r.needs_human_review DESC, r.score DESC
""")

if recs.empty:
    st.info("No open-case recommendations to show.")
    st.stop()

# --- Filters ---
col1, col2, col3 = st.columns(3)
with col1:
    actions = ["All"] + sorted(recs["action"].dropna().unique().tolist())
    action_filter = st.selectbox("Action", actions)
with col2:
    review_filter = st.selectbox("Human review", ["All", "Yes", "No"])
with col3:
    hardship_filter = st.selectbox("Hardship flag", ["All", "Yes", "No"])

filtered = recs.copy()
if action_filter != "All":
    filtered = filtered[filtered["action"] == action_filter]
if review_filter == "Yes":
    filtered = filtered[filtered["needs_human_review"] == True]  # noqa: E712
elif review_filter == "No":
    filtered = filtered[filtered["needs_human_review"] == False]  # noqa: E712
if hardship_filter == "Yes":
    filtered = filtered[filtered["hardship_flag"] == True]  # noqa: E712
elif hardship_filter == "No":
    filtered = filtered[filtered["hardship_flag"] == False]  # noqa: E712

st.metric("Showing", f"{len(filtered):,d} of {len(recs):,d} cases")

ALL_ACTIONS = ["call", "sms", "email", "push_notification", "reminder_letter",
               "hardship_referral", "specialist_agent", "do_nothing"]

# --- Case cards ---
for i, (_, row) in enumerate(filtered.head(50).iterrows()):
    label = f"Case {row['case_id']} — **{row['action']}** (score: {row['score']:.3f})"
    if row.get("hardship_flag"):
        label += " | HARDSHIP"
    if row.get("needs_human_review"):
        label += " | HUMAN REVIEW"

    with st.expander(label, expanded=(i < 3)):
        c1, c2, c3 = st.columns([2, 2, 1])
        with c1:
            st.markdown("**Recommendation**")
            st.write(f"Action: **{row['action']}**")
            if row.get("channel"):
                st.write(f"Channel: {row['channel']}")
            st.write(f"Time window: {row.get('time_window', 'N/A')}")
            p_cure = row.get("p_cure_30d") or 0
            p_pay = row.get("p_payment_7d") or 0
            st.write(f"P(self-cure 30d): {p_cure:.1%}")
            st.write(f"P(payment 7d): {p_pay:.1%}")

        with c2:
            st.markdown("**Why**")
            for r_col in ("reason_1", "reason_2", "reason_3"):
                val = row.get(r_col)
                if val:
                    st.write(f"- {val}")
            blocked = row.get("blocked_actions")
            if blocked:
                st.markdown(f"**Blocked:** {blocked}")

        with c3:
            st.markdown("**Customer**")
            overdue = row.get("total_overdue") or 0
            st.write(f"Overdue: ${overdue:,.0f}")
            st.write(f"Max DPD: {row.get('max_dpd', 0)}")
            st.write(f"Products: {row.get('products_held', 0)}")
            st.write(f"Province: {row.get('province_code', '?')}")

        # --- Agent decision ---
        st.divider()
        decision_key = f"decision_{i}"
        d1, d2 = st.columns([1, 2])
        with d1:
            agent_action = st.radio(
                "Decision", ["accept", "edit", "reject"],
                key=f"action_{i}", horizontal=True,
            )
        with d2:
            if agent_action in ("edit", "reject"):
                reason_code = st.selectbox(
                    "Reason", [rc for rc in REASON_CODES if rc != "agrees"],
                    key=f"reason_{i}",
                )
                note = st.text_input("Note (optional)", key=f"note_{i}")
            else:
                reason_code = "agrees"
                note = ""

        if agent_action == "edit":
            final_action = st.selectbox(
                "Override action",
                [a for a in ALL_ACTIONS if a != row["action"]],
                key=f"override_{i}",
            )
        else:
            final_action = row["action"]

        if st.button("Submit decision", key=f"submit_{i}"):
            try:
                did = record_decision(
                    case_id=str(row["case_id"]),
                    golden_id=str(row["golden_id"]),
                    recommended_action=row["action"],
                    agent_action=agent_action,
                    final_action=final_action,
                    reason_code=reason_code,
                    note=note,
                    model_version=str(row.get("model_version", "")),
                )
                st.success(f"Logged: {agent_action.upper()} (id: {did[:8]}...)")
            except ValueError as e:
                st.error(str(e))
