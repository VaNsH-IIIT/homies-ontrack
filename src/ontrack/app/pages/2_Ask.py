"""Ask: plain-English questions over the C360, with the SQL or sources shown (owner: P2)."""
import json
import time
from datetime import date, datetime

import streamlit as st

from ontrack import config
from ontrack.app.common import get_con, header
from ontrack.l2_ask import ask, explain, llm, metrics, understand
from ontrack.l2_ask.warm_demo import PAGE_EXAMPLES

header("Ask", "Plain-English questions over collections data and policies. Every answer shows its SQL or its "
              "sources; protected or out-of-scope questions are refused.")

EXAMPLES = PAGE_EXAMPLES                     # shared with warm_demo, so every button is pre-answered
LOG = config.WORK_DIR / "ask_log.jsonl"
MAX_CHARS = 1000


@st.cache_resource
def engine() -> ask.Engine:
    return ask.Engine(get_con())


def md(text: str) -> str:
    """Streamlit reads `$...$` as LaTeX: "$770 a month ... $383.05" lost both dollar signs. Escape them."""
    return text.replace("$", "\\$")


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
question = " ".join((question or "").split())        # collapse whitespace / newlines
if not question:
    st.info("Type a question about collections cases, accounts, contacts, payments or policies, or pick one on "
            "the left.")
    st.stop()
if len(question) > MAX_CHARS:
    st.warning(f"That question is {len(question):,} characters long; only the first {MAX_CHARS:,} are used.")
    question = question[:MAX_CHARS]

# ---- Understood as: editable tokens (certified metrics) ----
u = understand.understand(question)
# Comparisons, rankings and multi-part questions go to the agent: no editable single-metric tokens for them.
multi_part = any("comparison" in x for x in u.unresolved)
explain_q = explain.match(question) is not None      # G20: case / customer explanations, no metric tokens
if explain_q:
    u.metric = None
if u.metric and u.metric in metrics.METRICS and u.metric != "roll_rate" and not multi_part:
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

STEP_LABELS = {"run_sql": "running a validated SQL query", "certified_metric": "computing a certified metric",
               "describe_table": "reading the data dictionary", "case_calls": "reading the case's recorded calls",
               "case_notes": "reading the case's agent notes", "search_documents": "searching the policy documents",
               "search_notes": "searching agent notes", "final_answer": "writing the answer"}

with st.status("Answering…", expanded=False) as status:
    t0 = time.time()
    try:
        eng = engine()
        eng.on_step = lambda n, name, act: status.update(            # live progress for slower agent answers
            label=f"Step {n}: {STEP_LABELS.get(name, name)}…", state="running")
        v = ask.scope.route(question)
        if v.refused:
            a = ask.Answer(f"{v.reason} {v.alternative}", "", True, "refuse", reason=v.category)
        elif u.metric and not u.unresolved and u.metric != "roll_rate" and not multi_part:
            a = eng.certified(u, question) or eng.answer(question)
        else:
            a = eng.answer(question)
    except Exception as e:  # noqa: BLE001 - never show a traceback to a user
        a = ask.Answer(f"Sorry, that question could not be answered ({type(e).__name__}). Try rephrasing it, or "
                       f"pick an example on the left.", "", False, "error")
    finally:
        try:
            engine().on_step = None
        except Exception:  # noqa: BLE001
            pass
    status.update(label=f"Answered in {time.time() - t0:.1f} s · route: {a.route}", state="complete")
try:
    log(question, a, u.tokens())
except OSError:
    pass

# ---- Answer ----
if a.refused:
    st.error(f"**Refused.** {md(a.answer.removeprefix('Refuse: '))}", icon="🛑")
    st.caption("Stopped before any SQL ran (scope guard), or by the SQL guard. Refusals are logged for review.")
    st.stop()

if a.route == "error":
    st.warning(md(a.answer))
    st.stop()

st.caption(f"Route: **{a.route}**" + (f" · certified metric `{a.understood_as.get('certified_metric')}`"
                                      if a.understood_as.get("certified_metric") else ""))
df = a.table
if a.route == "explain":
    st.markdown(md(a.answer.split("\n\n")[0]))
if df is not None and len(df):
    st.dataframe(df, hide_index=True, width="stretch")
    num = [c for c in df.columns[1:] if str(df[c].dtype).startswith(("float", "int"))]
    if len(df) > 1 and num and len(df) <= 60 and a.route != "explain":
        st.bar_chart(df.set_index(df.columns[0])[num[0]])
elif a.route not in ("explain",):
    st.markdown(md(a.answer))

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
