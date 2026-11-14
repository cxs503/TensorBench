"""Conservative, page-addressable field proposals from extracted PDF text.

Candidates are suggestions for human/agent review, not accepted normalized
business records. This module deliberately avoids OCR and table reconstruction.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
from pathlib import Path
from typing import Any


_PATTERNS = {
    "invoice_number": re.compile(r"(?im)^\s*(?:invoice\s*(?:no\.?|number)|发票号码|发票编号)\s*[:：#]?\s*([A-Z0-9][A-Z0-9/_-]{1,})\s*$"),
    "contract_number": re.compile(r"(?im)^\s*(?:contract\s*(?:no\.?|number)|合同编号|合同号)\s*[:：#]?\s*([A-Z0-9][A-Z0-9/_-]{1,})\s*$"),
    "purchase_order_number": re.compile(r"(?im)^\s*(?:purchase\s*order\s*(?:no\.?|number)|PO\s*(?:no\.?|number)|采购订单号)\s*[:：#]?\s*([A-Z0-9][A-Z0-9/_-]{1,})\s*$"),
    "document_date": re.compile(r"(?im)^\s*(?:invoice\s*date|contract\s*date|date|日期|签订日期|开票日期)\s*[:：]?\s*(\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}日?)\s*$"),
    "total_amount": re.compile(r"(?im)^\s*(?:total\s*(?:amount|due)|grand\s*total|amount\s*due|合计|总金额|价税合计)\s*[:：]?\s*([￥¥$€£]?\s*[\d,]+(?:\.\d{1,2})?)\s*(CNY|RMB|USD|EUR|GBP|人民币|美元|欧元)?\s*$"),
}


class PdfFieldProposalError(ValueError):
    """Invalid page-evidence extraction input."""


def propose_pdf_fields(extraction: Any) -> dict[str, Any]:
    if not isinstance(extraction, dict) or not isinstance(extraction.get("pages"), list):
        raise PdfFieldProposalError("input must be a PDF page-evidence object with pages[]")
    source = extraction.get("source")
    if not isinstance(source, dict) or not source.get("sha256") or not source.get("source_ref"):
        raise PdfFieldProposalError("PDF source_ref and source sha256 are required")
    proposals: list[dict[str, Any]] = []
    for page in extraction["pages"]:
        if not isinstance(page, dict) or not isinstance(page.get("text"), str):
            raise PdfFieldProposalError("each page must contain extracted text")
        page_text = page["text"]
        page_no = page.get("page_number") or (page.get("locator") or {}).get("page_number")
        if not isinstance(page_no, int) or page_no < 1:
            raise PdfFieldProposalError("each page must have a positive page_number")
        page_evidence_id = page.get("evidence_id")
        for field_name, pattern in _PATTERNS.items():
            for match in pattern.finditer(page_text):
                raw_value = match.group(1).strip()
                normalized: str | None = None
                currency: str | None = None
                if field_name == "total_amount":
                    normalized = re.sub(r"[,\s￥¥$€£]", "", raw_value)
                    currency = match.group(2)
                elif field_name == "document_date":
                    normalized = raw_value.replace("年", "-").replace("月", "-").replace("日", "").replace("/", "-").replace(".", "-")
                else:
                    normalized = raw_value
                proposals.append({
                    "field": field_name,
                    "raw_value": raw_value,
                    "normalized_candidate": normalized,
                    "currency_candidate": currency,
                    "review_status": "proposed_unverified",
                    "source_evidence_id": page_evidence_id,
                    "source_ref": source["source_ref"],
                    "source_sha256": source["sha256"],
                    "locator": {
                        "page_number": page_no,
                        "start_offset": match.start(1),
                        "end_offset": match.end(1),
                        "matched_text": match.group(0).strip(),
                        "page_text_sha256": (page.get("locator") or {}).get("page_text_sha256"),
                        "value_sha256": hashlib.sha256(raw_value.encode("utf-8")).hexdigest(),
                    },
                    "extraction_method": "label_pattern",
                })
    return {
        "schema_version": "0.1.0",
        "product_id": "business-evidence-engine",
        "product_version": "0.3.0",
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source": source,
        "status": "needs_review" if proposals else "no_candidates",
        "proposal_count": len(proposals),
        "proposals": proposals,
        "limitations": [
            "Candidates are not accepted normalized document fields.",
            "No OCR, table-cell extraction, handwriting recognition or legal interpretation is performed.",
            "Label-pattern matches can be wrong; review must verify the page image and surrounding context.",
            "Line-item rows and supplier identity are not inferred.",
        ],
    }


def propose_pdf_fields_file(path: str | Path) -> dict[str, Any]:
    try:
        extraction = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PdfFieldProposalError(f"cannot read PDF extraction JSON: {exc}") from exc
    return propose_pdf_fields(extraction)
