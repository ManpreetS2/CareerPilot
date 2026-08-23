"""Shared FastAPI dependencies."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.db.database import get_db
from backend.db.models import User
from backend.services.auth_service import get_user_by_token


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    # The cookie is how the web app authenticates (set by /api/auth/login,
    # sent automatically by the browser on same-site requests). The header
    # is how the browser extension authenticates instead — see
    # settings.session_header_name for why the cookie alone doesn't reach it.
    token = request.cookies.get(settings.session_cookie_name) or request.headers.get(
        settings.session_header_name
    )
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not logged in.")
    user = get_user_by_token(db, token)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired or invalid.")
    return user
