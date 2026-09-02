"""Auth API routes — signup, login, logout, current-user."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from backend.api.dependencies import get_current_user
from backend.core.config import settings
from backend.core.rate_limit import (
    RateLimited,
    clear_failed_login,
    peek_login_allowed,
    record_failed_login,
)
from backend.db.database import get_db
from backend.db.models import User
from backend.schemas.schemas import UserCreate, UserLogin, UserPublic
from backend.services import auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_ttl_days * 24 * 60 * 60,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


@router.post("/signup", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
def signup(payload: UserCreate, response: Response, db: Session = Depends(get_db)) -> UserPublic:
    user = auth_service.signup(db, payload.email, payload.password)
    token = auth_service.create_session(db, user)
    _set_session_cookie(response, token)
    return UserPublic.model_validate(user)


@router.post("/login", response_model=UserPublic)
def login(
    payload: UserLogin, request: Request, response: Response, db: Session = Depends(get_db)
) -> UserPublic:
    try:
        peek_login_allowed(request, payload.email)
    except RateLimited as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again later.",
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
    user = auth_service.authenticate(db, payload.email, payload.password)
    if user is None:
        try:
            record_failed_login(request, payload.email)
        except RateLimited:
            pass
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password."
        )
    clear_failed_login(request, payload.email)
    session = auth_service.create_session(db, user)
    _set_session_cookie(response, session)
    return UserPublic.model_validate(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> None:
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        try:
            auth_service.invalidate_session(db, token)
        except Exception as exc:  # noqa: BLE001 — logout must not look successful if revoke failed
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to end the session.",
            ) from exc
    response.delete_cookie(key=settings.session_cookie_name, path="/")


@router.get("/me", response_model=UserPublic)
def me(user: User = Depends(get_current_user)) -> UserPublic:
    return UserPublic.model_validate(user)
