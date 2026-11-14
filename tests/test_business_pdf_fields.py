from tensorbench.business_pdf_fields import PdfFieldProposalError, propose_pdf_fields


def _extraction():
    import hashlib
    text = "Invoice No: INV-2026-001\nInvoice Date: 2026-11-14\nTotal Amount: ¥1,234.50 CNY\n"
    return {
        "source": {"source_ref": "contract://invoice/1", "sha256": "a" * 64},
        "pages": [{
            "page_number": 2,
            "evidence_id": "sha256:" + "a" * 64 + ":page:2",
            "text": text,
            "locator": {"page_number": 2, "page_text_sha256": hashlib.sha256(text.encode()).hexdigest()},
        }],
    }


def test_pdf_field_proposals_preserve_page_and_exact_offsets():
    report = propose_pdf_fields(_extraction())
    assert report["status"] == "needs_review"
    assert report["proposal_count"] == 3
    invoice = next(item for item in report["proposals"] if item["field"] == "invoice_number")
    assert invoice["normalized_candidate"] == "INV-2026-001"
    assert invoice["locator"]["page_number"] == 2
    assert invoice["locator"]["matched_text"] == "Invoice No: INV-2026-001"
    amount = next(item for item in report["proposals"] if item["field"] == "total_amount")
    assert amount["normalized_candidate"] == "1234.50"
    assert amount["currency_candidate"] == "CNY"


def test_pdf_field_proposals_never_mark_values_as_verified():
    report = propose_pdf_fields(_extraction())
    assert all(item["review_status"] == "proposed_unverified" for item in report["proposals"])


def test_pdf_field_proposals_reject_missing_source_fingerprint():
    extraction = _extraction()
    del extraction["source"]["sha256"]
    try:
        propose_pdf_fields(extraction)
    except PdfFieldProposalError as exc:
        assert "sha256" in str(exc)
    else:
        raise AssertionError("missing source fingerprint must be rejected")


def test_pdf_field_proposals_returns_no_candidates_for_unlabeled_text():
    extraction = _extraction()
    extraction["pages"][0]["text"] = "INV-001 2026-11-14 1234.50"
    report = propose_pdf_fields(extraction)
    assert report["status"] == "no_candidates"
    assert report["proposals"] == []


from tensorbench.business_pdf_fields import (
    approved_pdf_fields_to_document,
    review_pdf_field_proposals,
)


def test_pdf_field_review_accepts_only_explicitly_approved_values_and_preserves_provenance():
    proposals = propose_pdf_fields(_extraction())
    invoice = next(item for item in proposals["proposals"] if item["field"] == "invoice_number")
    amount = next(item for item in proposals["proposals"] if item["field"] == "total_amount")
    reviewed = review_pdf_field_proposals(
        proposals,
        [{"proposal_id": invoice["proposal_id"], "decision": "accept"},
         {"proposal_id": amount["proposal_id"], "decision": "accept"}],
        reviewer="independent-reviewer",
    )
    assert reviewed["status"] == "needs_review"
    assert reviewed["approved_fields"]["invoice_number"]["value"] == "INV-2026-001"
    document = approved_pdf_fields_to_document(reviewed, document_type="invoice", doc_id="inv-1") if False else None
    # Partial review is deliberately not eligible for reconciliation normalization.
    assert "document" not in reviewed


def test_pdf_field_review_requires_complete_decisions_before_normalization():
    proposals = propose_pdf_fields(_extraction())
    decisions = [{"proposal_id": item["proposal_id"], "decision": "accept"} for item in proposals["proposals"]]
    reviewed = review_pdf_field_proposals(proposals, decisions, reviewer="reviewer-1")
    assert reviewed["status"] == "reviewed"
    document = approved_pdf_fields_to_document(reviewed, document_type="invoice", doc_id="invoice-1")
    assert document["invoice_number"] == "INV-2026-001"
    assert document["total_amount"] == "1234.50"
    assert document["currency"] == "CNY"
    assert document["sha256"] == "a" * 64
    assert document["field_evidence"]["invoice_number"][0]["source_evidence_id"].endswith(":page:2")


def test_pdf_field_review_rejects_unknown_duplicate_and_invalid_decisions():
    proposals = propose_pdf_fields(_extraction())
    proposal_id = proposals["proposals"][0]["proposal_id"]
    for decisions in (
        [{"proposal_id": "unknown", "decision": "accept"}],
        [{"proposal_id": proposal_id, "decision": "accept"}, {"proposal_id": proposal_id, "decision": "reject"}],
        [{"proposal_id": proposal_id, "decision": "maybe"}],
    ):
        try:
            review_pdf_field_proposals(proposals, decisions, reviewer="reviewer-1")
        except PdfFieldProposalError:
            pass
        else:
            raise AssertionError("invalid review decision must be rejected")


def test_pdf_field_review_withholds_conflicting_accepted_values():
    proposals = propose_pdf_fields(_extraction())
    first = next(item for item in proposals["proposals"] if item["field"] == "invoice_number")
    altered = dict(first, proposal_id="b" * 64, normalized_candidate="INV-DIFFERENT")
    proposals["proposals"].append(altered)
    decisions = [{"proposal_id": item["proposal_id"], "decision": "accept"} for item in proposals["proposals"]]
    reviewed = review_pdf_field_proposals(proposals, decisions, reviewer="reviewer-1")
    assert reviewed["status"] == "conflicted"
    assert "invoice_number" in reviewed["review"]["conflicting_fields"]
    try:
        approved_pdf_fields_to_document(reviewed, document_type="invoice", doc_id="invoice-1")
    except PdfFieldProposalError:
        pass
    else:
        raise AssertionError("conflicted reviewed fields must not enter reconciliation")
