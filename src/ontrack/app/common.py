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


def header(title: str, subtitle: str = "") -> None:
    st.set_page_config(page_title=f"OnTrack · {title}", page_icon="🧭", layout="wide")
    st.markdown(f"### 🧭 OnTrack · {title}")
    if subtitle:
        st.caption(subtitle)
