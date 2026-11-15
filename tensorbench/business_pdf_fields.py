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


def _spec(pattern, *, value_group=1, subject_group=None, normalizer="text", currency_group=None):
    """One page-addressable field rule inside a field spectrum."""
    return {
        "pattern": pattern,
        "value_group": value_group,
        "subject_group": subject_group,
        "normalizer": normalizer,
        "currency_group": currency_group,
    }


#: Spectrum 1: trade documents (invoice / PO / contract). Unchanged rules.
_TRADE_DOCUMENTS_V1 = {
    "invoice_number": _spec(re.compile(r"(?im)^\s*(?:invoice\s*(?:no\.?|number)|发票号码|发票编号)\s*[:：#]?\s*([A-Z0-9][A-Z0-9/_-]{1,})\s*$")),
    "contract_number": _spec(re.compile(r"(?im)^\s*(?:contract\s*(?:no\.?|number)|合同编号|合同号)\s*[:：#]?\s*([A-Z0-9][A-Z0-9/_-]{1,})\s*$")),
    "purchase_order_number": _spec(re.compile(r"(?im)^\s*(?:purchase\s*order\s*(?:no\.?|number)|PO\s*(?:no\.?|number)|采购订单号)\s*[:：#]?\s*([A-Z0-9][A-Z0-9/_-]{1,})\s*$")),
    "document_date": _spec(re.compile(r"(?im)^\s*(?:invoice\s*date|contract\s*date|date|日期|签订日期|开票日期)\s*[:：]?\s*(\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}日?)\s*$"),
                      normalizer="date"),
    "total_amount": _spec(re.compile(r"(?im)^\s*(?:total\s*(?:amount|due)|grand\s*total|amount\s*due)\s*[:：]?\s*"
                                     r"([￥¥$€£]?\s*[\d,]+(?:\.\d{1,2})?)\s*(CNY|RMB|USD|EUR|GBP|人民币|美元|欧元)?\s*$"),
                       normalizer="amount", currency_group=2),
}


#: Spectrum 2: business-plan / investor-deck documents. Ratio and milestone
#: rules are written as generic table shapes (label line followed by a value
#: line), not as a list of this document's row labels, so a different plan
#: yields different values rather than silently reusing these ones.
_BUSINESS_PLAN_V1 = {
    "document_title": _spec(re.compile(r"(?m)^[ \t]*([^\n|·]{2,40}(?:商业计划书|Business\s+Plan))[ \t]*$")),
    "document_version": _spec(re.compile(r"(?m)^[ \t]*[^\n|]{0,30}\|[ \t]*(V\d+(?:\.\d+)*)[ \t]*\|")),
    "document_issue_date": _spec(re.compile(r"(?m)\|[ \t]*(\d{4}\s*年\s*\d{1,2}\s*月)[ \t]*$"),
                                 normalizer="cn_month"),
    "legal_disclaimer": _spec(re.compile(r"(?m)(本文件为[^\n，。；]{4,40})")),
    "financing_stage": _spec(re.compile(r"(?m)建议以([^\n，。]{2,24}?)(?:战略)?融资")),
    # Declared on purpose: a plan that asks for money without stating an amount
    # must produce no proposal here, not an inferred number.
    "funding_amount": _spec(re.compile(r"(?m)^[ \t]*(?:融资金额|募资总额|估值)[ \t]*[:：][ \t]*([^\n]{1,40})")),
    "table_label_percent": _spec(
        re.compile(r"(?m)^[ \t]*([\u4e00-\u9fff][^\n%\d]{1,15})[ \t]*\n[ \t]*(\d{1,3})[ \t]*%[ \t]*$"),
        value_group=2, subject_group=1, normalizer="percent"),
    "ratio_block": _spec(
        re.compile(r"(?m)(?:^[ \t]*([\u4e00-\u9fff][^\n%\d]{1,15})[ \t]*\n)?"
                   r"((?:[ \t]*\d{1,3}[ \t]*%[ \t]*\n){2,6})"),
        value_group=2, subject_group=1, normalizer="percent_series"),
    "roadmap_window": _spec(
        re.compile(r"(?m)^[ \t]*([\u4e00-\u9fff][^\n\d]{1,15})[ \t]*\n[ \t]*"
                   r"(\d{1,2}[ \t]*[–\-~—][ \t]*\d{1,2})[ \t]*个月"),
        value_group=2, subject_group=1, normalizer="month_span"),
    # A citation row is keyed by "publisher: title": a publisher alone is not a
    # unique row key (two Gartner reports sit on the same page), and a duplicate
    # row key must surface as a review conflict rather than be merged silently.
    "market_reference": _spec(
        re.compile(r"(?m)^[ \t]*(([A-Za-z][A-Za-z0-9 .&_-]{2,24})[：:][ \t]*(.{2,80}?)[ \t]*[（(]\s*(\d{4})\s*[）)])"),
        value_group=3, subject_group=1),
}


