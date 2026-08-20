"""Reusable HTTP client for the CareerPilot FastAPI backend."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

DEFAULT_BACKEND_URL = "http://localhost:8000"


class BackendError(RuntimeError):
    """Raised when the FastAPI backend cannot be reached or returns an error."""


class CareerPilotClient:
    def __init__(self, base_url: str | None = None, timeout: float = 15.0) -> None:
        self.base_url = (base_url or os.getenv("BACKEND_URL") or DEFAULT_BACKEND_URL).rstrip("/")
        self.timeout = timeout

    def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> Any:
        url = f"{self.base_url}{path}"
        try:
            response = httpx.request(method, url, timeout=self.timeout, **kwargs)
        except httpx.ConnectError as exc:
            raise BackendError(
                f"Cannot reach backend at {self.base_url}. Start it with: "
                "uvicorn backend.main:app --reload"
            ) from exc
        except httpx.HTTPError as exc:
            raise BackendError(f"Backend request failed: {exc}") from exc

        if response.status_code >= 400:
            detail = response.text
            try:
                payload = response.json()
                detail = str(payload.get("detail", payload))
            except ValueError:
                pass
            raise BackendError(f"{response.status_code} from {path}: {detail}")
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def parse_resume(self, filename: str, file_bytes: bytes, content_type: str) -> dict[str, Any]:
        files = {"file": (filename, file_bytes, content_type or "application/pdf")}
        return self._request("POST", "/api/parse-resume", files=files)

    def save_preferences(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/api/preferences", json=payload)

    def list_jobs(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/jobs")

    def get_job(self, job_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/jobs/{job_id}")

    def score_job(self, job_id: str) -> dict[str, Any]:
        return self._request("POST", f"/api/jobs/{job_id}/score")

    def generate_materials(self, job_id: str) -> dict[str, Any]:
        return self._request("POST", f"/api/jobs/{job_id}/generate-materials")

    def approve_job(self, job_id: str, decision: str, notes: str | None = None) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/jobs/{job_id}/approve",
            json={"decision": decision, "notes": notes},
        )


client = CareerPilotClient()
