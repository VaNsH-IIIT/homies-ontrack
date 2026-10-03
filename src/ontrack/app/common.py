"""Shared helpers for the Streamlit app (owner: P1). Pages import from here."""
import duckdb
import streamlit as st

from ontrack.db import DB_PATH

TAGLINE = "AI recommends. Rules constrain. Humans decide. Outcomes improve the next recommendation."


@st.cache_resource
def get_con() -> duckdb.DuckDBPyConnection:
    """One read-only connection for the whole app (the pipeline writes; the app only reads)."""
    return duckdb.connect(str(DB_PATH), read_only=True)


def query(sql: str, params: list | None = None):
    """Run a query on a fresh cursor and return a pandas DataFrame."""
    return get_con().cursor().execute(sql, params or []).df()


def table_exists(schema: str, name: str) -> bool:
    return bool(get_con().cursor().execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = ? AND table_name = ?",
        [schema, name]).fetchone()[0])


# ---------------------------------------------------------------------------------------------
# Decision log (human review / override). Kept in its own small database file so the app can
# write decisions while the main database stays read-only (pipelines can rebuild it meanwhile).
# ---------------------------------------------------------------------------------------------
from ontrack import config  # noqa: E402

DECISIONS_PATH = config.WORK_DIR / "decisions.duckdb"
REASON_CODES = ["agrees", "customer_hardship", "customer_requested_other_channel", "dispute_or_complaint",
                "wrong_contact_time", "already_paid_or_promised", "data_wrong", "other"]


def _decisions_con() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(DECISIONS_PATH))
    con.execute("""CREATE TABLE IF NOT EXISTS decision_log (
        decision_id VARCHAR, case_id VARCHAR, golden_id VARCHAR, agent_id VARCHAR,
        recommended_action VARCHAR, agent_action VARCHAR, final_action VARCHAR,
        reason_code VARCHAR, note VARCHAR, model_version VARCHAR, ts TIMESTAMP)""")
    return con


def record_decision(case_id: str, golden_id: str, recommended_action: str, agent_action: str,
                    final_action: str, reason_code: str, note: str = "", agent_id: str = "demo-agent",
                    model_version: str = "") -> str:
    """Log an agent's accept / edit / reject. Rejecting or editing requires a reason code."""
    if agent_action not in ("accept", "edit", "reject"):
        raise ValueError("agent_action must be accept, edit or reject")
    if agent_action != "accept" and (not reason_code or reason_code == "agrees"):
        raise ValueError("editing or rejecting a recommendation needs a reason code")
    import uuid
    decision_id = str(uuid.uuid4())
    con = _decisions_con()
    con.execute("INSERT INTO decision_log VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, now())",
                [decision_id, case_id, golden_id, agent_id, recommended_action, agent_action,
                 final_action, reason_code, note, model_version])
    con.close()
    return decision_id


def decisions(case_id: str | None = None):
    """Decision history as a DataFrame (all cases, or one case)."""
    con = _decisions_con()
    sql = "SELECT * FROM decision_log" + (" WHERE case_id = ?" if case_id else "") + " ORDER BY ts DESC"
    df = con.execute(sql, [case_id] if case_id else []).df()
    con.close()
    return df


def header(title: str, subtitle: str = "") -> None:
    st.set_page_config(page_title=f"OnTrack · {title}", page_icon="🧭", layout="wide")
    st.markdown(f"### 🧭 OnTrack · {title}")
    if subtitle:
        st.caption(subtitle)
