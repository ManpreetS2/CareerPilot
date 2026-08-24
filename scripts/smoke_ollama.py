#!/usr/bin/env python3
"""Opt-in live Ollama smoke check. Not run in CI.

Verifies /api/tags and one tiny schema-constrained /api/chat response.
Never pulls models, never writes application data, and never prints the
configured endpoint, prompts, or secrets.
"""

from __future__ import annotations

import argparse
import json
import sys

import httpx

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core.config import settings, validate_ollama_base_url


def _base_url() -> str:
    return validate_ollama_base_url(settings.ollama_base_url).rstrip("/")


def _client() -> httpx.Client:
    timeout = httpx.Timeout(
        connect=float(settings.ollama_connect_timeout_seconds),
        read=float(settings.ollama_read_timeout_seconds),
        write=float(settings.ollama_read_timeout_seconds),
        pool=float(settings.ollama_connect_timeout_seconds),
    )
    return httpx.Client(
        timeout=timeout,
        follow_redirects=False,
        trust_env=False,
        verify=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Opt-in Ollama smoke check (not CI).")
    parser.parse_args()
    try:
        base = _base_url()
    except Exception:
        print("ollama_smoke result=fail stage=config")
        return 1
    schema = {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}},
        "required": ["ok"],
    }
    try:
        with _client() as client:
            tags = client.get(f"{base}/api/tags")
            if tags.status_code != 200:
                print("ollama_smoke result=fail stage=tags")
                return 1
            payload = {
                "model": settings.ollama_model,
                "stream": False,
                "think": False,
                "keep_alive": settings.ollama_keep_alive,
                "format": schema,
                "options": {"temperature": 0},
                "messages": [
                    {"role": "system", "content": "Return only JSON."},
                    {"role": "user", "content": "Reply with ok true."},
                ],
            }
            chat = client.post(f"{base}/api/chat", json=payload)
            if chat.status_code != 200:
                print("ollama_smoke result=fail stage=chat")
                return 1
            body = chat.json()
            content = (body.get("message") or {}).get("content")
            parsed = json.loads(content) if isinstance(content, str) else None
            if not isinstance(parsed, dict) or parsed.get("ok") is not True:
                print("ollama_smoke result=fail stage=schema")
                return 1
    except httpx.HTTPError:
        print("ollama_smoke result=fail stage=network")
        return 1
    except Exception:
        print("ollama_smoke result=fail stage=response")
        return 1
    print("ollama_smoke result=pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
