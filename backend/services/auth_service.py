"""Signup, login, and session lifecycle."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.security import (
    generate_session_token,
    hash_password,
    hash_session_token,
    verify_password,
)
from backend.db.models import User, UserSession

_MIN_PASSWORD_LENGTH = 8
_MAX_PASSWORD_LENGTH = 128


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def signup(db: Session, email: str, password: str) -> User:
    normalized_email = _normalize_email(email)
    if len(password) < _MIN_PASSWORD_LENGTH or len(password) > _MAX_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password does not meet length requirements.",
        )
    existing = db.query(User).filter(User.email == normalized_email).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    user = User(email=normalized_email, hashed_password=hash_password(password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Two concurrent signups for the same email both pass the
        # check above and race to insert — the unique index on
        # User.email is what actually enforces uniqueness. The loser
        # lands here instead of a 500: same 409 the check above would
        # have given it if it had lost the race a moment earlier.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        ) from None
    db.refresh(user)
    return user


# Precomputed so `authenticate` always pays the same argon2-verify cost,
# whether or not the email exists — otherwise a nonexistent email returns
# right after the SELECT while a wrong password additionally waits on a
# real hash verify, and that latency gap lets an attacker enumerate which
# emails have accounts just by timing login attempts.
_DUMMY_HASH = hash_password(generate_session_token())


def authenticate(db: Session, email: str, password: str) -> User | None:
    """None for either a nonexistent email or a wrong password — the two
    cases are handled identically (same response, same latency) so a login
    failure can't be used to probe which emails have accounts."""
    user = db.query(User).filter(User.email == _normalize_email(email)).first()
    if user is None:
        verify_password(password, _DUMMY_HASH)
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def create_session(db: Session, user: User) -> str:
    """Create a rotated server session and return the raw cookie token."""
    db.query(UserSession).filter(UserSession.user_id == user.id).delete()
    raw_token = generate_session_token()
    session = UserSession(
        token=hash_session_token(raw_token),
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.session_ttl_days),
    )
    db.add(session)
    db.commit()
    return raw_token


def get_user_by_token(db: Session, token: str) -> User | None:
    session = db.query(UserSession).filter(UserSession.token == hash_session_token(token)).first()
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
    db.query(UserSession).filter(UserSession.token == hash_session_token(token)).delete()
    db.commit()
