"""CareerPilot AI — Streamlit home."""

from __future__ import annotations

import streamlit as st

from api_client import BackendError, client

st.set_page_config(page_title="CareerPilot AI", page_icon="✈️", layout="wide")

st.title("CareerPilot AI")
st.caption("AI-assisted job search copilot — Day 1 scaffold")

st.markdown(
    """
Use the sidebar pages to walk the **dummy** Day 1 flow:

1. **Upload** — send a resume file to the mock `/parse-resume` API
2. **Jobs** — review mock discovered roles and fit scores
3. **Application** — review mock tailored bullets and approve / edit / reject
"""
)

col_a, col_b = st.columns(2)
with col_a:
    st.subheader("Backend")
    try:
        health = client.health()
        st.success(f"Connected · {health.get('status')} · db {health.get('database')}")
    except BackendError as exc:
        st.error(str(exc))

with col_b:
    st.subheader("Day 1 scope")
    st.info(
        "Resume parsing, job scraping, fit scoring, Playwright apply, and OCR "
        "are **not implemented**. APIs return realistic mock data."
    )
