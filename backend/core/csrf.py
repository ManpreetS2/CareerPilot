"""Origin/Referer CSRF checks for cookie-authenticated mutating requests."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from backend.core.config import settings

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


class OriginCSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method.upper() in _SAFE_METHODS:
            return await call_next(request)
        if request.url.path.startswith("/api/extension/"):
            return await call_next(request)
        cookie_name = settings.session_cookie_name
        if cookie_name not in request.cookies:
            return await call_next(request)
        origin = request.headers.get("origin") or ""
        referer = request.headers.get("referer") or ""
        allowed = set(settings.cors_allow_origins)
        if origin:
            if origin not in allowed:
                return JSONResponse(status_code=403, content={"detail": "Invalid request origin."})
            return await call_next(request)
        if referer:
            if not any(referer.startswith(item.rstrip("/") + "/") or referer.rstrip("/") == item.rstrip("/") for item in allowed):
                return JSONResponse(status_code=403, content={"detail": "Invalid request origin."})
            return await call_next(request)
        host = (request.headers.get("host") or "").split(":")[0].lower()
        if host in {"testserver", "localhost", "127.0.0.1"}:
            return await call_next(request)
        return JSONResponse(status_code=403, content={"detail": "Missing request origin."})
