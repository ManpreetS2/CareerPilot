"""Shared FastAPI dependencies."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.db.database import get_db
from backend.db.models import User
from backend.services.auth_service import get_user_by_token


def _user_from_token(db: Session, token: str | None) -> User:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not logged in.")
    user = get_user_by_token(db, token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid.",
        )
    return user


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Web routes authenticate only from the HttpOnly session cookie."""
    return _user_from_token(db, request.cookies.get(settings.session_cookie_name))


def get_extension_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Extension autofill authenticates only from the configured session header."""
    return _user_from_token(db, request.headers.get(settings.session_header_name))
