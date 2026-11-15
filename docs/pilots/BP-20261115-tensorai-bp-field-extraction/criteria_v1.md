# Pilot criteria — BP-20261115-tensorai-bp-field-extraction (v1)

Frozen **before** the run. This file is the acceptance-criteria source of truth; the run
records `criteria_sha256` of these exact bytes. Thresholds are declared here and may not be
widened after a result is observed (`docs/SCENARIO_ACCEPTANCE_FRAMEWORK.md` §3 step ②).

Scenario: ingest one real business-plan PDF (internal consent, private) through the existing
TensorBench PDF ingestion chain (`pdf_evidence` → `business_pdf_fields` → field review →
structured record) and measure what the declared field spectra actually recover.

## Declared checks

| id | check | threshold (fixed now) | required |
|---|---|---|---|
| C1 | PDF ingestion | `status=complete`, every page `extraction_status=extracted`, `page_count` equals the page count of the source bytes, source SHA-256 equals the declared input fingerprint | yes |
| C2 | legacy spectrum coverage (`trade_documents_v1`, 5 fields) | report a proposal count per field; no averaging into a coverage score; a 0 is reported as 0 with a mechanism-level reason | yes |
| C3 | business-plan spectrum coverage (`business_plan_v1`, 10 fields) | ≥ 8 of 10 declared fields yield ≥ 1 proposal that carries a page locator | yes |
| C4 | page back-reference integrity | 100 % of accepted values carry `page_number ≥ 1`, `0 ≤ start_offset < end_offset ≤ len(page_text)`, `page_text_sha256`, `value_sha256`; any orphan value fails the check (0 tolerated) | yes |
| C5 | absence honesty | the field `funding_amount` yields exactly 0 proposals and the document's explicit non-disclosure sentence is located by a separate search; any inferred amount fails the pilot | yes |
| C6 | arithmetic invariants of extracted tables | funding-use rows sum to 100 % **exactly**; each revenue-mix row sums to 100 % **exactly**; roadmap windows are contiguous and cover 0–36 months **exactly** | yes |
| C7 | independent spot-check | ≥ 5 accepted fields are re-derived by a second code path (re-read PDF bytes, slice `page_text[start:end]`, recompute hashes) with exact page + offset + value match; 1 mismatch fails | yes |
| C8 | negative path | ≥ 3 corrupted copies (truncated body, non-PDF bytes, zero-byte file) each fail with the declared error type, CLI exit code 2, **no** output artifact written, and a §5 failure record filed per case; a silent success or an uncaught traceback fails | yes |
| C9 | private-input containment | the source PDF is never committed; repo artifacts carry no verbatim free-text value from the source (values only as masked prefix ≤ 4 chars + SHA-256) | yes |
| C10 | report contract | the pilot report validates against `schemas/validation-report.schema.json` with 0 errors; `overall_status` must be `partial` because the independent review ④ and the status publication ⑤ are out of scope for this mission | yes |

## Stopping rules

* C1 fails ⇒ stop, honest-FAIL, no field claim of any kind is reported as extracted.
* Any required check has no measurement ⇒ the check is `not_measured`, and the pilot status is
  `partial`, never `passed` (`docs/PRODUCT_SHARED_CONTRACTS.md` §4).

## Interpretation limits declared in advance

* Field proposals are regex label/table-shape suggestions, not OCR and not document truth. An
  accepted value proves "this span exists on this page of a PDF with this SHA-256", nothing more.
* One document, one language, one layout. Coverage numbers are **this document's** numbers and are
  not a population estimate for business plans in general.
* This mission may not set `scenario_validated=true` and may not sign its own review receipt
  (`docs/SCENARIO_ACCEPTANCE_FRAMEWORK.md` §3 step ④/⑤).