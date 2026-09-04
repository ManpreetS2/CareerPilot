"""Saved Searches and Job Alerts contracts."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class SavedSearchCreate(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    query_text: str = Field(min_length=1, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    opportunity: str | None = None
    employment_type: list[str] = Field(default_factory=list)
    work_mode: list[str] = Field(default_factory=list)
    date_posted: str | None = None
    cadence_hours: int = 12


class SavedSearchUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=200)
    enabled: bool | None = None
    cadence_hours: int | None = None


class SavedSearchItem(BaseModel):
    id: int
    label: str
    query_text: str
    location: str | None = None
    opportunity: str | None = None
    employment_type: list[str] = Field(default_factory=list)
    work_mode: list[str] = Field(default_factory=list)
    date_posted: str | None = None
    cadence_hours: int
    enabled: bool
    last_run_at: datetime | None = None
    created_at: datetime
    unseen_match_count: int = 0


class SavedSearchMatchItem(BaseModel):
    job_id: str
    title: str
    company: str
    location: str | None = None
    url: str
    source: str
    date_posted: date | None = None
    first_seen_at: datetime
    seen_at: datetime | None = None
