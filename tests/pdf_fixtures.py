"""Helpers for building tiny PDFs in tests without extra dependencies."""

from __future__ import annotations

from pathlib import Path


def build_simple_text_pdf(text: str) -> bytes:
    """Create a minimal PDF with embedded text that pdfplumber can extract."""
    # Keep content stream ASCII-safe for the test fixture writer.
    safe = (
        text.replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
        .replace("\r", " ")
        .replace("\n", ") Tj T* (")
    )
    stream = f"BT /F1 11 Tf 50 750 Td 14 TL ({safe}) Tj ET"
    stream_bytes = stream.encode("latin-1", errors="replace")

    objects = [
        b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n",
        b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n",
        b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources<< /Font<< /F1 5 0 R >> >> >>endobj\n",
        b"4 0 obj<< /Length "
        + str(len(stream_bytes)).encode()
        + b" >>stream\n"
        + stream_bytes
        + b"\nendstream\nendobj\n",
        b"5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(out))
        out.extend(obj)

    xref_pos = len(out)
    out.extend(f"xref\n0 {len(offsets)}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        out.extend(f"{offset:010d} 00000 n \n".encode())
    out.extend(
        f"trailer<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode()
    )
    return bytes(out)


def build_multipage_text_pdf(page_texts: list[str]) -> bytes:
    """Create a multi-page PDF with one text stream per page."""
    if not page_texts:
        raise ValueError("page_texts must be non-empty")

    objects: list[bytes] = []
    # Placeholder indices: 1=Catalog, 2=Pages, then pairs of Page+Content, then Font.
    page_ids: list[int] = []
    next_id = 3
    page_payloads: list[tuple[int, int, bytes]] = []
    for text in page_texts:
        safe = (
            text.replace("\\", "\\\\")
            .replace("(", "\\(")
            .replace(")", "\\)")
            .replace("\r", " ")
            .replace("\n", ") Tj T* (")
        )
        stream = f"BT /F1 11 Tf 50 750 Td 14 TL ({safe}) Tj ET"
        stream_bytes = stream.encode("latin-1", errors="replace")
        page_id = next_id
        content_id = next_id + 1
        next_id += 2
        page_ids.append(page_id)
        page_payloads.append((page_id, content_id, stream_bytes))

    font_id = next_id
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects.append(b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n")
    objects.append(
        f"2 0 obj<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>endobj\n".encode()
    )
    for page_id, content_id, stream_bytes in page_payloads:
        objects.append(
            (
                f"{page_id} 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Contents {content_id} 0 R /Resources<< /Font<< /F1 {font_id} 0 R >> >> >>endobj\n"
            ).encode()
        )
        objects.append(
            f"{content_id} 0 obj<< /Length {len(stream_bytes)} >>stream\n".encode()
            + stream_bytes
            + b"\nendstream\nendobj\n"
        )
    objects.append(
        f"{font_id} 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n".encode()
    )

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(out))
        out.extend(obj)
    xref_pos = len(out)
    out.extend(f"xref\n0 {len(offsets)}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        out.extend(f"{offset:010d} 00000 n \n".encode())
    out.extend(
        f"trailer<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode()
    )
    return bytes(out)


def write_simple_text_pdf(path: Path, text: str) -> Path:
    path.write_bytes(build_simple_text_pdf(text))
    return path


def build_image_only_pdf() -> bytes:
    """Create a one-page PDF with no text operators (forces near-empty extraction)."""
    # Empty content stream — pdfplumber returns little/no text.
    stream = b""
    objects = [
        b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n",
        b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n",
        b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R >>endobj\n",
        b"4 0 obj<< /Length 0 >>stream\nendstream\nendobj\n",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(out))
        out.extend(obj)
    xref_pos = len(out)
    out.extend(f"xref\n0 {len(offsets)}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        out.extend(f"{offset:010d} 00000 n \n".encode())
    out.extend(
        f"trailer<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode()
    )
    return bytes(out)


SAMPLE_RESUME_TEXT = """
Alex Rivera
alex.rivera@example.com
+1-555-0142

Skills: Python, FastAPI, SQL, PostgreSQL, React, Docker, AWS

Experience
Software Engineering Intern, Northstar Labs
2025-05 – 2025-08
- Shipped an internal API used by 4 product teams.
- Reduced p95 latency on search endpoints by 28%.

Projects
Campus Connect
Student-org discovery platform with search and event RSVP.
Technologies: Python, FastAPI, React
https://github.com/example/campus-connect

Education
State University — B.S. Computer Science, 2027

Certifications
AWS Cloud Practitioner

Strengths
Backend APIs, Clear written communication, Fast iteration
""".strip()
