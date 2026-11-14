# Business Evidence Engine — Product Requirements

**Product ID:** `business-evidence-engine` · **Status:** foundation / not implemented · **First external segment:** engineering-company procurement and contract review.

## Problem and outcome

Business documents are individually plausible but inconsistent across contract, purchase order, delivery/acceptance record, invoice and payment. The product identifies discrepancies and produces a traceable evidence packet for a human reviewer. It is not an accounting system or legal decision-maker.

## MVP workflow

1. User uploads a bounded document bundle (PDF, image, DOCX/XLSX) to an isolated tenant workspace.
2. Extract text/tables with page and cell locators; preserve original file hashes.
3. Normalize parties, identifiers, dates, currencies, quantities, tax, line items and payment terms.
4. Match records across document types using deterministic keys first, assisted matching second.
5. Run rule checks and produce discrepancy findings with source snippets/coordinates.
6. Human reviewer resolves findings and exports an audit packet.

## MVP checks

- Party/entity, contract/PO/invoice number and date consistency.
- Line-item quantity, unit price, tax, currency and total arithmetic.
- Contract-to-PO scope/price/term deviation.
- Delivery/acceptance-to-invoice quantity and milestone alignment.
- Duplicate invoice/order and split/overbilling patterns.
- Payment term, due date and bank/account changes flagged for human verification.
- Missing required documents and unresolved matches.

## Acceptance and pilot

- Use 30–50 permissioned, de-identified document bundles with human-labelled discrepancies.
- Exact arithmetic and deterministic identifier checks must be 100% correct on the fixture suite.
- Report extraction accuracy separately from cross-document matching accuracy.
- Target ≥0.90 precision for high-severity discrepancy alerts before a customer pilot; recall must be reported by defect type.
- Every finding includes source document hash, page/cell locator, extracted values, comparison rule and reviewer state.
- Tenant isolation, encryption, access audit, retention/deletion and no-training-on-customer-data policy must be verified before real customer documents are accepted.

## Non-goals

Automated payment execution, legal advice, fraud accusation, ERP replacement, or silent approval/rejection of invoices.

## First vertical slice

A local, single-tenant batch review of a permissioned sample bundle. Do not build a complete ERP integration, billing system or multi-tenant SaaS control plane before validating repeated customer demand.


## Implementation status (verified against repository source, 2026-11-14)

**Overall: partially implemented; no real-world document-bundle pilot completed.**

Implemented in the current codebase:
- Bounded PDF ingestion with page-level evidence references and content fingerprints (`tensorbench/pdf_evidence.py`).
- Rule-based proposals for a limited set of labelled fields, retaining page/evidence provenance and marking candidates unverified (`tensorbench/business_pdf_fields.py`).
- Existing normalized-record reconciliation and deterministic discrepancy checks (`tensorbench/business_evidence.py`).
- CLI workflow for explicit PDF field review, conflict detection and provenance-preserving normalized-document output; focused tests cover the review gate.

Not yet implemented or not yet demonstrated:
- OCR for scanned PDFs/images.
- Reliable table/line-item extraction with cell coordinates.
- Automated multi-document bundle orchestration that invokes reconciliation from reviewed PDF outputs.
- Complete contract → purchase order → delivery/acceptance → invoice workflow.
- Permissioned, de-identified real document bundles with labelled extraction/matching accuracy.
- Customer-grade tenant isolation, retention/deletion and security review.

Release interpretation:
- Extracted fields remain `proposed_unverified` until a human approves them. Only fully reviewed, conflict-free proposals can be emitted as normalized document fields.
- No OCR/table capability or business discrepancy accuracy is implied by the current parser tests.
- Do not ingest customer-confidential documents before privacy/security controls are verified.
