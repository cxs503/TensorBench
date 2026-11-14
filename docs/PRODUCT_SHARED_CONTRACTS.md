# Shared Contracts for Evidence Products

**Status:** v0.1 foundation contract. **Owner:** TensorBench. **Consumers:** ResearchAudit, Physics Dataset Validator, Agent Achievement Evaluator, Business Evidence Engine.

These contracts define interchange, not a shared monolithic runtime. Product services may be independently deployed. TensorData remains authoritative for governed dataset assets; TensorKnowledge remains authoritative for governed knowledge objects; TensorPlatform remains authoritative for missions, agents, permissions and orchestration.

## 1. Evidence item

An evidence item identifies a source artifact and the exact span/region supporting a finding. It must be possible for a reviewer to retrieve the source and verify its digest.

Required fields:
- `evidence_id`: stable identifier within the owning system;
- `source_type`: `file | dataset | code | run | url | database_record | image_region | table_cell | time_range`;
- `source_ref`: URI or stable system identifier;
- `sha256`: digest of the referenced immutable bytes or canonical record where applicable;
- `locator`: optional page/line/JSONPath/cell/time-range/spatial locator;
- `provenance`: source owner, acquisition time, source version and rights/permission reference.

A URL alone is not durable evidence. Capture the retrieved content or a versioned snapshot and hash it where legally permitted. Do not copy restricted source content into public reports.

## 2. Check definition

A check is versioned and declared before execution:
- `check_id`, `version`, `category`, `description`;
- `method`: deterministic rule, numerical test, statistical test, model-assisted analysis, or human review;
- `severity_default`;
- `parameters` and explicit applicability conditions;
- `expected_evidence`;
- `known_limitations`.

Model-assisted checks must record model/provider/version and prompt/template revision when available. They are advisory unless calibrated against a labelled evaluation set and explicitly promoted.

## 3. Finding

Each finding includes:
- `finding_id`, `check_id`, `status`: `confirmed | likely | inconclusive | not_applicable`;
- `severity`: `critical | high | medium | low | info`;
- `confidence` in [0,1] when a calibrated probability is available; otherwise omit it;
- `summary`, `rationale`, `evidence_refs[]`;
- `counter_evidence_refs[]` when relevant;
- `review_state`: `unreviewed | accepted | rejected | amended`;
- `limitations[]`.

Never turn absence of evidence into proof of absence. An inconclusive check is not a pass.

## 4. Validation report

A report records `report_id`, `schema_version`, `product_id`, `product_version`, `run_id`, `created_at`, `input_refs[]`, `input_fingerprints`, `checks[]`, `findings[]`, `summary`, `overall_status`, `artifacts[]`, and `provenance`.

Overall status is one of:
- `passed`: all required applicable checks passed;
- `failed`: at least one required check failed;
- `inconclusive`: required checks could not reach a defensible verdict;
- `partial`: some checks were not run or inputs were incomplete.

A product may not emit `passed` when required checks are missing, unmeasured, or inconclusive.

## 5. Asset record

An asset record describes a reusable output, not merely a task or PR:
- stable `asset_id`, `asset_type`, `title`, `owner_project`;
- source commit/revision and producing run/work-package IDs;
- input and output fingerprints;
- license/rights status and dependencies;
- validation report references;
- maturity: `A0_idea | A1_implemented | A2_verified | A3_reusable | A4_adopted`;
- reuse/adoption events and customer/revenue references where disclosure is permitted.

Do not count A0/A1 assets as validated assets. A2 requires evidence; A3 requires documented reuse/deployment; A4 requires external adoption or recurring operational use.

## 6. Evidence and privacy

- Keep original inputs immutable; derived artifacts are new versioned assets.
- Hashes prove byte identity, not truth, ownership or permission.
- Store customer documents and personal data only in approved storage with least privilege, encryption, retention and deletion controls.
- Public demo fixtures must be synthetic and labelled; never pass synthetic fixtures off as customer evidence.
- Redact secrets and unnecessary personal data from logs and reports.
- Rights unknown = quarantined; no training, publication or redistribution until cleared.

## 7. Acceptance semantics for scenario claims

Sections 1–6 define interchange. How a product turns a run into an acceptance claim —
`scenario`/`criteria_freeze`/`review_receipt` report blocks, the six independent review checks, the
`acceptance-status.schema.json` binding for `products/STATUS.json` and the failure/regression
record format that points at the platform `negative_knowledge_ledger` — is specified in
[SCENARIO_ACCEPTANCE_FRAMEWORK.md](SCENARIO_ACCEPTANCE_FRAMEWORK.md).

## 8. Interoperability

Products should export JSON conforming to the schemas in `schemas/`. API transport, authentication and asynchronous job lifecycle are deployment concerns and must be agreed with TensorPlatform before implementation. Do not couple products through private database tables or shared internal Python imports.
