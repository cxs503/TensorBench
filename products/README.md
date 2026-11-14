# Four Evidence Products — Foundation

This directory defines four product verticals that share TensorBench's evidence and validation contracts. It is a product foundation and handoff specification, not a claim that the four products are already implemented.

## Product map

| Product | Primary user | First use | System of record |
|---|---|---|---|
| ResearchAudit | research teams, R&D groups | audit TensorKnowledge reports | TensorBench audit runs; source knowledge remains in TensorKnowledge |
| Physics Dataset Validator | physics-AI teams, simulation labs | ship-flow simulation datasets | TensorData dataset and quality records |
| Agent Achievement Evaluator | AI engineering teams, TensorPlatform | verify completed agent work packages | TensorBench evaluation runs; mission state remains in TensorPlatform |
| Business Evidence Engine | engineering, procurement and trading teams | cross-check contracts, orders, invoices | customer-controlled source documents; TensorBench audit evidence |

## Shared design

All four products use the common contracts in [shared contracts](../docs/PRODUCT_SHARED_CONTRACTS.md):
- evidence items point to immutable source locations and carry hashes;
- checks are versioned and predeclared;
- findings have severity, confidence, evidence links and reproducible rationale;
- reports distinguish measured/verified facts, model suggestions and unresolved questions;
- every run records software version, configuration, input fingerprints and reviewer actions.

Do not create a new database or duplicate TensorData/TensorKnowledge registries. Use adapters and stable identifiers. Product-specific rules belong in product modules, not TensorBench's generic runner.

## Product PRDs

- [ResearchAudit](research-audit/PRD.md)
- [Physics Dataset Validator](physics-dataset-validator/PRD.md)
- [Agent Achievement Evaluator](agent-achievement-evaluator/PRD.md)
- [Business Evidence Engine](business-evidence-engine/PRD.md)

## Handoff sequence

1. Platform integration agent: implement run submission and artifact/result linking against the shared contracts.
2. Product agents: implement one end-to-end vertical slice each, using real or explicitly synthetic-labelled fixtures.
3. Independent QA agent: maintain hidden holdout cases and score false positives/negatives.
4. Product owner: approve domain rules and customer-facing claims.

## Non-negotiable release gate

A product is not MVP-complete because it has a UI, LLM-generated report, passing unit tests, or merged PRs. It must ingest a real supported input, execute deterministic checks, preserve evidence references, produce a machine-readable result, and pass a blind evaluation set. AI-generated interpretations must be visibly separated from deterministic checks and human decisions.

## Implementation status and acceptance

The current implementation state is tracked in [STATUS.json](STATUS.json). Product release gates and evidence requirements are defined in [FOUR_PRODUCT_ACCEPTANCE_MATRIX.md](../docs/FOUR_PRODUCT_ACCEPTANCE_MATRIX.md). These are deliberately separate from the aspirational PRDs: a partially implemented product is not a real-world-verified product.
