"""Auth API routes — signup, login, logout, current-user."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from backend.api.dependencies import get_current_user
from backend.core.config import settings
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
    session = auth_service.create_session(db, user)
    _set_session_cookie(response, session.token)
    return UserPublic.model_validate(user)


@router.post("/login", response_model=UserPublic)
def login(payload: UserLogin, response: Response, db: Session = Depends(get_db)) -> UserPublic:
    user = auth_service.authenticate(db, payload.email, payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password."
        )
    session = auth_service.create_session(db, user)
    _set_session_cookie(response, session.token)
    return UserPublic.model_validate(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> None:
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        # Invalidate server-side first — clearing only the client cookie
        # would let a stolen/copied cookie keep working after "logout".
        auth_service.invalidate_session(db, token)
    response.delete_cookie(key=settings.session_cookie_name, path="/")


@router.get("/me", response_model=UserPublic)
def me(user: User = Depends(get_current_user)) -> UserPublic:
    return UserPublic.model_validate(user)
