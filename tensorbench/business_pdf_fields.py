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
                proposal_id = hashlib.sha256(json.dumps({
                    "source_sha256": source["sha256"], "page_number": page_no,
                    "field": field_name, "start_offset": match.start(1),
                    "end_offset": match.end(1), "normalized_candidate": normalized, "currency_candidate": currency,\n                    "value_sha256": hashlib.sha256(raw_value.encode("utf-8")).hexdigest(),
                }, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
                proposals.append({
                    "proposal_id": proposal_id,
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



def review_pdf_field_proposals(proposal_bundle: Any, decisions: Any, *, reviewer: str) -> dict[str, Any]:
    """Record explicit human decisions; never promote unreviewed candidates."""
    if not isinstance(proposal_bundle, dict) or not isinstance(proposal_bundle.get("proposals"), list):
        raise PdfFieldProposalError("proposal bundle must contain proposals[]")
    source = proposal_bundle.get("source")
    if not isinstance(source, dict) or not source.get("source_ref") or not re.fullmatch(r"[a-fA-F0-9]{64}", str(source.get("sha256", ""))):
        raise PdfFieldProposalError("proposal bundle has invalid source provenance")
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise PdfFieldProposalError("reviewer identity is required")
    if not isinstance(decisions, list):
        raise PdfFieldProposalError("decisions must be an array")

    proposals = proposal_bundle["proposals"]
    for proposal in proposals:
        if not isinstance(proposal, dict):
            raise PdfFieldProposalError("each proposal must be an object")
        locator = proposal.get("locator")
        if not isinstance(locator, dict):
            raise PdfFieldProposalError("proposal locator is required")
        if proposal.get("source_sha256") != source["sha256"] or proposal.get("source_ref") != source["source_ref"]:
            raise PdfFieldProposalError("proposal source provenance does not match proposal bundle")
        raw_value = proposal.get("raw_value")
        if not isinstance(raw_value, str) or hashlib.sha256(raw_value.encode("utf-8")).hexdigest() != locator.get("value_sha256"):
            raise PdfFieldProposalError("proposal value fingerprint mismatch")
        identity = {
            "source_sha256": source["sha256"],
            "page_number": locator.get("page_number"),
            "field": proposal.get("field"),
            "start_offset": locator.get("start_offset"),
            "end_offset": locator.get("end_offset"),
            "value_sha256": locator.get("value_sha256"),
        }
        expected_id = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        if proposal.get("proposal_id") != expected_id:
            raise PdfFieldProposalError("proposal identity fingerprint mismatch")
    by_id = {item.get("proposal_id"): item for item in proposals if isinstance(item, dict) and item.get("proposal_id")}
    if len(by_id) != len(proposals):
        raise PdfFieldProposalError("every proposal must have a unique proposal_id")
    seen: set[str] = set()
    normalized_decisions: dict[str, str] = {}
    for item in decisions:
        if not isinstance(item, dict):
            raise PdfFieldProposalError("each decision must be an object")
        proposal_id, decision = item.get("proposal_id"), item.get("decision")
        if proposal_id not in by_id:
            raise PdfFieldProposalError(f"decision references unknown proposal_id: {proposal_id!r}")
        if proposal_id in seen:
            raise PdfFieldProposalError(f"duplicate decision for proposal_id: {proposal_id}")
        if decision not in {"accept", "reject"}:
            raise PdfFieldProposalError("decision must be accept or reject")
        seen.add(proposal_id)
        normalized_decisions[proposal_id] = decision

    reviewed = json.loads(json.dumps(proposal_bundle, ensure_ascii=False))
    accepted: list[dict[str, Any]] = []
    rejected: list[str] = []
    pending: list[str] = []
    for proposal in reviewed["proposals"]:
        decision = normalized_decisions.get(proposal["proposal_id"])
        proposal["review_status"] = "accepted" if decision == "accept" else "rejected" if decision == "reject" else "proposed_unverified"
        if decision == "accept":
            accepted.append(proposal)
        elif decision == "reject":
            rejected.append(proposal["proposal_id"])
        else:
            pending.append(proposal["proposal_id"])

    fields: dict[str, list[dict[str, Any]]] = {}
    for proposal in accepted:
        fields.setdefault(proposal["field"], []).append(proposal)
    conflicts = []
    approved_fields: dict[str, Any] = {}
    for field_name, items in fields.items():
        values = {(item.get("normalized_candidate"), item.get("currency_candidate")) for item in items}
        if len(values) != 1:
            conflicts.append(field_name)
            continue
        value, currency = next(iter(values))
        approved_fields[field_name] = {
            "value": value,
            "currency": currency,
            "evidence": [{
                "proposal_id": item["proposal_id"],
                "source_evidence_id": item.get("source_evidence_id"),
                "source_ref": item["source_ref"],
                "source_sha256": item["source_sha256"],
                "locator": item["locator"],
            } for item in items],
        }

    fingerprint = hashlib.sha256(json.dumps(proposal_bundle, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return {
        "schema_version": "1.0.0",
        "product_id": "business-evidence-engine",
        "status": "conflicted" if conflicts else "needs_review" if pending else "reviewed",
        "proposal_bundle_sha256": fingerprint,
        "source": source,
        "review": {
            "reviewer": reviewer.strip(),
            "reviewed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "decisions": [{"proposal_id": key, "decision": value} for key, value in sorted(normalized_decisions.items())],
            "pending_proposal_ids": pending,
            "rejected_proposal_ids": rejected,
            "conflicting_fields": sorted(conflicts),
        },
        "approved_fields": approved_fields,
        "limitations": ["Accepted values reflect a recorded reviewer decision, not an independent guarantee of document truth.", "Conflicting accepted values are withheld from normalized output."],
    }


def approved_pdf_fields_to_document(reviewed: Any, *, document_type: str, doc_id: str) -> dict[str, Any]:
    """Create a reconciliation input using accepted fields only, preserving provenance."""
    if not isinstance(reviewed, dict) or reviewed.get("product_id") != "business-evidence-engine":
        raise PdfFieldProposalError("reviewed proposal bundle is required")
    if reviewed.get("status") != "reviewed":
        raise PdfFieldProposalError("all proposals must be reviewed and conflicts resolved before normalization")
    if document_type not in {"contract", "purchase_order", "delivery", "invoice", "payment"}:
        raise PdfFieldProposalError("unsupported document_type")
    if not isinstance(doc_id, str) or not doc_id.strip():
        raise PdfFieldProposalError("doc_id is required")
    source = reviewed.get("source") or {}
    fields = reviewed.get("approved_fields") or {}
    mapping = {
        "invoice_number": "invoice_number",
        "contract_number": "contract_number",
        "purchase_order_number": "po_number",
        "document_date": "document_date",
        "total_amount": "total_amount",
    }
    document: dict[str, Any] = {
        "doc_id": doc_id.strip(),
        "document_type": document_type,
        "source_ref": source.get("source_ref"),
        "sha256": source.get("sha256"),
        "field_evidence": {},
    }
    for proposal_field, target_field in mapping.items():
        entry = fields.get(proposal_field)
        if entry is None:
            continue
        document[target_field] = entry["value"]
        document["field_evidence"][target_field] = entry["evidence"]
        if proposal_field == "total_amount" and entry.get("currency"):
            document["currency"] = entry["currency"]
    document["evidence_ref"] = "pdf:" + str(source.get("sha256"))
    return document
