"""Interview-prep Day 1 mocks."""

from __future__ import annotations

from backend.schemas.schemas import InterviewPrep
from backend.services.job_service import get_job


def mock_interview_prep(job_id: str) -> InterviewPrep:
    job = get_job(job_id)
    return InterviewPrep(
        job_id=job.id or job_id,
        likely_questions=[
            "Walk me through a Python API you built.",
            "How would you model this job's data in SQL?",
            "Tell me about a time you got stuck and how you unblocked.",
        ],
        talking_points=[
            f"Connect Campus Connect work to {job.company}'s stack.",
            "Highlight tests and latency improvement from the intern role.",
        ],
        gaps_to_address=[
            "No production Kubernetes experience yet (mock gap).",
        ],
    )
