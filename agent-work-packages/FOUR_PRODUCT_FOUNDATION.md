# Agent Work Package: Four Evidence Products Foundation

**Package ID:** `TB-WP-FOUR-PRODUCTS-FOUNDATION-001` · **Status:** ready for platform decomposition · **Priority:** P0.

## Objective

Implement the smallest executable vertical slices for the four products defined in `products/*/PRD.md`, reusing TensorBench contracts and existing TensorData/TensorKnowledge services. This package is not permission to create four parallel frameworks.

## Work streams

### WP-A — Shared contract implementation
- Implement strict JSON Schema validation for evidence item, finding, validation report and asset record.
- Add canonical serialization and SHA-256 fingerprint helpers.
- Add fixtures for valid, invalid, missing-evidence and inconclusive records.
- Tests must prove invalid records are rejected and hashes are deterministic.

### WP-B — ResearchAudit
- Inspect TensorKnowledge's four-contract schemas and existing audit scripts before coding.
- Implement a read-only adapter that ingests one real report and bibliography.
- Start with citation presence, reference metadata and claim/evidence traceability.
- Export a shared validation report; do not duplicate the knowledge graph or review state machine.

### WP-C — Physics Dataset Validator
- Inspect TensorData's quality rules, immutable dataset manifests and report API.
- Implement a profile-driven validator adapter, beginning with schema/units/time-axis checks.
- Add known-good and deliberately corrupted labelled fixtures.
- Publish quality findings through TensorData's existing quality workflow; no new dataset registry.

### WP-D — Agent Achievement Evaluator
- Inspect TensorPlatform mission/work-package contracts and TensorBench runner/publish path.
- Implement read-only snapshot ingestion and objective checks for criterion-to-test mapping, test execution, changed-code coverage and artifact provenance.
- Add a blind-labelled fixture corpus; do not let the evaluated agent author its own labels or thresholds.

### WP-E — Business Evidence Engine
- Implement a local batch prototype using permissioned synthetic fixtures first.
- Extract structured values with page/cell locators; exact arithmetic and key matching are deterministic.
- Add discrepancy report export and reviewer decisions. No customer data until privacy controls are reviewed.

### WP-Q — Independent quality
- Own hidden holdout cases and reference labels.
- Run tests from clean environment and report precision, recall, false acceptance, false rejection and unresolved cases.
- Developers may not approve their own product's release gate.

## Required deliverables

1. Four runnable end-to-end vertical slices, each with CLI/API invocation documented.
2. Machine-readable reports conforming to shared schemas.
3. Labelled evaluation set and test protocol; hidden holdout controlled by WP-Q.
4. Test logs, source revisions, dependency/license inventory and known limitations.
5. One demo bundle per product, clearly labelled real-permissioned or synthetic.
6. Asset records with maturity A0–A4; no A2+ without independent evidence.

## Exit criteria

- No mock-only path represented as a completed feature.
- At least one real supported input per product; synthetic inputs are allowed for adversarial tests only and must be labelled.
- Deterministic checks have exact expected outputs.
- Blind evaluation metrics are reported per defect class.
- All findings link to retrievable evidence.
- A failed/inconclusive required check cannot be converted to pass by an LLM summary.
- Product owner accepts scope; independent QA signs off on measured quality.

## Platform handoff protocol

The platform may split these work streams into smaller tasks after inspecting the target repositories. Each task must name the exact repository/path, acceptance criteria, expected test command, input fixture, output artifact and reviewer. Do not open mass PRs until each work stream has a runnable slice and its own test evidence.
