from tensorbench.business_evidence import reconcile_bundle


def _doc(doc_id, document_type, **extra):
    return {
        "doc_id": doc_id,
        "document_type": document_type,
        "source_ref": f"fixture://{doc_id}",
        "sha256": "a" * 64 if doc_id.endswith("1") else "b" * 64,
        "supplier_id": "supplier-1",
        "buyer_id": "buyer-1",
        "currency": "CNY",
        **extra,
    }


def _matched_bundle():
    po = _doc(
        "po-1", "purchase_order", po_number="PO-001", total_amount="200.00",
        line_items=[{"sku": "A", "quantity": "2", "unit_price": "100.00", "amount": "200.00"}],
    )
    invoice = _doc(
        "invoice-1", "invoice", invoice_number="INV-001", po_ref="PO-001",
        total_amount="200.00",
        line_items=[{"sku": "A", "quantity": "2", "unit_price": "100.00", "amount": "200.00"}],
    )
    return {
        "documents": [po, invoice],
        "vendor_master": {"bank_accounts": {"supplier-1": "CN123", "supplier-2": "CN123"}},
    }


def test_business_evidence_reconciles_matching_po_and_invoice():
    report = reconcile_bundle(_matched_bundle())
    assert report["overall_status"] == "passed"
    assert report["summary"]["document_count"] == 2
    assert all(check["state"] == "passed" for check in report["checks"])


def test_business_evidence_flags_arithmetic_supplier_and_bank_mismatches():
    bundle = _matched_bundle()
    invoice = bundle["documents"][1]
    invoice["supplier_id"] = "supplier-2"
    invoice["total_amount"] = "240.00"
    invoice["line_items"][0]["amount"] = "240.00"
    invoice["bank_account"] = "CN999"
    report = reconcile_bundle(bundle)
    assert report["overall_status"] == "failed"
    failed = {finding["check_id"] for finding in report["findings"]}
    assert "invoice.purchase_order_match" in failed
    assert "supplier.bank_account_change" in failed


def test_business_evidence_keeps_unresolved_po_inconclusive():
    bundle = _matched_bundle()
    bundle["documents"][1]["po_ref"] = "PO-MISSING"
    report = reconcile_bundle(bundle)
    assert report["overall_status"] == "inconclusive"
    assert any(check["state"] == "inconclusive" for check in report["checks"])


def test_business_evidence_requires_source_fingerprints():
    bundle = _matched_bundle()
    del bundle["documents"][0]["sha256"]
    report = reconcile_bundle(bundle)
    assert report["overall_status"] == "inconclusive"
    assert any(check["check_id"] == "source.provenance" and check["state"] == "inconclusive"
               for check in report["checks"])


def test_business_evidence_rejects_duplicate_document_ids():
    bundle = _matched_bundle()
    bundle["documents"].append(dict(bundle["documents"][0]))
    try:
        reconcile_bundle(bundle)
    except ValueError as exc:
        assert "duplicate doc_id" in str(exc)
    else:
        raise AssertionError("duplicate document ids must be rejected")


def test_business_evidence_does_not_pass_when_required_comparison_data_is_missing():
    bundle = _matched_bundle()
    del bundle["documents"][1]["line_items"]
    del bundle["documents"][1]["currency"]
    report = reconcile_bundle(bundle)
    assert report["overall_status"] == "inconclusive"
    unresolved = [check for check in report["checks"] if check["state"] == "inconclusive"]
    assert any(check["check_id"] == "document.arithmetic" for check in unresolved)
    assert any(check["check_id"] == "invoice.purchase_order_match" for check in unresolved)
