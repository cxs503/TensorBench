# Agent Achievement Evaluator — Product Requirements

**Product ID:** `agent-achievement-evaluator` · **Status:** foundation / not implemented · **Initial user:** TensorPlatform.

## Problem and outcome

Task counts, PR counts, documentation volume and agent self-reports are weak proxies for engineering progress. This evaluator determines whether a work package produced the promised working capability, whether its tests actually exercise it, and whether the result is independently reproducible and reusable.

## Evaluation workflow

1. Resolve work-package/mission ID, declared goal, acceptance criteria and baseline before inspecting outcome.
2. Snapshot candidate commit, changed files, test commands/results, benchmark records and artifacts.
3. Run static checks and tests in an isolated environment; inspect test relevance and coverage of changed behavior.
4. Compare observed behavior with predeclared acceptance criteria and baseline.
5. Produce evidence-linked findings, maturity grade and reviewer decision; publish result to TensorPlatform through a versioned API.

## Evaluation dimensions

- Goal/acceptance coverage: each criterion maps to code, test and observed output.
- Functional reality: code path is reachable and works on representative inputs; reject placeholder/mock-only behavior.
- Test validity: tests fail when the behavior is intentionally broken; detect vacuous tests and over-mocking.
- Algorithm/domain correctness: delegated to domain-specific validators and benchmarks; evaluator must not invent scientific truth.
- Regression/security/reliability: tests, static analysis, dependency/license and security findings.
- Reproducibility: exact commit, environment, commands, logs and artifacts.
- Reuse/value: documented interface, integration consumer, measured performance/cost benefit or verified adoption.

## Output and scoring

Output per-dimension status, findings, evidence references, test provenance, confidence/calibration metadata and maturity A0–A4. Do not collapse everything into one opaque score. A failed required criterion blocks `passed`; missing evidence is `inconclusive`. Credit and agent performance consequences remain a TensorPlatform policy decision.

## Blind evaluation

Create ≥100 labelled work-package examples: genuine completed features, partial implementations, docs-only changes, mock-only demos, invalid tests, regressions and strong reusable improvements. Hold out examples from developers. Report confusion matrix, precision/recall by defect type and inter-reviewer agreement. Target false acceptance ≤5% for the pilot; report false rejection separately.

## Non-goals

Autonomous legal/HR performance decisions, judging agent identity or intent, or deciding scientific correctness without domain evidence.

## First vertical slice

Evaluate 20–30 real, completed TensorPlatform missions across code, docs-only, test-only, and feature changes. Manually label ground truth before running evaluator. Use a read-only GitHub snapshot and disposable test environment; do not merge, close or modify PRs.


## Implementation status (verified against repository source, 2026-11-14)

**Overall: partially implemented; not yet verified in a real TensorPlatform mission workflow.**

Implemented in the current codebase:
- Work-package/acceptance evidence models and deterministic evidence validation in `tensorbench/achievement.py`.
- Commit-pinned evidence and criterion/evidence association.
- Test/change/artifact completeness checks and report generation.
- Explicit publishing path to TensorPlatform; publishing is not automatic.
- Unit and publish-path tests exist (`tests/test_agent_achievement_evaluator.py`, `tests/test_achievement_platform_publish.py`).

Not yet implemented or not yet demonstrated:
- Automatic read-only collection of a real mission, linked PRs, commits, GitHub check-runs and job logs from TensorPlatform/GitHub.
- Disposable isolated execution of candidate code and independent test-quality assessment (mutation/vacuity/over-mocking checks).
- Blind-labelled holdout corpus and measured false-acceptance/false-rejection rates.
- A real mission evaluated end-to-end and independently reviewed.

Release interpretation:
- Passing current unit tests proves the implemented evidence-package checks, not that an agent delivered the promised feature.
- Missing platform/GitHub evidence must remain `inconclusive`; no automatic maturity grade or agent-performance decision.
- Human reviewer retains grade/decision authority until calibration and independent review gates are met.
