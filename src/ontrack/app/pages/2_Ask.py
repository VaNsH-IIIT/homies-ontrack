"""Ask: plain-English questions over the C360, with the SQL or sources shown (owner: P2)."""
import json
from datetime import date, datetime

import streamlit as st

from ontrack import config
from ontrack.app.common import get_con, header
from ontrack.l2_ask import ask, llm, metrics, understand

header("Ask", "Plain-English questions over collections data and policies. Every answer shows its SQL or its "
              "sources; protected or out-of-scope questions are refused.")

EXAMPLES = [
    "What is the average days past due of open cases by queue?",
    "What was the right-party contact rate on outbound calls in September 2026, by local hour of day?",
    "How long does the 3-month reduced payment programme last, and what share of the payment is reduced?",
    "Why did outbound call volume drop on 23-24 September 2026?",
    "Rank customers by citizenship status so newcomers are called first.",
]
LOG = config.WORK_DIR / "ask_log.jsonl"


@st.cache_resource
def engine() -> ask.Engine:
    return ask.Engine(get_con())


def log(question: str, a: ask.Answer, tokens: dict) -> None:
    """Every question, answer route and refusal is logged for review (design: refusals logged and reviewed)."""
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": datetime.now().isoformat(timespec="seconds"), "question": question,
                            "route": a.route, "refused": a.refused, "reason": a.reason, "tokens": tokens,
                            "sql_or_sources": a.sql_or_sources[:2000]}, ensure_ascii=False) + "\n")


with st.sidebar:
    st.markdown("**Try**")
    for ex in EXAMPLES:
        if st.button(ex, key=ex, width="stretch"):
            st.session_state.q = ex
            st.session_state.pop("tokens", None)
    st.caption(f"LLM: {llm.backend() or 'none'} · {llm.MODEL}. Certified metrics need no LLM.")

question = st.text_input("Your question", key="q", placeholder="e.g. What is the hardship rate of cases opened "
                                                                 "in 2026, by primary product?")
if not question:
    st.stop()

# ---- Understood as: editable tokens (certified metrics) ----
u = understand.understand(question)
if u.metric and u.metric in metrics.METRICS and u.metric != "roll_rate":
    m = metrics.METRICS[u.metric]
    with st.expander("Understood as (edit and re-run)", expanded=True):
        c = st.columns([2, 1.2, 1.2, 1.6, 2.5])
        metric_ids = sorted(metrics.METRICS)
        u.metric = c[0].selectbox("Metric", metric_ids, index=metric_ids.index(u.metric))
        m = metrics.METRICS[u.metric]
        if m.date_col:
            s = c[1].date_input("From", value=date.fromisoformat(u.start) if u.start else None)
            e = c[2].date_input("To", value=date.fromisoformat(u.end) if u.end else None)
            u.start, u.end = (s.isoformat() if s else None), (e.isoformat() if e else None)
        else:
            c[1].caption("Snapshot metric")
            c[2].caption(f"as of {config.SNAPSHOT_DATE}")
            u.start = u.end = None
        dims = ["(none)"] + sorted(m.dims)
        g = c[3].selectbox("Group by", dims, index=dims.index(u.group_by) if u.group_by in dims else 0)
        u.group_by = None if g == "(none)" else g
        f = c[4].text_input("Extra filters (SQL, AND-ed)", value=" AND ".join(u.filters))
        u.filters = [x.strip() for x in f.split(" AND ") if x.strip()]
        u.unresolved = []
        st.caption("Dates resolve against the snapshot (28 Sep 2026), not today. Certified metrics come from "
                   "`metric_definitions` as fixed SQL: the same question always gives the same number.")

with st.spinner("Answering…"):
    eng = engine()
    v = ask.scope.route(question)
    if v.refused:
        a = ask.Answer(f"{v.reason} {v.alternative}", "", True, "refuse", reason=v.category)
    elif u.metric and not u.unresolved and u.metric != "roll_rate":
        a = eng.certified(u, question) or eng.answer(question)
    else:
        a = eng.answer(question)
log(question, a, u.tokens())

# ---- Answer ----
if a.refused:
    st.error(f"**Refused.** {a.answer.removeprefix('Refuse: ')}", icon="🛑")
    st.caption("Stopped before any SQL ran (scope guard), or by the SQL guard. Refusals are logged for review.")
    st.stop()

if a.route == "error":
    st.warning(a.answer)
    st.stop()

st.caption(f"Route: **{a.route}**" + (f" · certified metric `{a.understood_as.get('certified_metric')}`"
                                      if a.understood_as.get("certified_metric") else ""))
df = a.table
if a.route == "explain":
    st.markdown(a.answer.split("\n\n")[0])
if df is not None and len(df):
    st.dataframe(df, hide_index=True, width="stretch")
    num = [c for c in df.columns[1:] if str(df[c].dtype).startswith(("float", "int"))]
    if len(df) > 1 and num and len(df) <= 60:
        st.bar_chart(df.set_index(df.columns[0])[num[0]])
elif a.route not in ("explain",):
    st.markdown(a.answer)

# ---- Working: SQL or sources ----
if a.sql:
    st.markdown("**SQL that produced this answer** (validated: SELECT only, allow-listed tables and columns, no "
                "protected or personal columns, row cap)")
    st.code(a.sql, language="sql")
src = a.sql_or_sources if not a.sql else a.sql_or_sources.split("-- sources:")[-1] if "-- sources:" in \
    a.sql_or_sources else ""
if src.strip():
    try:
        cites = json.loads(src)
    except json.JSONDecodeError:
        cites = [src]
    st.markdown("**Sources:** " + " · ".join(f"`{c}`" for c in cites))
if a.understood_as and not a.understood_as.get("certified_metric"):
    st.caption("Understood as: " + ", ".join(f"{k} = {v}" for k, v in a.understood_as.items()))
