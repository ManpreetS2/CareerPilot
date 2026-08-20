"""Application page — Day 1 mock materials and human approval."""

from __future__ import annotations

import streamlit as st

from api_client import BackendError, client

st.set_page_config(page_title="Application · CareerPilot AI", page_icon="✈️", layout="wide")

st.title("Application")
st.caption("Day 1: tailored bullets and approval are mock FastAPI responses.")

DEFAULT_JOB_ID = "job-001"
job_id = st.session_state.get("selected_job_id") or DEFAULT_JOB_ID

try:
    job = client.get_job(job_id)
    materials = client.generate_materials(job_id)
except BackendError as exc:
    st.error(str(exc))
    st.stop()

st.subheader(job.get("title", "Selected role"))
st.write(f"**{job.get('company')}** · {job.get('location') or 'Location n/a'}")
st.caption(job.get("url", ""))

status = materials.get("approval_status", "draft")
st.info(f"Approval state: **{status}**")

st.markdown("#### Tailored resume bullets (mock)")
for bullet in materials.get("tailored_bullets", []):
    st.markdown(f"- {bullet}")

with st.expander("Cover letter draft"):
    st.write(materials.get("cover_letter_draft") or "None")

with st.expander("Recruiter message"):
    st.write(materials.get("recruiter_message") or "None")

with st.expander("Source traceability"):
    for note in materials.get("source_traceability_notes", []):
        st.write(f"- {note}")

st.markdown("#### Human approval")
col_a, col_b, col_c = st.columns(3)
decision = None
with col_a:
    if st.button("Approve", type="primary", use_container_width=True):
        decision = "approved"
with col_b:
    if st.button("Edit", use_container_width=True):
        decision = "edit_requested"
with col_c:
    if st.button("Reject", use_container_width=True):
        decision = "rejected"

if decision:
    try:
        result = client.approve_job(job_id, decision)
        st.success(result.get("message", f"Marked {decision}"))
        st.json(result)
    except BackendError as exc:
        st.error(str(exc))
