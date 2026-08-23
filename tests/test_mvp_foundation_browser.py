"""Pytest wrapper for the privacy-safe MVP foundation browser workflow."""

from __future__ import annotations

from scripts.test_mvp_foundation_browser import run_browser_workflow


def test_mvp_foundation_browser_workflow() -> None:
    result = run_browser_workflow()
    assert result["checks"] >= 8
    assert result["tracker_patches"] == 1
    assert result["interview_posts"] == 1
    assert result["external_requests"] == 0
