# Changelog

All notable changes to TensorBench. Versions follow the package version in
`tensorbench/__init__.py` (exposed by `python -m tensorbench --version`).

## 0.2.0 — 2026-11-16

Business Evidence Engine packaging increment (mission m22925). No behaviour of the extraction or
reconciliation rules changed: this release makes the existing surface documented, versioned and
walkable end to end.

### Added

* `tensorbench --version` — the version was previously only importable, not printable.
* `docs/m22925/DEMO.md` — onboarding quickstart over the four BE commands
  (`extract-pdf` → `propose-pdf-fields` → `review-pdf-fields` → `reconcile-business`), written
  against a committed run rather than a sketch.
* `docs/m22925/demo/` — artifacts of that real run: a synthetic 1-page invoice PDF, per-stage JSON,
  a consistent bundle (`overall_status=passed`) and a deliberately inconsistent one
  (`overall_status=failed` on `invoice.purchase_order_match`), plus `timing.json` with per-stage
  wall clock and the sha256 of every artifact.
* `docs/m22925/run_demo.py`, `docs/m22925/make_demo_pdf.py` — reproducible generator of the demo
  (dependency-free PDF writer; only `pypdf` is needed to read it back).
* `docs/m22925/check_verdict_row.py` — re-binds the published BE claim to its evidence: pinned refs
  against `origin/main` blobs, recomputed `criteria_sha256`, receipt pass-preconditions, and the
  maturity-ledger row.
* `tests/test_be_scenario_publish.py` — 12 guards for the published `scenario_validated=true` claim.
* `acceptanceEvidence.maturity_verdict_ref` (optional, `null` allowed) in
  `schemas/acceptance-status.schema.json`, so a published claim can cite the ledger row that
  records its review. The object stays closed to unknown keys; AE / RA / PV do not carry it.

### Changed

* `products/STATUS.json` — BE `scenario_validated=true`, with `acceptance_evidence` bound to
  `review_receipt_amended.json` @ `ee5d828`, `validation_report.json` @ `8c18865`, the frozen
  criteria hash and the ledger row `id=911`. `not_implemented_or_unverified` and
  `external_partial_state` restated against the pilot's own declared limits.
* `docs/SCENARIO_ACCEPTANCE_FRAMEWORK.md` §8 — the four-line state table and the sentence claiming
  "no pilot has been run" now reflect the published PV and BE lines.
* `docs/business-evidence-pdf-ingestion.md` — points at the quickstart instead of duplicating it.

### Fixed

* Nothing in the product code paths. Rule changes would have invalidated the reviewed pilot; the
  pilot inputs and their fingerprints are unchanged.

## 0.1.0

Initial package: benchmark execution and evidence collection, evidence-bundle contracts, isolated
run attachment, achievement evaluation/publication, and the Business Evidence Engine modules
(`pdf_evidence.py`, `business_pdf_fields.py`, `business_evidence.py`) with the CLI surface.