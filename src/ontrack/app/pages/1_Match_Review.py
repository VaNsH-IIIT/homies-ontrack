"""Match review: the data steward approves or rejects grey-zone identity matches (owner: P1).

Splink scores between 0.80 and 0.95 are never merged automatically. A steward sees the field-by-field
evidence (masked: initials, birth year, postal FSA) and decides; the next pipeline build links approved
pairs (method 'steward_approved') and keeps rejected ones apart.
"""
import pandas as pd
import streamlit as st

from ontrack.app.common import (STEWARD_REASONS, header, query, record_steward_decision, steward_decisions,
                                table_exists)

header("Match review", "Grey-zone identity matches (Splink 0.80–0.95) wait for a data steward. Nothing is merged "
                       "until a person approves it.")

if "steward_msg" in st.session_state:
    st.success(st.session_state.pop("steward_msg"))

if not table_exists("gold", "match_review_queue"):
    st.info("No review queue yet: run `python -m ontrack.l1_factory.build`.")
    st.stop()

queue = query("SELECT * FROM gold.match_review_queue")
if "dob_check" not in queue.columns:
    st.info("This queue was built before match evidence was added: re-run `python -m ontrack.l1_factory.build`.")
    st.stop()

# Decisions made since the last build are live here; the build turns them into links.
log = steward_decisions()
key = ["source_system", "source_key", "candidate_crm_customer_id"]
if not log.empty:
    queue = queue.merge(log[key + ["decision", "reason_code", "ts"]], on=key, how="left")
    queue["status"] = queue.decision.fillna(queue.steward_status)
else:
    queue["status"] = queue.steward_status

m = st.columns(4)
m[0].metric("In the queue", f"{len(queue):,}")
m[1].metric("Pending", f"{(queue.status == 'pending').sum():,}")
m[2].metric("Approved", f"{(queue.status == 'approved').sum():,}", help="Linked on the next build")
m[3].metric("Rejected", f"{(queue.status == 'rejected').sum():,}", help="Never linked")

if table_exists("silver", "splink_validation"):
    v = query("SELECT * FROM silver.splink_validation").iloc[0]
    st.caption(f"Why there is a queue: above 0.95 Splink links automatically (precision {v.precision:.2%} and "
               f"recall {v.recall:.2%} on {int(v.holdout_keys):,} keys with known owners). Below 0.95 the model "
               "is unsure, so a person decides.")

f = st.columns(3)
systems = f[0].multiselect("Source system", sorted(queue.source_system.unique()), default=sorted(queue.source_system.unique()))
status = f[1].selectbox("Status", ["pending", "approved", "rejected", "all"])
lo, hi = f[2].slider("Match probability", 0.80, 0.95, (0.80, 0.95), step=0.01)
view = queue[queue.source_system.isin(systems) & queue.match_probability.between(lo, hi)]
if status != "all":
    view = view[view.status == status]
view = view.sort_values("match_probability", ascending=False).reset_index(drop=True)

cols = ["status", "source_system", "source_key", "candidate_crm_customer_id", "match_probability",
        "surname_similarity", "given_initial_match", "dob_check", "postal_edit_distance", "phone_match"]
st.markdown(f"#### {len(view):,} matches")
picked = st.dataframe(view[cols], hide_index=True, width="stretch", height=280,
                      on_select="rerun", selection_mode="single-row")
rows = picked.selection.rows
if not rows:
    st.caption("Select a row to review it.")
    st.stop()
r = view.iloc[rows[0]]


def yes_no(v) -> str:
    return "—" if pd.isna(v) else ("✅ same" if v else "❌ differs")


st.markdown(f"#### {r.source_system} `{r.source_key}` → CRM `{r.candidate_crm_customer_id}` · "
            f"probability **{r.match_probability:.3f}** (weight {r.match_weight:+.2f})")
st.table({
    "Field": ["Surname", "Given-name initial", "Date of birth", "Postal code", "Phone"],
    "CRM record": [r.crm_surname_masked or "—", "", "", r.crm_postal_fsa or "—", ""],
    "Source record": [r.source_surname_masked or "—", "", "", r.source_postal_fsa or "—", ""],
    "Evidence": ["—" if pd.isna(r.surname_similarity) else f"Jaro-Winkler {r.surname_similarity:.3f}",
                 yes_no(r.given_initial_match), r.dob_check,
                 "—" if pd.isna(r.postal_edit_distance)
                 else f"{int(r.postal_edit_distance)} character(s) apart",
                 yes_no(r.phone_match)],
})
st.caption("Values are masked (initial and length, postal FSA only): gold holds no names, dates of birth or "
           "contact details. A steward who needs the full record opens it in the source system.")

target = query("SELECT golden_id FROM gold.customer_xref WHERE source_system = 'crm' AND source_key = ?",
               [r.candidate_crm_customer_id])
if not target.empty:
    gid = target.golden_id.iloc[0]
    c = query("""SELECT products_held, open_case_count, source_key_count, _source_systems
                 FROM gold.c360_customer WHERE golden_id = ?""", [gid])
    if not c.empty:
        c = c.iloc[0]
        st.caption(f"If approved, `{r.source_key}` joins {gid}: today {int(c.source_key_count)} source keys "
                   f"({', '.join(c._source_systems)}), {int(c.products_held)} products, "
                   f"{int(c.open_case_count)} open case(s).")

d = st.radio("Decision", ["approved", "rejected"], horizontal=True,
             format_func=lambda x: "Approve: same person" if x == "approved" else "Reject: different people")
with st.form("steward", clear_on_submit=True):
    reason = st.selectbox("Reason", STEWARD_REASONS[d])
    note = st.text_input("Note (optional)")
    if st.form_submit_button("Record decision", type="primary"):
        try:
            record_steward_decision(r.source_system, r.source_key, r.candidate_crm_customer_id,
                                    float(r.match_probability), d, reason, note)
            st.session_state["steward_msg"] = f"Recorded for {r.source_key}: {d} ({reason}). The next build applies it."
            st.rerun()
        except ValueError as e:
            st.error(str(e))

if not log.empty:
    st.markdown("#### Decision log")
    st.dataframe(log[["ts", "decision", "reason_code", "source_system", "source_key", "candidate_crm_customer_id",
                      "match_probability", "steward_id", "note"]], hide_index=True, width="stretch")
