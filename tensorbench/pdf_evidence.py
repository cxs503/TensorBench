"""Page-addressable PDF text extraction with source integrity metadata.

This is an ingestion adapter, not OCR or a table-understanding system. It
preserves page-level provenance so downstream extraction/review can cite the
exact source page rather than an untraceable text blob.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Any


class PdfEvidenceError(ValueError):
    """PDF input cannot be safely processed."""


def extract_pdf_evidence(
    path: str | Path,
    *,
    source_ref: str,
    max_bytes: int = 50 * 1024 * 1024,
    max_pages: int = 1000,
) -> dict[str, Any]:
    """Extract text page-by-page and attach stable page-level evidence refs."""
    file_path = Path(path)
    if not isinstance(source_ref, str) or not source_ref.strip():
        raise PdfEvidenceError("source_ref must be a non-empty stable source identifier")
    if max_bytes < 1 or max_pages < 1:
        raise PdfEvidenceError("max_bytes and max_pages must be positive")
    try:
        size = file_path.stat().st_size
    except OSError as exc:
        raise PdfEvidenceError(f"cannot stat PDF input: {exc}") from exc
    if size == 0:
        raise PdfEvidenceError("PDF input is empty")
    if size > max_bytes:
        raise PdfEvidenceError(f"PDF exceeds max_bytes limit ({size} > {max_bytes})")

    raw = file_path.read_bytes()
    digest = sha256(raw).hexdigest()
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise PdfEvidenceError(
            "PDF support is optional; install TensorBench with the [pdf] extra"
        ) from exc

    try:
        reader = PdfReader(BytesIO(raw), strict=True)
    except Exception as exc:
        raise PdfEvidenceError(f"cannot parse PDF: {exc}") from exc
    if reader.is_encrypted:
        raise PdfEvidenceError("encrypted PDFs are not supported; provide an authorized decrypted copy")
    if len(reader.pages) == 0:
        raise PdfEvidenceError("PDF contains no pages")
    if len(reader.pages) > max_pages:
        raise PdfEvidenceError(
            f"PDF exceeds max_pages limit ({len(reader.pages)} > {max_pages})"
        )

    pages: list[dict[str, Any]] = []
    failed_pages = 0
    for page_number, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
            status = "extracted" if text.strip() else "no_text"
            error = None
        except Exception as exc:  # keep other pages available and explicitly mark this one
            text = ""
            status = "extraction_failed"
            error = f"{type(exc).__name__}: {exc}"
            failed_pages += 1
        page_digest = sha256(text.encode("utf-8")).hexdigest()
        pages.append({
            "evidence_id": f"sha256:{digest}:page:{page_number}",
            "source_type": "file",
            "source_ref": source_ref,
            "sha256": digest,
            "locator": {"page_number": page_number, "page_text_sha256": page_digest},
            "text": text,
            "extraction_status": status,
            **({"error": error} if error else {}),
        })

    return {
        "schema_version": "0.1.0",
        "product_id": "business-evidence-engine",
        "product_version": "0.2.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "source_ref": source_ref,
            "filename": file_path.name,
            "media_type": "application/pdf",
            "byte_length": len(raw),
            "sha256": digest,
            "page_count": len(pages),
        },
        "status": "partial" if failed_pages else "complete",
        "limitations": [
            "Text extraction only; scanned pages require OCR.",
            "Page text is not a verified table/field extraction.",
            "A text span is not a legal or financial conclusion; downstream claims must retain page evidence refs.",
        ],
        "pages": pages,
    }


def extract_pdf_file(
    path: str | Path,
    *,
    source_ref: str,
    max_bytes: int = 50 * 1024 * 1024,
    max_pages: int = 1000,
) -> dict[str, Any]:
    return extract_pdf_evidence(
        path, source_ref=source_ref, max_bytes=max_bytes, max_pages=max_pages
    )
