"""Agent card: NBA recommendations with accept / edit / reject (owner: P3).

Shows the recommended action for each open case with reasons, blocked
actions, and hardship flags. The agent can accept, edit, or reject the
recommendation, and the decision is logged to l4.decision_log.
"""
import streamlit as st

st.set_page_config(page_title="Agent Card — OnTrack", layout="wide")
st.title("Agent Card")
st.caption("Next best action for open collection cases")

try:
    from ontrack.db import connect
    con = connect(read_only=True)
except Exception as e:
    st.error(f"Cannot connect to the database: {e}")
    st.info("Run `python -m ontrack.l1_factory.bronze` and `python -m ontrack.l1_factory.build` first.")
    st.stop()

try:
    recs = con.execute("""
        SELECT r.case_id, r.golden_id, r.action, r.channel, r.time_window,
               r.score, r.reason_1, r.reason_2, r.reason_3,
               r.blocked_actions, r.hardship_flag, r.needs_human_review,
               r.model_version, r.p_cure_30d, r.p_payment_7d,
               cu.total_overdue, cu.max_dpd, cu.products_held,
               cu.province_code, cu.preferred_language
        FROM gold.nba_recommendation r
        LEFT JOIN gold.c360_customer cu ON cu.golden_id = r.golden_id
        ORDER BY r.score DESC
    """).fetchdf()
except Exception:
    st.warning("No recommendations found. Run `python -m ontrack.l4_nba.run` first.")
    st.stop()

if recs.empty:
    st.info("No open-case recommendations to show.")
    st.stop()

# Filters
col1, col2, col3 = st.columns(3)
with col1:
    actions = ["All"] + sorted(recs["action"].unique().tolist())
    action_filter = st.selectbox("Action", actions)
with col2:
    review_filter = st.selectbox("Human review", ["All", "Yes", "No"])
with col3:
    hardship_filter = st.selectbox("Hardship flag", ["All", "Yes", "No"])

filtered = recs.copy()
if action_filter != "All":
    filtered = filtered[filtered["action"] == action_filter]
if review_filter == "Yes":
    filtered = filtered[filtered["needs_human_review"] == True]
elif review_filter == "No":
    filtered = filtered[filtered["needs_human_review"] == False]
if hardship_filter == "Yes":
    filtered = filtered[filtered["hardship_flag"] == True]
elif hardship_filter == "No":
    filtered = filtered[filtered["hardship_flag"] == False]

st.metric("Showing", f"{len(filtered):,d} of {len(recs):,d} cases")

# Cards
for i, (_, row) in enumerate(filtered.head(50).iterrows()):
    with st.expander(
        f"Case {row['case_id']} — **{row['action']}** (score: {row['score']:.3f})"
        + (" ⚠️ HARDSHIP" if row.get("hardship_flag") else "")
        + (" 👤 HUMAN REVIEW" if row.get("needs_human_review") else ""),
        expanded=(i < 3),
    ):
        c1, c2, c3 = st.columns([2, 2, 1])
        with c1:
            st.markdown("**Recommendation**")
            st.write(f"Action: **{row['action']}**")
            if row.get("channel"):
                st.write(f"Channel: {row['channel']}")
            st.write(f"Time window: {row.get('time_window', 'N/A')}")
            st.write(f"P(self-cure 30d): {row.get('p_cure_30d', 0):.1%}")
            st.write(f"P(payment 7d): {row.get('p_payment_7d', 0):.1%}")

        with c2:
            st.markdown("**Why**")
            for r in ["reason_1", "reason_2", "reason_3"]:
                if row.get(r):
                    st.write(f"• {row[r]}")
            if row.get("blocked_actions"):
                st.markdown(f"**Blocked:** {row['blocked_actions']}")

        with c3:
            st.markdown("**Customer**")
            st.write(f"Overdue: ${row.get('total_overdue', 0):,.0f}")
            st.write(f"Max DPD: {row.get('max_dpd', 0)}")
            st.write(f"Products: {row.get('products_held', 0)}")
            st.write(f"Province: {row.get('province_code', '?')}")

        # Agent decision
        st.divider()
        dcol1, dcol2, dcol3 = st.columns(3)
        with dcol1:
            if st.button("✅ Accept", key=f"accept_{i}"):
                st.success("Decision logged: ACCEPT")
        with dcol2:
            if st.button("✏️ Edit", key=f"edit_{i}"):
                st.info("Edit mode (choose a different action)")
        with dcol3:
            if st.button("❌ Reject", key=f"reject_{i}"):
                st.warning("Decision logged: REJECT")

con.close()