#: Named, versioned field spectra. A spectrum is the declared field list an
#: extraction is measured against; coverage is reported per field, never
#: averaged.
FIELD_SPECTRA = {
    "trade_documents_v1": _TRADE_DOCUMENTS_V1,
    "business_plan_v1": _BUSINESS_PLAN_V1,
}

DEFAULT_FIELD_SPECTRUM = "trade_documents_v1"

#: Backwards-compatible alias for the original single-spectrum module surface.
_PATTERNS = _TRADE_DOCUMENTS_V1


def field_spectrum_names() -> tuple[str, ...]:
    return tuple(sorted(FIELD_SPECTRA))


def field_names(spectrum: str = DEFAULT_FIELD_SPECTRUM) -> tuple[str, ...]:
    return tuple(FIELD_SPECTRA[_resolve_spectrum(spectrum)])


def _resolve_spectrum(spectrum: str) -> str:
    if spectrum not in FIELD_SPECTRA:
        raise PdfFieldProposalError(
            f"unknown field spectrum {spectrum!r}; expected one of {', '.join(sorted(FIELD_SPECTRA))}"
        )
    return spectrum


_NORMALIZERS = {
    "text": lambda raw, match, spec: (raw, None),
    "date": lambda raw, match, spec: (
        raw.replace("年", "-").replace("月", "-").replace("日", "").replace("/", "-").replace(".", "-"), None),
    "amount": lambda raw, match, spec: (re.sub(r"[,\s￥¥$€£]", "", raw), None),
    "cn_month": lambda raw, match, spec: (re.sub(r"\s+", "", raw)
                                          .replace("年", "-").replace("月", ""), None),
    "percent": lambda raw, match, spec: (raw.rstrip("%").strip(), None),
    "percent_series": lambda raw, match, spec: ("/".join(
        token.rstrip("%") for token in raw.split()), None),
    "month_span": lambda raw, match, spec: (re.sub(r"\s+", "", raw)
                                            .replace("–", "-").replace("—", "-").replace("~", "-"), None),
}


class PdfFieldProposalError(ValueError):
    """Invalid page-evidence extraction input."""


