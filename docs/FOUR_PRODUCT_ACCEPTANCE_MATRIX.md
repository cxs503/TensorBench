# Four-product acceptance baseline

**As of:** 2026-11-14  
**Purpose:** keep implementation claims, test evidence and real-world release evidence separate.

## Status vocabulary

| Status | Meaning |
|---|---|
| implemented | Executable code exists and focused automated tests cover the declared behavior. |
| partially_implemented | Some planned capabilities exist, but material release requirements remain absent. |
| not_implemented | No executable implementation has been verified. |
| real_world_verified | A permissioned real workflow passed its declared acceptance set with retained evidence and independent review. |

A passing unit-test suite never upgrades a product to real_world_verified. Missing or unsupported evidence is inconclusive, never a pass.

## Current product state

| Product | Current state | Real workflow verified? | Immediate next gate |
|---|---|---:|---|
| ResearchAudit | Partially implemented: citation/provenance integrity checks exist; semantic support and independent review workflow remain open. | No | Audit one permissioned report, bibliography and source bundle; retain reviewer receipt. |
| Physics Dataset Validator | Partially implemented: CSV structure, units, ranges, leakage and rights checks exist; conservation, boundary/initial conditions and multimodal alignment remain open. | No | Implement one explicit conservation profile and test a real TensorLBM flow export plus labelled corruptions. |
| Agent Achievement Evaluator | Partially implemented: commit-pinned evidence package checks and explicit publish path exist; automatic mission/CI collection and isolated execution remain open. | No | Collect one real mission, linked PR, commit and CI evidence read-only; retain human grading. |
| Business Evidence Engine | Partially implemented: PDF page evidence, limited field proposals and normalized reconciliation exist; OCR, tables and approved-field handoff remain open. | No | Complete a permissioned multi-document PDF → review → normalization → reconciliation run and measure accuracy. |

## Machine-checkable acceptance

The six-deliverable framework that makes the record below machine-checkable — scenario
specification, frozen criteria, evidence requirements, independent review receipt (six checks),
`products/STATUS.json` v2 schema and the failure/regression record format — is
[SCENARIO_ACCEPTANCE_FRAMEWORK.md](SCENARIO_ACCEPTANCE_FRAMEWORK.md). It extends this baseline;
it does not replace the status vocabulary or the release gates below.

## Mandatory acceptance record per product

Every acceptance run must retain:

- immutable input fingerprints and source locators;
- product version, rule/profile version and configuration;
- declared acceptance criteria and applicability assumptions;
- command/API invocation and environment;
- raw test/check outputs, including failures and skipped checks;
- findings with evidence references and pass / fail / inconclusive;
- reviewer identity/role, decision, timestamp and rationale;
- labelled evaluation metrics where a holdout set exists.

## Release gates

1. **G0 — executable slice:** supported input → deterministic checks → machine-readable report.
2. **G1 — evidence integrity:** immutable provenance, reproducible run and explicit inconclusive behavior.
3. **G2 — real workflow:** at least one permissioned real input bundle and independently reviewable output.
4. **G3 — calibrated pilot:** labelled holdout, per-defect precision/recall, false acceptance and false rejection.
5. **G4 — operational readiness:** security/privacy, retention, access control, observability and documented support boundaries.

Do not claim MVP completion at G0 or G1. A product-facing pilot requires G2; wider release requires G3 and applicable G4 controls.

## Ownership boundaries

- TensorKnowledge owns knowledge assets and claim/evidence records; ResearchAudit supplies audit runs and findings.
- TensorData owns dataset identity, versions and rights; Physics Dataset Validator supplies quality evidence.
- TensorPlatform owns mission lifecycle and agent policy; Agent Achievement Evaluator supplies independently reviewable outcome evidence.
- Business customers own source documents and business decisions; Business Evidence Engine supplies traceable extraction and discrepancy evidence.
