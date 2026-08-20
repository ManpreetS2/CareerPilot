"""Jobs page — Day 1 dummy listings from FastAPI."""

from __future__ import annotations

import streamlit as st

from api_client import BackendError, client

st.set_page_config(page_title="Jobs · CareerPilot AI", page_icon="✈️", layout="wide")

st.title("Jobs")
st.caption("Day 1: jobs and match scores are mock data from FastAPI.")

if st.button("Refresh jobs", type="primary"):
    st.session_state.pop("jobs", None)
    st.session_state.pop("job_scores", None)

try:
    jobs = st.session_state.get("jobs") or client.list_jobs()
    st.session_state["jobs"] = jobs
except BackendError as exc:
    st.error(str(exc))
    st.stop()

if not jobs:
    st.info("No jobs returned.")
    st.stop()

scores: dict[str, dict] = st.session_state.get("job_scores") or {}
for job in jobs:
    job_id = job.get("id")
    if job_id and job_id not in scores:
        try:
            scores[job_id] = client.score_job(job_id)
        except BackendError as exc:
            scores[job_id] = {"error": str(exc)}
st.session_state["job_scores"] = scores

for job in jobs:
    job_id = job.get("id") or ""
    match = scores.get(job_id, {})
    with st.container(border=True):
        top, right = st.columns([3, 1])
        with top:
            st.subheader(job.get("title", "Untitled role"))
            st.write(f"**{job.get('company', 'Unknown')}** · {job.get('location') or 'Location n/a'}")
            st.caption(job.get("description", ""))
        with right:
            overall = match.get("overall_score")
            st.metric("Match", f"{overall:.0f}" if isinstance(overall, (int, float)) else "—")
            st.write(match.get("recommendation", job.get("status", "")).title())
        if st.button("Select for application", key=f"select-{job_id}"):
            st.session_state["selected_job_id"] = job_id
            st.success(f"Selected {job_id}. Open the Application page.")