def propose_pdf_fields(extraction: Any, *, spectrum: str = DEFAULT_FIELD_SPECTRUM) -> dict[str, Any]:
    """Propose field candidates for one declared field spectrum.

    ``spectrum`` selects the field list (see :data:`FIELD_SPECTRA`); the
    default keeps the original trade-document behaviour.
    """
    spectrum = _resolve_spectrum(spectrum)
    rules = FIELD_SPECTRA[spectrum]
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
        for field_name, rule in rules.items():
            pattern = rule["pattern"]
            value_group = rule["value_group"]
            subject_group = rule["subject_group"]
            normalizer = _NORMALIZERS[rule["normalizer"]]
            for match in pattern.finditer(page_text):
                captured = match.group(value_group) or ""
                raw_value = captured.strip()
                # Offsets must address the stripped value exactly; a rule whose
                # capture group swallows a trailing newline (table row blocks)
                # would otherwise point one character past the value.
                lead = len(captured) - len(captured.lstrip())
                start = match.start(value_group) + lead
                end = match.end(value_group) - (len(captured) - len(captured.rstrip()))
                subject = (match.group(subject_group) or "").strip() if subject_group else None
                if not raw_value:
                    continue
                if subject is not None and not subject:
                    subject = None
                normalized, currency = normalizer(raw_value, match, rule)
                if rule["currency_group"]:
                    currency = match.group(rule["currency_group"])
                identity = {
                    "source_sha256": source["sha256"], "page_number": page_no,
                    "field": field_name, "start_offset": start,
                    "end_offset": end, "normalized_candidate": normalized,
                    "currency_candidate": currency,
                    "value_sha256": hashlib.sha256(raw_value.encode("utf-8")).hexdigest(),
                }
                if subject is not None:
                    identity["subject"] = subject
                proposal_id = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
                proposal: dict[str, Any] = {
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
                        "start_offset": start,
                        "end_offset": end,
                        "matched_text": match.group(0).strip(),
                        "page_text_sha256": (page.get("locator") or {}).get("page_text_sha256"),
                        "value_sha256": hashlib.sha256(raw_value.encode("utf-8")).hexdigest(),
                    },
                    "extraction_method": "label_pattern",
                }
                if subject is not None:
                    proposal["subject"] = subject
                proposals.append(proposal)
    return {
        "schema_version": "0.1.0",
        "product_id": "business-evidence-engine",
        "product_version": "0.3.0",
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source": source,
        "field_spectrum": spectrum,
        "field_spectrum_fields": list(rules),
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


def propose_pdf_fields_file(path: str | Path, *, spectrum: str = DEFAULT_FIELD_SPECTRUM) -> dict[str, Any]:
    try:
        extraction = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PdfFieldProposalError(f"cannot read PDF extraction JSON: {exc}") from exc
    return propose_pdf_fields(extraction, spectrum=spectrum)



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
            "normalized_candidate": proposal.get("normalized_candidate"),
            "currency_candidate": proposal.get("currency_candidate"),
            "value_sha256": locator.get("value_sha256"),
        }
        if proposal.get("subject") is not None:
            identity["subject"] = proposal["subject"]
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

    groups: dict[tuple[str, str | None], list[dict[str, Any]]] = {}
    for proposal in accepted:
        groups.setdefault((proposal["field"], proposal.get("subject")), []).append(proposal)
    conflicts = []
    approved_fields: dict[str, Any] = {}
    for (field_name, subject), items in groups.items():
        values = {(item.get("normalized_candidate"), item.get("currency_candidate")) for item in items}
        if len(values) != 1:
            conflicts.append(field_name if subject is None else f"{field_name}#{subject}")
            continue
        value, currency = next(iter(values))
        key = field_name if subject is None else f"{field_name}#{subject}"
        approved_fields[key] = {
            "field": field_name,
            "subject": subject,
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
        "field_spectrum": proposal_bundle.get("field_spectrum", DEFAULT_FIELD_SPECTRUM),
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


def approved_pdf_fields_to_evidence_record(reviewed: Any, *, record_type: str, record_id: str) -> dict[str, Any]:
    """Emit a structured record for any field spectrum (no trade-document mapping).

    Trade documents keep using :func:`approved_pdf_fields_to_document`, whose
    narrow mapping is part of the reconciliation contract. This function makes a
    reviewed business-plan (or any other spectrum) extraction into a structured
    output that still carries page locators and value fingerprints.
    """
    if not isinstance(reviewed, dict) or reviewed.get("product_id") != "business-evidence-engine":
        raise PdfFieldProposalError("reviewed proposal bundle is required")
    if reviewed.get("status") != "reviewed":
        raise PdfFieldProposalError("all proposals must be reviewed and conflicts resolved before normalization")
    if not isinstance(record_type, str) or not record_type.strip():
        raise PdfFieldProposalError("record_type is required")
    if not isinstance(record_id, str) or not record_id.strip():
        raise PdfFieldProposalError("record_id is required")
    source = reviewed.get("source") or {}
    fields: dict[str, Any] = {}
    for key, entry in sorted((reviewed.get("approved_fields") or {}).items()):
        fields[key] = {
            "field": entry.get("field", key),
            "subject": entry.get("subject"),
            "value": entry.get("value"),
            "currency": entry.get("currency"),
            "evidence": entry.get("evidence", []),
        }
    return {
        "schema_version": "1.0.0",
        "product_id": "business-evidence-engine",
        "product_version": "0.4.0",
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "record_id": record_id.strip(),
        "record_type": record_type.strip(),
        "field_spectrum": reviewed.get("field_spectrum", DEFAULT_FIELD_SPECTRUM),
        "source": source,
        "evidence_ref": "pdf:" + str(source.get("sha256")),
        "field_count": len(fields),
        "fields": fields,
        "review": {
            "reviewer": (reviewed.get("review") or {}).get("reviewer"),
            "reviewed_at": (reviewed.get("review") or {}).get("reviewed_at"),
            "proposal_bundle_sha256": reviewed.get("proposal_bundle_sha256"),
        },
        "limitations": [
            "Values are reviewer-accepted proposals, not an independent verification of document truth.",
            "No OCR, table reconstruction or financial interpretation is performed.",
        ],
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
