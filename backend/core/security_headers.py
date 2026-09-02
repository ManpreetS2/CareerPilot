"""Environment-aware security headers for the API process.

The React UI is served by Vite (dev) or a static host, not this FastAPI app.
Headers here apply to API JSON, /health, and /docs.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from backend.core.config import settings

_DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")

# API JSON does not execute scripts. /docs (Swagger UI) needs inline scripts,
# so CSP is omitted there. A document CSP for the Vite frontend is a deploy-time
# concern for the static host, not something this API can safely impose on localhost.
_API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
_DOCS_FRAME = "DENY"


def _is_production() -> bool:
    return settings.app_env.strip().lower() in {"production", "prod"}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
        )
        response.headers.setdefault("X-Frame-Options", _DOCS_FRAME)
        path = request.url.path
        if not path.startswith(_DOCS_PATHS) and path not in _DOCS_PATHS:
            response.headers.setdefault("Content-Security-Policy", _API_CSP)
        if _is_production() and settings.cookie_secure:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response
