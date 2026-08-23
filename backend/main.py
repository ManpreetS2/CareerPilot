"""CareerPilot AI FastAPI entrypoint."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.routes import applications, candidate, health, interview, jobs, scoring, tracker
from backend.core.config import settings
from backend.core.logging import setup_logging
from backend.db.init_db import init_db

logger = logging.getLogger(__name__)


def _browser_fake_materials(_prompt: str, _system_prompt: str | None = None) -> str:
    """Deterministic grounded JSON for the privacy-safe browser workflow only."""
    return json.dumps(
        {
            "tailored_bullets": ["Python is listed in the stored candidate skill evidence."],
            "cover_letter_draft": "Thank you for considering my application.",
            "recruiter_message": "I would welcome the chance to discuss this role.",
            "source_traceability_notes": ["Python <- candidate skills"],
        }
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging(settings.log_level)
    init_db()
    if os.environ.get("CAREERPILOT_BROWSER_FAKE_MATERIALS") == "1":
        app.state.application_materials_generator = _browser_fake_materials
        logger.info("browser_fake_materials enabled=1")
    logger.info("CareerPilot API started")
    yield


app = FastAPI(
    title="CareerPilot AI",
    description="AI-assisted job search and application copilot.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    # Unpacked extensions get a chrome-extension:// origin whose id varies
    # per install (no fixed manifest key) — matched by regex rather than an
    # exact origin. Local-only dev server, single machine, single user.
    allow_origin_regex=r"^chrome-extension://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(candidate.router)
app.include_router(jobs.router)
app.include_router(scoring.router)
app.include_router(applications.router)
app.include_router(tracker.router)
app.include_router(interview.router)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": "CareerPilot AI",
        "status": "running",
        "docs": "/docs",
        "health": "/health",
    }


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    # Ensure every error entry is JSON-serializable (Pydantic ctx may include Exception).
    safe_errors = []
    for err in exc.errors():
        item = dict(err)
        ctx = item.get("ctx")
        if isinstance(ctx, dict):
            item["ctx"] = {
                key: (str(value) if isinstance(value, BaseException) else value)
                for key, value in ctx.items()
            }
        safe_errors.append(item)
    return JSONResponse(status_code=422, content={"detail": safe_errors})


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled server error: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
