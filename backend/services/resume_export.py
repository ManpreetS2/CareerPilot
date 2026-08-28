"""Render an owned ResumeVersion snapshot to PDF or DOCX bytes.

There is no stored artifact or public URL. Bytes are generated on demand from
the immutable snapshot plus tailored bullets. Callers must already have
enforced ownership.
"""

from __future__ import annotations

import io
import zipfile
from xml.sax.saxutils import escape as xml_escape
from typing import Any, Literal

ExportFormat = Literal["pdf", "docx"]

ALLOWED_EXPORT_FORMATS: tuple[ExportFormat, ...] = ("pdf", "docx")
PDF_MIME = "application/pdf"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MIME_BY_FORMAT: dict[str, str] = {"pdf": PDF_MIME, "docx": DOCX_MIME}


class ResumeExportError(Exception):
    def __init__(self, message: str = "Resume export is unavailable.") -> None:
        super().__init__(message)


class InvalidResumeExportFormatError(Exception):
    def __init__(self) -> None:
        super().__init__("Unsupported export format.")


def parse_export_format(value: str | None) -> ExportFormat:
    normalized = (value or "").strip().lower()
    if normalized not in ALLOWED_EXPORT_FORMATS:
        raise InvalidResumeExportFormatError()
    return normalized  # type: ignore[return-value]


def safe_download_filename(version_number: int, fmt: ExportFormat) -> str:
    number = max(int(version_number), 1)
    return f"resume-v{number}.{fmt}"


def _plain(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\r\n", "\n").replace("\r", "\n").strip()


def _item_line(item: Any) -> str:
    if item is None:
        return ""
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        title = _plain(item.get("title") or item.get("role") or item.get("name") or item.get("degree"))
        org = _plain(item.get("company") or item.get("organization") or item.get("school") or item.get("institution"))
        detail = _plain(item.get("description") or item.get("summary") or item.get("details"))
        head = " — ".join(part for part in (title, org) if part)
        if head and detail:
            return f"{head}. {detail}"
        return head or detail or _plain(item)
    return _plain(item)


def _list_lines(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [line for line in (_item_line(item) for item in value) if line]
    return [_plain(value)] if _plain(value) else []


def resume_plaintext(snapshot: dict[str, Any] | None, bullets: list | None) -> str:
    source = snapshot if isinstance(snapshot, dict) else {}
    blocks: list[str] = []
    name = _plain(source.get("name") or source.get("legal_name") or "Resume")
    blocks.append(name)
    contact = [
        _plain(source.get("email")),
        _plain(source.get("phone")),
        _plain(source.get("linkedin_url")),
        _plain(source.get("github_url")),
        _plain(source.get("portfolio_url")),
    ]
    contact_line = " | ".join(part for part in contact if part)
    if contact_line:
        blocks.append(contact_line)
    tailored = [_plain(item) for item in (bullets or []) if _plain(item)]
    if tailored:
        blocks.append("Tailored highlights")
        blocks.extend(f"• {line}" for line in tailored)
    for heading, key in (
        ("Experience", "experience"),
        ("Projects", "projects"),
        ("Education", "education"),
        ("Skills", "skills"),
        ("Certifications", "certifications"),
        ("Strengths", "strengths"),
    ):
        lines = _list_lines(source.get(key))
        if not lines:
            continue
        blocks.append(heading)
        if key == "skills":
            blocks.append(", ".join(lines))
        else:
            blocks.extend(f"• {line}" for line in lines)
    return "\n".join(blocks).strip() + "\n"


def _wrap(text: str, width: int = 92) -> list[str]:
    if not text:
        return [""]
    words = text.split(" ")
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if len(candidate) <= width:
            current = candidate
            continue
        if current:
            lines.append(current)
        while len(word) > width:
            lines.append(word[:width])
            word = word[width:]
        current = word
    if current:
        lines.append(current)
    return lines or [""]


def _pdf_escape(text: str) -> str:
    safe = text.encode("latin-1", errors="replace").decode("latin-1")
    return safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def render_pdf(text: str) -> bytes:
    pages: list[list[str]] = []
    current: list[str] = []
    for raw_line in text.split("\n"):
        wrapped = _wrap(raw_line)
        for line in wrapped:
            if len(current) >= 48:
                pages.append(current)
                current = []
            current.append(line)
    if current or not pages:
        pages.append(current or [""])

    objects: list[bytes] = []
    page_ids: list[int] = []
    next_id = 3
    page_payloads: list[tuple[int, int, bytes]] = []
    for page_lines in pages:
        commands = ["BT /F1 11 Tf 50 742 Td 14 TL"]
        for line in page_lines:
            commands.append(f"({_pdf_escape(line)}) Tj T*")
        commands.append("ET")
        stream = "\n".join(commands).encode("latin-1", errors="replace")
        page_id = next_id
        content_id = next_id + 1
        next_id += 2
        page_ids.append(page_id)
        page_payloads.append((page_id, content_id, stream))
    font_id = next_id
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects.append(b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n")
    objects.append(
        f"2 0 obj<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>endobj\n".encode()
    )
    for page_id, content_id, stream in page_payloads:
        objects.append(
            (
                f"{page_id} 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Contents {content_id} 0 R /Resources<< /Font<< /F1 {font_id} 0 R >> >> >>endobj\n"
            ).encode()
        )
        objects.append(
            f"{content_id} 0 obj<< /Length {len(stream)} >>stream\n".encode()
            + stream
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


def _w_t(text: str) -> str:
    return f"<w:p><w:r><w:t xml:space=\"preserve\">{xml_escape(text)}</w:t></w:r></w:p>"


def render_docx(text: str) -> bytes:
    body = "".join(_w_t(line) for line in text.split("\n"))
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}<w:sectPr/></w:body></w:document>"
    )
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>
"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("word/document.xml", document_xml)
    return buffer.getvalue()


def export_resume_bytes(
    *,
    snapshot: dict[str, Any] | None,
    tailored_bullets: list | None,
    version_number: int,
    fmt: ExportFormat,
) -> tuple[bytes, str, str]:
    text = resume_plaintext(snapshot, tailored_bullets)
    if not text.strip():
        raise ResumeExportError("Resume version has no exportable content.")
    if fmt == "pdf":
        payload = render_pdf(text)
    else:
        payload = render_docx(text)
    if not payload:
        raise ResumeExportError()
    return payload, MIME_BY_FORMAT[fmt], safe_download_filename(version_number, fmt)
