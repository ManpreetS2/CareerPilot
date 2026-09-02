"""Delete one authenticated user's private data and revoke every session.

Shared job catalog rows and job intelligence stay. Those are not owned by
the deleting user.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from backend.db.models import (
    ApplicationPackageRecord,
    ApplicationTrackerRecord,
    Candidate,
    FormFillAttemptRecord,
    InterviewPrepRecord,
    MatchEvidenceRecord,
    MatchScoreRecord,
    ResumeVersionRecord,
    SavedJobRecord,
    TargetPreference,
    User,
    UserSession,
)


def _candidate_ids(db: Session, user_id: int) -> list[int]:
    return [
        row[0]
        for row in db.query(Candidate.id).filter(Candidate.user_id == user_id).all()
    ]


def delete_user_account(db: Session, user: User) -> None:
    """Erase owner-scoped rows, then the User. Commits once at the end."""
    user_id = user.id
    candidate_ids = _candidate_ids(db, user_id)

    db.query(MatchEvidenceRecord).filter(MatchEvidenceRecord.user_id == user_id).delete(
        synchronize_session=False
    )
    if candidate_ids:
        db.query(MatchScoreRecord).filter(MatchScoreRecord.candidate_id.in_(candidate_ids)).delete(
            synchronize_session=False
        )
        db.query(ApplicationPackageRecord).filter(
            ApplicationPackageRecord.candidate_id.in_(candidate_ids)
        ).delete(synchronize_session=False)
        db.query(ResumeVersionRecord).filter(
            ResumeVersionRecord.candidate_id.in_(candidate_ids)
        ).delete(synchronize_session=False)

    db.query(ApplicationPackageRecord).filter(ApplicationPackageRecord.user_id == user_id).delete(
        synchronize_session=False
    )
    db.query(ResumeVersionRecord).filter(ResumeVersionRecord.user_id == user_id).delete(
        synchronize_session=False
    )
    db.query(FormFillAttemptRecord).filter(FormFillAttemptRecord.user_id == user_id).delete(
        synchronize_session=False
    )
    db.query(ApplicationTrackerRecord).filter(ApplicationTrackerRecord.user_id == user_id).delete(
        synchronize_session=False
    )
    db.query(InterviewPrepRecord).filter(InterviewPrepRecord.user_id == user_id).delete(
        synchronize_session=False
    )
    db.query(SavedJobRecord).filter(SavedJobRecord.user_id == user_id).delete(
        synchronize_session=False
    )
    db.query(TargetPreference).filter(TargetPreference.user_id == user_id).delete(
        synchronize_session=False
    )
    db.query(Candidate).filter(Candidate.user_id == user_id).delete(synchronize_session=False)
    db.query(UserSession).filter(UserSession.user_id == user_id).delete(synchronize_session=False)
    db.query(User).filter(User.id == user_id).delete(synchronize_session=False)
    db.commit()
