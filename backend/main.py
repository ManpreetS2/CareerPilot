"""CareerPilot AI FastAPI entrypoint."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.routes import account, applications, auth, candidate, career_growth, health, interview, jobs, scoring, tracker
from backend.core.config import settings, validate_runtime_settings
from backend.core.csrf import OriginCSRFMiddleware
from backend.core.logging import setup_logging
from backend.core.security_headers import SecurityHeadersMiddleware
from backend.db.init_db import init_db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging(settings.log_level)
    validate_runtime_settings()
    init_db()
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
    allow_origins=settings.cors_allow_origins,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(OriginCSRFMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(account.router)
app.include_router(candidate.router)
app.include_router(jobs.router)
app.include_router(scoring.router)
app.include_router(applications.router)
app.include_router(tracker.router)
app.include_router(interview.router)
app.include_router(career_growth.router)


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
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=dict(exc.headers) if exc.headers else None,
    )


_SENSITIVE_LOC = {
    "password",
    "token",
    "secret",
    "authorization",
    "cookie",
    "api_key",
    "apikey",
    "session",
}


def _sanitize_validation_errors(errors: list[dict]) -> list[dict]:
    sanitized: list[dict] = []
    for err in errors:
        item = dict(err)
        item.pop("input", None)
        loc = [str(part).lower() for part in item.get("loc", ())]
        sensitive = any(key in part for part in loc for key in _SENSITIVE_LOC)
        ctx = item.get("ctx")
        if isinstance(ctx, dict):
            cleaned: dict[str, object] = {}
            for key, value in ctx.items():
                if isinstance(value, BaseException):
                    cleaned[key] = type(value).__name__
                elif sensitive or key.lower() in _SENSITIVE_LOC:
                    cleaned[key] = "[redacted]"
                else:
                    cleaned[key] = value
            item["ctx"] = cleaned
        sanitized.append(item)
    return sanitized


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"detail": _sanitize_validation_errors(exc.errors())},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled server error type=%s", type(exc).__name__)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
