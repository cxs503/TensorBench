# Business Evidence Engine — 12-minute onboarding

This is the hands-on quickstart for the PDF side of the Business Evidence Engine. It walks the
four real commands in order, on a committed synthetic document, so you can see every artifact
before you point the chain at a document you actually have permission to process.

Everything below was executed to produce `docs/m22925/demo/` (see `timing.json` for the per-stage
timings and `artifacts` for the sha256 of every file). Re-run it with
`python3 docs/m22925/run_demo.py`.

## 0. What the chain does (and refuses to do)

```
PDF ──extract-pdf──▶ page-addressable text evidence
      ──propose-pdf-fields──▶ unverified field proposals (page + offsets + value hash)
      ──review-pdf-fields──▶ accepted/rejected fields ─▶ normalized document
      ──reconcile-business──▶ cross-document checks (arithmetic, PO match, delivery qty, bank change)
```

Refused by design: OCR, table-cell reconstruction, legal/fraud verdicts, payment execution.
A "no text" page is reported as `no_text`, never as empty content.

## 1. Install

```bash
pip install 'tensorbench[pdf]'      # or: pip install pypdf
python -m tensorbench --version     # tensorbench 0.2.0
```

## 2. Wrap a PDF into page evidence

```bash
python -m tensorbench extract-pdf \
  --input docs/m22925/demo/demo_invoice.pdf \
  --source-ref 'demo://m22925/demo-invoice/v1' \
  --output docs/m22925/demo/1_pages.json
```

`--source-ref` must be a stable id from *your* document system; it is never inferred from the path.
You get `source.sha256` (whole file), and per page: `page_number`, `text`, `page_text_sha256`,
`evidence_id`, `status`. An encrypted PDF is rejected, not bypassed.

## 3. Propose fields against a declared spectrum

```bash
python -m tensorbench propose-pdf-fields \
  --input docs/m22925/demo/1_pages.json \
  --spectrum trade_documents_v1 \
  --output docs/m22925/demo/2_proposals.json
```

Two spectra ship today: `trade_documents_v1` (invoice / contract / PO number, date, total) and
`business_plan_v1` (10 fields: title, version, issue date, disclaimer, financing stage, funding
amount, table label+percent, ratio blocks, roadmap windows, market references). A proposal is
**unverified**: it carries the raw text slice, page number, byte offsets, and a value hash — not a
decision. Fields that the document does not state produce no proposal (`funding_amount` in the
pilot: 0 proposals, correctly).

## 4. Record review decisions

```bash
python -m tensorbench review-pdf-fields \
  --input docs/m22925/demo/2_proposals.json \
  --decisions docs/m22925/demo/3_decisions.json \
  --reviewer 'your-name' \
  --document-type invoice --doc-id INV-2026-001 \
  --output docs/m22925/demo/4_reviewed.json
```

`decisions.json` is `[{"proposal_id": "...", "decision": "accept"|"reject"}]`. Without a decision a
proposal stays `proposed_unverified` — silence never promotes a value. Two different values under
the same `(field, subject)` are reported as a conflict and withheld. The command exits 1 if any
proposal is still pending, so it is safe in scripts.

The demo's reviewer string says `demo-auto-review (… not a human reviewer)` on purpose: the
acceptances were generated, and the record says so rather than implying a human signed off.

## 5. Reconcile against the other documents

```bash
python -m tensorbench reconcile-business \
  --input docs/m22925/demo/5_bundle_happy.json \
  --output docs/m22925/demo/6_reconcile_happy.json        # overall_status: passed

python -m tensorbench reconcile-business \
  --input docs/m22925/demo/7_bundle_mismatch.json \
  --output docs/m22925/demo/8_reconcile_mismatch.json     # overall_status: failed
```

The bundle is `{"documents": [...]}` with `doc_id` / `document_type` ∈ {contract, purchase_order,
delivery, invoice, payment} and, per document, `source_ref` + `sha256` (without them the provenance
check is `inconclusive`, not `passed`). The mismatch bundle differs from the consistent one by a
single line item (1234.00 vs 1234.50) and is caught by `invoice.purchase_order_match`.

## 6. Reading the output

| Field | Meaning |
|---|---|
| `overall_status` | `passed` / `failed` / `inconclusive`. `inconclusive` means a required input was missing — it is *not* a pass |
| `checks[].state` | `passed` / `failed` / `inconclusive` / `not_measured` per rule |
| `findings[]` | one entry per failed/inconclusive check, with severity and evidence refs; a discrepancy signal, never a fraud or legal conclusion |
| `summary` | counts only (`document_count`, `invoice_count`, `finding_count`) — no verdict language |

## 7. Before you trust it on a real document

* Run it under a declared `permission_basis`; the pilot used `internal_consent` and kept verbatim
  text outside the repository (`private_pointer.json`).
* Expect the coverage to be *this document's* coverage: one layout, one language. The pilot got
  9/10 fields on a business plan and 0/5 with the trade-document spectrum — the second number is a
  spectrum mismatch, not a broken document.
* Multi-column tables: only the first percentage column is captured (`table_label_percent`).
* No labelled ground truth means no precision/recall claim. Say "partial", as the pilot does.

Known limits are enumerated in `products/STATUS.json` (`BE.not_implemented_or_unverified`) and
`docs/m22925/value_evidence.json`.