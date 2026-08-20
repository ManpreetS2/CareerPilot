"""Reusable prompt evaluation helper.

Runs a single LLM generate() call, measures latency, and writes sanitized
metadata to logs/. API keys are never logged.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.services.llm_client import LLMClient, get_llm_client

logger = logging.getLogger(__name__)


def run_prompt(
    prompt: str,
    provider: str | None = None,
    system_prompt: str | None = None,
    client: LLMClient | None = None,
) -> dict[str, Any]:
    """Execute one prompt and persist sanitized run metadata under logs/."""
    llm = client or get_llm_client(provider)
    started = time.perf_counter()
    text = llm.generate(prompt, system_prompt=system_prompt)
    latency_ms = round((time.perf_counter() - started) * 1000, 2)

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "provider": llm.provider,
        "model": llm.model,
        "latency_ms": latency_ms,
        "prompt_chars": len(prompt),
        "system_prompt_chars": len(system_prompt) if system_prompt else 0,
        "response_chars": len(text),
        "response_preview": text[:400],
    }
    path = _write_log(record)
    record["log_path"] = str(path)
    record["text"] = text
    logger.info(
        "Prompt harness complete provider=%s model=%s latency_ms=%s",
        llm.provider,
        llm.model,
        latency_ms,
    )
    return record


def _write_log(record: dict[str, Any]) -> Path:
    logs_dir = Path("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = logs_dir / f"prompt_harness_{stamp}.json"
    sanitized = {k: v for k, v in record.items() if k != "text"}
    path.write_text(json.dumps(sanitized, indent=2), encoding="utf-8")
    return path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CareerPilot prompt test harness")
    parser.add_argument("--provider", default=None, help="gemini | anthropic | openai")
    parser.add_argument(
        "--prompt",
        default="Reply with one sentence confirming the CareerPilot prompt harness works.",
    )
    parser.add_argument("--system-prompt", default=None)
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    result = run_prompt(
        prompt=args.prompt,
        provider=args.provider,
        system_prompt=args.system_prompt,
    )
    print(result["text"])
    print(f"\nprovider={result['provider']} model={result['model']} latency_ms={result['latency_ms']}")
    print(f"metadata: {result['log_path']}")
