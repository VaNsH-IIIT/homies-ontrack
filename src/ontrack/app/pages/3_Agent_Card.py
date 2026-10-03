"""Agent card: the next best action for one case, why, what is blocked, and the agent's decision (owner: P3).

Search a case_id or golden_id (demo case CS-2026-583749), or pick from the queue.
Accept / edit / reject is written with common.record_decision() (edit and reject need a reason code).
"""
import pandas as pd
import streamlit as st

from ontrack.app.common import REASON_CODES, decisions, header, query, record_decision, table_exists

header("Agent card", "Next best action for an open collections case: AI recommends, rules constrain, you decide.")

if not table_exists("gold", "nba_recommendation"):
    st.warning("No recommendations yet. Run `python -m ontrack.l4_nba.run` first.")
    st.stop()

ACTIONS = ["call", "sms", "email", "push_notification", "reminder_letter", "specialist_agent",
           "hardship_referral", "do_nothing"]
LABEL = {"call": "📞 Call", "sms": "💬 SMS payment link", "email": "✉️ Email payment link",
         "push_notification": "📱 App push", "reminder_letter": "📮 Reminder letter",
         "specialist_agent": "🧑‍💼 Specialist agent", "hardship_referral": "🤝 Hardship referral",
         "do_nothing": "⏸️ No contact for now"}
DEMO_CASE = "CS-2026-583749"


def clean(row: pd.Series) -> dict:
    """NA-safe row: pandas NA / NaN become None, so truth tests never raise."""
    return row.astype(object).where(row.notna(), None).to_dict()


# ---- Book overview ----
mix = query("""SELECT action, count(*) AS n, sum(needs_human_review::INT) AS human FROM gold.nba_recommendation
               GROUP BY 1""").set_index("action")
total = int(mix["n"].sum())
m = st.columns(5)
m[0].metric("Open cases", f"{total:,}")
m[1].metric("Human-only queue", f"{int(mix['human'].sum()):,}", f"{mix['human'].sum() / total:.0%} of cases",
            delta_color="off", help="Hardship, vulnerability, dispute, complaint, holds and cease requests")
m[2].metric("Hardship referrals", f"{int(mix['n'].get('hardship_referral', 0)):,}")
m[3].metric("Calls today", f"{int(mix['n'].get('call', 0)):,}", "= daily call capacity", delta_color="off")
digital = int(sum(mix["n"].get(a, 0) for a in ("sms", "email", "push_notification")))
m[4].metric("Digital payment links", f"{digital:,}")

# ---- Find a case ----
q = st.text_input("Find a case by case_id or golden_id", value=DEMO_CASE,
                  help=f"Demo case {DEMO_CASE}. Clear the box to browse the queue.").strip()
if q:
    cases = query("SELECT case_id FROM gold.nba_recommendation WHERE case_id = ? OR golden_id = ? ORDER BY score DESC",
                  [q, q])
    if cases.empty:
        st.warning("No open case with that case_id or golden_id.")
        st.stop()
    case_ids = cases["case_id"].tolist()
else:
    f1, f2, f3 = st.columns(3)
    action_f = f1.selectbox("Action", ["All"] + ACTIONS)
    queue_f = f2.selectbox("Queue", ["All", "Human-only", "Automated"])
    cat_f = f3.selectbox("Routing reason", ["All", "hardship_case_flag", "hardship_text", "hardship_income",
                                            "vulnerability", "dispute", "complaint", "hold", "cease"])
    where, params = ["1=1"], []
    if action_f != "All":
        where.append("action = ?"); params.append(action_f)
    if queue_f != "All":
        where.append("needs_human_review = ?"); params.append(queue_f == "Human-only")
    if cat_f != "All":
        where.append("routing_category = ?"); params.append(cat_f)
    top = query(f"""SELECT case_id, action, round(score) AS dollars_at_risk, round(p_cure_30d, 2) AS self_cure,
                           routing_category FROM gold.nba_recommendation WHERE {' AND '.join(where)}
                    ORDER BY score DESC LIMIT 200""", params)
    st.caption("Highest dollars at risk first (overdue x chance it stays unpaid).")
    st.dataframe(top, hide_index=True, width="stretch", height=240)
    if top.empty:
        st.stop()
    case_ids = [st.selectbox("Open case", top["case_id"].tolist())]

if len(case_ids) > 1:
    case_ids = [st.selectbox(f"{len(case_ids)} open cases for this customer", case_ids)]

