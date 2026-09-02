"""Authenticated account lifecycle."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from backend.api.dependencies import get_current_user
from backend.core.config import settings
from backend.db.database import get_db
from backend.db.models import User
from backend.services.account_deletion import delete_user_account

router = APIRouter(prefix="/api/account", tags=["account"])


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """Delete the current user's private data and revoke every session.

    The caller cannot name another user. Shared job catalog rows are kept.
    """
    delete_user_account(db, user)
    response.delete_cookie(key=settings.session_cookie_name, path="/")
