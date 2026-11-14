# PDF Evidence Ingestion (Business Evidence Engine)

## Purpose

The PDF adapter converts an authorized source PDF into page-addressable text evidence. Each page retains the original source reference, whole-file SHA-256, page number, and a hash of the extracted page text. Downstream extraction and review can cite `evidence_id` and `locator.page_number`.

## Install and run

```bash
pip install 'tensorbench[pdf]'
tensorbench extract-pdf \
  --input purchase-order.pdf \
  --source-ref 'procurement://case-123/po-001/v1' \
  --output po-001.pages.json
```

The `source-ref` must be a stable identifier from the caller's document system; it is not inferred from a local path.

## Output semantics

- `source.sha256` fingerprints the exact input bytes.
- Each page has `evidence_id`, `source_ref`, `sha256`, and a page-number locator.
- `page_text_sha256` fingerprints the extracted text for that page.
- `status=partial` means one or more page text extractions failed; affected pages are marked `extraction_failed`.
- `no_text` is not a successful extraction of content. It commonly indicates a scanned page.

## Boundaries

This adapter does **not** perform OCR, preserve exact PDF character bounding boxes, extract verified table cells, infer document fields, or interpret contracts. PDF text extraction can reorder columns or flatten tables. Do not feed the extracted text into reconciliation as trusted structured data without a separate field-extraction step and page-level human/automated verification. Encrypted PDFs are rejected rather than bypassed.