r = clean(query("""
    SELECT r.*, c.primary_product, c.case_open_date, cu.province_code, cu.products_held, cu.total_overdue, cu.open_case_count
    FROM gold.nba_recommendation r
    JOIN gold.case_360 c ON c.case_id = r.case_id
    LEFT JOIN gold.c360_customer cu ON cu.golden_id = r.golden_id
    WHERE r.case_id = ?""", [case_ids[0]]).iloc[0])

# ---- The card ----
st.divider()
st.markdown(f"### {r['case_id']} · {r['golden_id']}")
st.caption(f"{str(r.get('primary_product') or '').replace('_', ' ').capitalize()} · opened {r.get('case_open_date')} · "
           f"province {r.get('province_code') or '?'} · {r.get('open_case_count') or 0} open case(s) · "
           f"model {r.get('model_version')}")

if r.get("hardship_flag"):
    st.error(f"**Hardship: human decision required.** {r.get('routing_reasons') or ''}", icon="🤝")
    if r.get("text_evidence"):
        st.markdown(f"> *\"{r['text_evidence']}\"*  \n> — {r.get('text_source') or 'note / call'}")
elif r.get("needs_human_review"):
    st.warning(f"**Human review required.** {r.get('routing_reasons') or ''}", icon="🧑‍⚖️")

left, mid, right = st.columns([1.1, 1.6, 1])
with left:
    st.markdown("**Recommendation**")
    st.markdown(f"## {LABEL.get(r['action'], r['action'])}")
    st.write(f"Channel: **{r.get('channel') or '-'}**")
    st.write(f"When: **{r.get('time_window') or '-'}**")
    if r.get("service_notes"):
        st.info(r["service_notes"])
with mid:
    st.markdown("**Why**")
    for k in ("reason_1", "reason_2", "reason_3"):
        if r.get(k):
            st.markdown(f"- {r[k]}")
    if r.get("counterfactual"):
        st.caption(f"↪ {r['counterfactual']}")
with right:
    st.markdown("**Numbers**")
    st.metric("Overdue now", f"${(r.get('overdue_now') or 0):,.0f}")
    st.metric("Chance it self-cures in 30 days", f"{(r.get('p_cure_30d') or 0):.0%}")
    st.metric("Dollars at risk", f"${(r.get('score') or 0):,.0f}", help="Overdue x chance it stays unpaid: queue priority")

with st.expander(f"Blocked actions ({len((r.get('blocked_actions') or '').split(', ')) if r.get('blocked_actions') else 0})"
                 " and the rule behind each"):
    if r.get("blocked_reasons"):
        for item in r["blocked_reasons"].split("; "):
            a, _, why = item.partition(": ")
            st.markdown(f"- **{a}**: {why}")
    else:
        st.write("Nothing is blocked for this case.")
    st.caption(f"Allowed: {r.get('allowed_actions')}")

# ---- Decision ----
st.divider()
st.markdown("**Your decision**")
with st.form(f"decision_{r['case_id']}", clear_on_submit=False):
    d1, d2, d3 = st.columns([1, 1.2, 2])
    agent_action = d1.radio("Decision", ["accept", "edit", "reject"], horizontal=True)
    final = d2.selectbox("Action to take (edit)", [a for a in ACTIONS if a != r["action"]])
    reason = d3.selectbox("Reason code (needed to edit or reject)", [c for c in REASON_CODES if c != "agrees"])
    note = st.text_input("Note (optional)")
    if st.form_submit_button("Submit decision", type="primary"):
        final_action = r["action"] if agent_action == "accept" else (final if agent_action == "edit" else "do_nothing")
        try:
            did = record_decision(case_id=r["case_id"], golden_id=r["golden_id"], recommended_action=r["action"],
                                  agent_action=agent_action, final_action=final_action,
                                  reason_code="agrees" if agent_action == "accept" else reason, note=note,
                                  model_version=str(r.get("model_version") or ""))
            st.success(f"Logged {agent_action.upper()} → {final_action} (decision {did[:8]})")
        except ValueError as e:
            st.error(str(e))

hist = decisions(r["case_id"])
if len(hist):
    st.markdown("**Decision history for this case**")
    st.dataframe(hist[["ts", "agent_id", "recommended_action", "agent_action", "final_action", "reason_code", "note"]],
                 hide_index=True, width="stretch")
