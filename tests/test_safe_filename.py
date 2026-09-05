"""safe_filename_stem is a security control (Content-Disposition header
injection defense against untrusted, scraped text), shared by every export
that builds a download filename from it."""

from __future__ import annotations

from backend.services.safe_filename import safe_filename_stem


def test_strips_header_injection_characters() -> None:
    stem = safe_filename_stem(['Intern"\r\nSet-Cookie: evil=1', "Acme"], default="fallback")
    assert '"' not in stem
    assert "\r" not in stem
    assert "\n" not in stem
    assert ":" not in stem


def test_strips_path_traversal_characters() -> None:
    stem = safe_filename_stem(["../../etc/passwd", "Acme"], default="fallback")
    assert "/" not in stem


def test_falls_back_when_stripped_to_empty() -> None:
    stem = safe_filename_stem(["???", "###"], default="fallback")
    assert stem == "fallback"


def test_falls_back_on_no_parts() -> None:
    assert safe_filename_stem([], default="fallback") == "fallback"
    assert safe_filename_stem([None, ""], default="fallback") == "fallback"  # type: ignore[list-item]


def test_collapses_whitespace_and_joins_parts() -> None:
    stem = safe_filename_stem(["Backend  Engineer", "Acme Corp"], default="fallback")
    assert stem == "Backend Engineer Acme Corp"


def test_truncates_to_max_length() -> None:
    stem = safe_filename_stem(["a" * 200], default="fallback", max_length=10)
    assert len(stem) <= 10
