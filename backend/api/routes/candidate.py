"""Candidate and preference placeholder routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from backend.db.database import get_db
from backend.db.models import Candidate, TargetPreference
from backend.schemas.schemas import ParseResumeResponse, TargetPreferences
from backend.services.candidate_service import mock_preferences, parse_resume_placeholder

router = APIRouter(prefix="/api", tags=["candidate"])


@router.post("/parse-resume", response_model=ParseResumeResponse)
async def parse_resume(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> ParseResumeResponse:
    """Day 1 mock: accept a file upload and return a canned CandidateProfile."""
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Filename is required")
    candidate = parse_resume_placeholder(file.filename)
    record = Candidate(
        name=candidate.name,
        email=candidate.email,
        phone=candidate.phone,
        skills=candidate.skills,
        projects=[item.model_dump() for item in candidate.projects],
        experience=[item.model_dump() for item in candidate.experience],
        education=[item.model_dump() for item in candidate.education],
        certifications=candidate.certifications,
        strengths=candidate.strengths,
        evidence_links=candidate.evidence_links,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    candidate.id = f"cand-{record.id:03d}"
    return ParseResumeResponse(candidate=candidate, preferences=mock_preferences())


@router.post("/preferences", response_model=TargetPreferences, status_code=status.HTTP_201_CREATED)
def save_preferences(
    preferences: TargetPreferences,
    db: Session = Depends(get_db),
) -> TargetPreferences:
    """Validate preferences and persist them to SQLite."""
    if not preferences.target_roles:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one target role is required",
        )
    record = TargetPreference(
        target_roles=preferences.target_roles,
        preferred_locations=preferences.preferred_locations,
        remote_preference=preferences.remote_preference,
        salary_min=preferences.salary_min,
        work_authorization=preferences.work_authorization,
        sponsorship_required=preferences.sponsorship_required,
        constraints=preferences.constraints,
    )
    db.add(record)
    db.commit()
    return preferences
