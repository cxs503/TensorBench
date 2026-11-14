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
