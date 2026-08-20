"""Upload / candidate page — Day 1 mock parse-resume flow."""

from __future__ import annotations

import streamlit as st

from api_client import BackendError, client

st.set_page_config(page_title="Upload · CareerPilot AI", page_icon="✈️", layout="wide")

st.title("CareerPilot AI")
st.header("Upload / Candidate")
st.caption("Day 1: submitting calls the mock FastAPI `/api/parse-resume` endpoint.")

uploaded = st.file_uploader("Resume PDF", type=["pdf"], accept_multiple_files=False)

col1, col2 = st.columns(2)
with col1:
    target_roles = st.text_input(
        "Target roles",
        value="Software Engineer Intern, Backend Engineer Intern",
        help="Comma-separated",
    )
    location = st.text_input("Preferred location", value="San Francisco, CA")
with col2:
    salary_min = st.number_input("Salary minimum (hourly USD)", min_value=0, value=35, step=1)
    work_auth = st.selectbox(
        "Work authorization",
        ["US Citizen", "US Permanent Resident", "Requires sponsorship", "Other"],
    )

submitted = st.button("Build candidate profile", type="primary", use_container_width=True)

if submitted:
    if uploaded is None:
        st.warning("Upload a PDF to continue. The file is not parsed on Day 1, but the API expects it.")
    else:
        try:
            result = client.parse_resume(
                filename=uploaded.name,
                file_bytes=uploaded.getvalue(),
                content_type=uploaded.type or "application/pdf",
            )
            preferences = {
                "target_roles": [item.strip() for item in target_roles.split(",") if item.strip()],
                "preferred_locations": [location] if location else [],
                "salary_min": int(salary_min),
                "work_authorization": work_auth,
                "sponsorship_required": work_auth == "Requires sponsorship",
                "constraints": [],
            }
            saved_prefs = client.save_preferences(preferences)
            st.session_state["candidate"] = result.get("candidate", result)
            st.session_state["preferences"] = saved_prefs
            st.success("Mock candidate profile loaded from FastAPI.")
        except BackendError as exc:
            st.error(str(exc))

candidate = st.session_state.get("candidate")
if candidate:
    st.subheader("Candidate profile")
    st.json(candidate)
    if st.session_state.get("preferences"):
        st.subheader("Saved preferences")
        st.json(st.session_state["preferences"])
else:
    st.info("No profile yet. Upload a PDF and submit to fetch mock data from the backend.")
