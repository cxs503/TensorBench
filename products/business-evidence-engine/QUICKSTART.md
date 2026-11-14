# Business Evidence Engine — deterministic reconciliation slice

This first executable slice accepts **normalized extraction JSON** and checks
cross-document consistency. It does not yet perform OCR/PDF layout extraction,
legal interpretation, fraud classification or payment execution.

## Run

```bash
pip install -e .
tensorbench reconcile-business --input bundle.json --output audit-report.json
```

Example bundle:

```json
{
  "vendor_master": {
    "bank_accounts": {"supplier-1": "CN123456"}
  },
  "documents": [
    {
      "doc_id": "po-1",
      "document_type": "purchase_order",
      "source_ref": "file://po-1.pdf",
      "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "po_number": "PO-001",
      "supplier_id": "supplier-1",
      "buyer_id": "buyer-1",
      "currency": "CNY",
      "total_amount": "200.00",
      "line_items": [
        {"sku": "A", "quantity": "2", "unit_price": "100.00", "amount": "200.00"}
      ]
    },
    {
      "doc_id": "invoice-1",
      "document_type": "invoice",
      "source_ref": "file://invoice-1.pdf",
      "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "invoice_number": "INV-001",
      "po_ref": "PO-001",
      "supplier_id": "supplier-1",
      "buyer_id": "buyer-1",
      "currency": "CNY",
      "total_amount": "200.00",
      "line_items": [
        {"sku": "A", "quantity": "2", "unit_price": "100.00", "amount": "200.00"}
      ]
    }
  ]
}
```

## Implemented checks

- Source reference and SHA-256 presence.
- Duplicate invoice numbers and document identifiers.
- Line-item arithmetic and document-total reconciliation.
- Invoice-to-PO matching for supplier, buyer, currency and total.
- Invoice quantity versus linked accepted-delivery quantity.
- Bank-account change against a supplied vendor master (blocks pass; requires human verification).

## Release boundaries

- Input fields must come from a separate extraction stage; do not treat model-extracted values as verified.
- A bank-account mismatch is a high-severity discrepancy signal, not a fraud verdict. Verify through an independent trusted channel.
- Missing PO/delivery links are inconclusive, not passes.
- The SHA-256 values must be computed from original source bytes by the ingestion adapter. This function checks their format and records them; it does not fetch or hash the source files itself.
- Customer data must not be used until tenant isolation, encryption, retention and deletion controls are reviewed.

The next adapter should attach PDF page/table-cell locators and verify that each normalized value can be traced back to the original document.


## PDF field proposal → human review → normalized reconciliation input

The PDF path is intentionally two-step. First extract page evidence and propose fields:

```bash
tensorbench extract-pdf --input invoice.pdf --source-ref "procurement://invoice/INV-001" --output invoice.pages.json
tensorbench propose-pdf-fields --input invoice.pages.json --output invoice.proposals.json
```

Reviewers must decide every proposal explicitly. The decisions file is a JSON array:

```json
[
  {"proposal_id": "<proposal_id from the proposal report>", "decision": "accept"},
  {"proposal_id": "<another proposal_id>", "decision": "reject"}
]
```

Then record the review and emit a normalized document only when all proposals have been decided and no accepted-field conflicts remain:

```bash
tensorbench review-pdf-fields --input invoice.proposals.json --decisions invoice.decisions.json --reviewer "reviewer-id" --document-type invoice --doc-id invoice-001 --output invoice.review.json
```

The output contains a review receipt and a reconciliation-compatible normalized document with source hashes and field-level evidence. If any proposal is pending or accepted values conflict, no normalized document is emitted. Add the normalized documents to a bundle and run the reconcile-business command; missing line items, PO links or other required data remain inconclusive rather than passing.

This does not add OCR or infer line items. A reviewer decision is recorded provenance, not a guarantee that the document itself is truthful.
