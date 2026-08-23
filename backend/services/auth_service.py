"""Signup, login, and session lifecycle."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.security import generate_session_token, hash_password, verify_password
from backend.db.models import User, UserSession

_MIN_PASSWORD_LENGTH = 8


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def signup(db: Session, email: str, password: str) -> User:
    normalized_email = _normalize_email(email)
    if len(password) < _MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Password must be at least {_MIN_PASSWORD_LENGTH} characters.",
        )
    existing = db.query(User).filter(User.email == normalized_email).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    user = User(email=normalized_email, hashed_password=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate(db: Session, email: str, password: str) -> User | None:
    """None for either a nonexistent email or a wrong password — the two
    cases are handled identically so a login failure can't be used to probe
    which emails have accounts."""
    user = db.query(User).filter(User.email == _normalize_email(email)).first()
    if user is None:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def create_session(db: Session, user: User) -> UserSession:
    session = UserSession(
        token=generate_session_token(),
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.session_ttl_days),
    )
    db.add(session)
    db.commit()
    return session


def get_user_by_token(db: Session, token: str) -> User | None:
    session = db.query(UserSession).filter(UserSession.token == token).first()
    if session is None:
        return None
    expires_at = session.expires_at
    # SQLite round-trips DateTime columns as naive (drops tzinfo even though
    # it was written as UTC-aware) — comparing that directly against an
    # aware "now" raises TypeError, so re-attach the UTC we know it was
    # stored as before comparing.
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        return None
    return db.query(User).filter(User.id == session.user_id).first()


def invalidate_session(db: Session, token: str) -> None:
    db.query(UserSession).filter(UserSession.token == token).delete()
    db.commit()
