"""Collections 360: look up one customer's golden record (owner: P1)."""
import streamlit as st

from ontrack.app.common import header, query

header("Collections 360", "One customer, one golden_id: every source system resolved, with match confidence and lineage.")

EXAMPLES = query("""SELECT c.golden_id FROM gold.c360_customer c
                    WHERE c.source_key_count >= 4 AND c.open_case_count > 0
                    ORDER BY c.golden_id LIMIT 5""").golden_id.tolist()

q = st.text_input("Find a customer by golden_id, CRM id, source key (card / loan / CIF) or account id",
                  value=EXAMPLES[0] if EXAMPLES else "",
                  help=f"Examples: {', '.join(EXAMPLES)}")
if not q:
    st.stop()
q = q.strip()

gid = query("""
    SELECT golden_id FROM gold.c360_customer WHERE golden_id = ?
    UNION SELECT golden_id FROM gold.customer_xref WHERE source_key = ?
    UNION SELECT golden_id FROM gold.c360_account WHERE account_id = ?
    LIMIT 1""", [q, q, q])
if gid.empty:
    st.warning("No customer found for that id.")
    st.stop()
gid = gid.golden_id.iloc[0]

cust = query("SELECT * FROM gold.c360_customer WHERE golden_id = ?", [gid]).iloc[0]
st.markdown(f"## {gid}")
m = st.columns(6)
m[0].metric("Products", int(cust.products_held))
m[1].metric("Total exposure", f"${cust.total_exposure:,.0f}")
m[2].metric("Total overdue", f"${cust.total_overdue:,.0f}")
m[3].metric("Max DPD", int(cust.max_dpd))
m[4].metric("Open cases", int(cust.open_case_count))
m[5].metric("Lowest match confidence", f"{cust.match_confidence_min:.2f}")

def chip(ok: bool, yes: str, no: str) -> str:
    return f"🟢 {yes}" if ok else f"🔴 {no}"

st.markdown(" · ".join([
    chip(cust.consent_call, "call OK", "no call consent"),
    chip(cust.consent_sms, "SMS OK", "no SMS consent"),
    chip(cust.consent_email, "email OK", "no email consent"),
    chip(not cust.internal_do_not_call_flag, "no do-not-call", "do-not-call"),
    chip(not cust.cease_communication_flag, "no cease request", "cease request"),
    chip(not cust.insolvency_flag, "no insolvency", "insolvency hold"),
    chip(not cust.third_party_hold_flag, "no third-party hold", "third-party hold"),
    "🟠 vulnerable: specialist only" if cust.vulnerability_flag else "",
]))
st.caption(f"Province {cust.province_code} · time zone {cust.time_zone} · language {cust.preferred_language} · "
           f"data quality: {cust._dq_status} · loaded {cust._loaded_at:%Y-%m-%d %H:%M}")

st.markdown("#### Identity resolution: how each source key was linked")
st.dataframe(query("""SELECT source_system AS system, source_key AS "source key", match_method AS method,
                             round(match_confidence, 3) AS confidence
                      FROM gold.customer_xref WHERE golden_id = ? ORDER BY system""", [gid]),
             hide_index=True, width="stretch")

st.markdown("#### Accounts")
st.dataframe(query("""SELECT account_id, product_type, round(balance, 2) AS balance, round(credit_limit, 2) AS "limit",
                             round(past_due_amount, 2) AS past_due, dpd, dpd_bucket, account_status, snapshot_date
                      FROM gold.c360_account WHERE golden_id = ? ORDER BY dpd DESC NULLS LAST""", [gid]),
             hide_index=True, width="stretch")

st.markdown("#### Collections cases")
st.dataframe(query("""SELECT case_id, case_status, primary_product, current_bucket, current_dpd, total_overdue,
                             current_treatment, hardship_flag, outcome, case_open_date
                      FROM gold.case_360 WHERE golden_id = ? ORDER BY case_open_date DESC""", [gid]),
             hide_index=True, width="stretch")

st.markdown("#### Contact timeline (latest 25)")
st.dataframe(query("""SELECT contact_ts_utc, channel, direction, outcome_code, rpc_flag, payment_taken_flag,
                             case_id, note_id, transcript_id
                      FROM gold.contact_timeline WHERE golden_id = ?
                      ORDER BY contact_ts_utc DESC LIMIT 25""", [gid]),
             hide_index=True, width="stretch")
st.caption("Names, dates of birth and contact details are excluded from gold (restricted PII schema); "
           "an agent sees them only for cases assigned to them.")
