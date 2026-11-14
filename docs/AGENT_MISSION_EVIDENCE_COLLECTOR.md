# Agent Mission Evidence Collector

This increment normalizes **read-only snapshots** into TensorBench's existing
revision-pinned Agent Achievement evaluator. It is not yet a live TensorPlatform
API connector and does not execute candidate code.

## Input contract

A JSON object contains:

- `mission`: TensorPlatform mission row (`id`, `repo`, `goal`, `status`,
  `claimed_by`), optionally with predeclared `acceptance_criteria`.
- `pull_request`: GitHub pull-request object with immutable `head.sha` and a
  `files` array (each file has `filename`).
- `checks`: `check_runs` and/or commit `statuses`, each pinned to a commit SHA.
- Optional top-level `acceptance_criteria` overrides mission criteria.

## Safety and interpretation

- No write operations are performed against TensorPlatform or GitHub.
- No shell commands or candidate code are executed.
- CI evidence is accepted only when its commit SHA matches the PR head SHA.
- Pending, missing, failed, or stale CI remains not-run / inconclusive / failed;
  it is never converted into a pass.
- If no predeclared acceptance criteria exist, the mission goal is retained as
  context but a synthetic non-evaluable criterion forces an inconclusive result.
- A successful PR/CI snapshot proves only that recorded checks passed on that
  revision. It does not prove that the requested feature is correct.
- The collector does not assign S/E grades or publish an evaluation.

## Current boundary / next increment

The current TensorPlatform mission row contract exposes mission identity, repo,
status, claimant and timestamps; the GitHub PR association is not a first-class
field in the mission row. This adapter therefore consumes an explicitly linked
PR snapshot supplied by a trusted collector. The next integration must add a
permissioned, read-only platform mission endpoint / connector and a GitHub PR
lookup policy, then retain raw responses and check-run logs as evidence.
