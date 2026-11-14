# Agent Achievement Evaluator — executable first slice

The first TensorBench evaluator checks whether an agent work package has a
revision-pinned, traceable evidence bundle. It is a pre-merge evidence gate,
not a replacement for domain benchmarks or independent code review.

## Run

```bash
tensorbench evaluate-work-package --input work-package-evidence.json --output evaluation.json
```

## Required input

- Work-package ID and exact candidate commit/revision.
- Predeclared acceptance criteria, including whether each criterion requires code and tests.
- Changed-file inventory.
- Test outcomes, each pinned to the exact candidate revision and linked to run-log artifacts.
- Artifact references with SHA-256 and source revision.

## Checks

- Rejects empty or documentation-only deltas when implementation code is required.
- Requires every acceptance criterion to link to existing evidence artifacts.
- Requires evidence artifacts to be pinned to the candidate revision.
- Requires linked tests to pass on the exact candidate revision and to carry resolvable run-log references.
- Marks missing or stale evidence inconclusive; failed required tests fail the work package.

## Important limitation

This first slice validates the completeness and consistency of supplied evidence.
It does not independently fetch GitHub data, execute arbitrary candidate code,
detect vacuous tests, prove feature reachability, or assess scientific correctness.
The platform adapter must obtain CI/test evidence from trusted GitHub workflow
records and a sandboxed test runner. A later independent evaluator should add
mutation testing, regression probes, domain benchmarks and blind-labelled
false-acceptance/false-rejection measurement.
