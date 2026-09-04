"""Saved Searches and Job Alerts routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.api.dependencies import get_current_user
from backend.api.profile_gate import enforce_profile_ready
from backend.db.database import get_db
from backend.db.models import User
from backend.schemas.saved_search import (
    SavedSearchCreate,
    SavedSearchItem,
    SavedSearchMatchItem,
    SavedSearchUpdate,
)
from backend.services.job_posting_time import posted_date_for_display
from backend.services.saved_search_service import (
    SavedSearchError,
    SavedSearchNotFoundError,
    create_saved_search,
    delete_saved_search,
    list_matches,
    list_saved_searches,
    mark_matches_seen,
    update_saved_search,
)

router = APIRouter(prefix="/api", tags=["saved-searches"])


def _http_for_saved_search_error(exc: Exception) -> HTTPException:
    if isinstance(exc, SavedSearchNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, SavedSearchError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    raise exc


def _to_item(record, unseen_match_count: int = 0) -> SavedSearchItem:
    return SavedSearchItem(
        id=record.id,
        label=record.label,
        query_text=record.query_text,
        location=record.location,
        opportunity=record.opportunity,
        employment_type=list(record.employment_type or []),
        work_mode=list(record.work_mode or []),
        date_posted=record.date_posted,
        cadence_hours=record.cadence_hours,
        enabled=record.enabled,
        last_run_at=record.last_run_at,
        created_at=record.created_at,
        unseen_match_count=unseen_match_count,
    )


@router.post("/saved-searches", response_model=SavedSearchItem, status_code=status.HTTP_201_CREATED)
def create_saved_search_route(
    payload: SavedSearchCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SavedSearchItem:
    """Persists a search the background scheduler will rerun on its own —
    same profile-first gate as a live "Find Jobs" click, since this is
    just an unattended trigger for that same discovery pipeline."""
    enforce_profile_ready(db, user.id)
    record = create_saved_search(db, user.id, payload)
    return _to_item(record)


@router.get("/saved-searches", response_model=list[SavedSearchItem])
def list_saved_searches_route(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[SavedSearchItem]:
    return [_to_item(record, unseen) for record, unseen in list_saved_searches(db, user.id)]


@router.patch("/saved-searches/{search_id}", response_model=SavedSearchItem)
def update_saved_search_route(
    search_id: int,
    payload: SavedSearchUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SavedSearchItem:
    try:
        record = update_saved_search(db, search_id, user.id, payload)
    except Exception as exc:  # noqa: BLE001 — map to sanitized HTTP
        raise _http_for_saved_search_error(exc) from exc
    return _to_item(record)


@router.delete("/saved-searches/{search_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved_search_route(
    search_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> None:
    try:
        delete_saved_search(db, search_id, user.id)
    except Exception as exc:  # noqa: BLE001 — map to sanitized HTTP
        raise _http_for_saved_search_error(exc) from exc


@router.get("/saved-searches/{search_id}/matches", response_model=list[SavedSearchMatchItem])
def list_saved_search_matches_route(
    search_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[SavedSearchMatchItem]:
    try:
        rows = list_matches(db, search_id, user.id)
    except Exception as exc:  # noqa: BLE001 — map to sanitized HTTP
        raise _http_for_saved_search_error(exc) from exc
    return [
        SavedSearchMatchItem(
            job_id=job.public_id,
            title=job.title,
            company=job.company,
            location=job.location,
            url=job.url,
            source=job.source,
            date_posted=posted_date_for_display(job.date_posted),
            first_seen_at=match.first_seen_at,
            seen_at=match.seen_at,
        )
        for match, job in rows
    ]


@router.post("/saved-searches/{search_id}/matches/seen", response_model=dict)
def mark_saved_search_matches_seen_route(
    search_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    try:
        updated = mark_matches_seen(db, search_id, user.id)
    except Exception as exc:  # noqa: BLE001 — map to sanitized HTTP
        raise _http_for_saved_search_error(exc) from exc
    return {"updated": updated}
