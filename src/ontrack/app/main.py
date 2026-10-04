"""OnTrack demo app (owner: P1). Run: streamlit run src/ontrack/app/main.py

Lists the pages so the sidebar reads "Home" (not the file name) and keeps each page's URL:
  home.py (P1) · pages/1_C360.py, pages/1_Match_Review.py (P1) · pages/2_Ask.py (P2) · pages/3_Agent_Card.py (P3)
"""
import streamlit as st

st.navigation([
    st.Page("home.py", title="Home", icon="🧭", default=True),
    st.Page("pages/1_C360.py", title="C360", url_path="C360"),
    st.Page("pages/1_Match_Review.py", title="Match Review", url_path="Match_Review"),
    st.Page("pages/2_Ask.py", title="Ask", url_path="Ask"),
    st.Page("pages/3_Agent_Card.py", title="Agent Card", url_path="Agent_Card"),
]).run()
