# AE-01 Mission Evidence Collector

Read-only collector that turns one TensorPlatform mission into a sealed, auditable
evidence bundle: `evidence/<mission_id>.json`.

## Why the brief's starting premise had to be corrected

The work order stated this repository was a from-scratch skeleton (`cli.py` +
`runner.py`) with zero merge PRs, and that PRs #12–#18 did not exist. The
repository contradicts that: `git log` shows **188 commits and 10 merge PRs**
(#3, #10–#18), including `feat/mission-evidence-collector`. Building a "new" collector
on top of a fabricated empty baseline would have duplicated `tensorbench/live_mission.py`
and misreported `products/STATUS.json`.

What was actually missing, and what this mission added:

| # | Requirement | State before | Reconciled here |
|---|---|---|---|
| ① | `schemas/evidence_bundle.json` | absent (only `evidence-item.schema.json`) | **added**, v1.0.0, draft 2020-12, `additionalProperties: false` |
| ② | read-only TensorPlatform client | `live_mission.py` required `head_commit` and aborted otherwise; no login-from-creds path | **added** `tensorbench/collect.py`: `/auth/login` with `/root/.eco_admin_creds.json`, mission metadata + deliverable fingerprints |
| ③ | GitHub PR/commit/CI association | only "PR containing the mission head commit" | **added** primary `head=agent/m<id>` resolution with commit-association fallback, plus check-runs/statuses for the exact head SHA |
| ④ | CLI `collect --missions m1,m2` → `evidence/<mid>.json` | only `collect-mission --mission-id N` single mission, no `evidence/` output | **added** `tensorbench collect` |
| ⑤ | `products/STATUS.json` four lines with two independent fields | one flat list, no `code_implemented`/`scenario_validated` split | **rewritten** v2.0.0 for AE/BE/RA/PV + baseline reconciliation |
| ⑥ | ≥5 real mission bundles as fixtures + negative + tamper tests | no `tests/fixtures/` at all | **added** 6 live bundles (5 with PR + 1 without PR) + 21 tests |

## Bundle contract (v1)

```
schemas/evidence_bundle.json
  mission_id, collected_at, collector{mode: live_read_only}
  platform{api_base, mission_endpoint, payload_sha256}
  mission{id, repo, status, claimed_by, created_at, finished_at, goal, goal_sha256, result_sha256}
  commit{sha, source, matches_mission_head}          | "missing"
  pull_request{number, state, merged, merged_at, merge_commit_sha, head_ref, head_sha,
               base_ref, changed_files, additions, deletions, html_url, resolution} | "missing"
  ci{conclusion: passed|failed|not_run|inconclusive, check_runs[], statuses[]} | "missing"
  deliverables[{path, status, additions, deletions, blob_sha, sha256, bytes, origin}]
  missing[]                 # every unevidenced field path, explicit
  source_fingerprints{}     # SHA-256 of each raw upstream payload
  integrity{bundle_sha256, digest_scope}
```

Rules enforced by the code, not by convention:

1. **No inference.** An absent upstream fact is the literal string `"missing"` and
   is repeated in `missing[]`. A mission with no PR therefore has
   `pull_request == "missing"`, `commit == "missing"`, `ci == "missing"`,
   `deliverables == []` (real example: mission 20111).
2. **Commit-exact.** The PR is tied to the mission by head branch `agent/m<id>`
   (resolution `branch_head`) or, if the branch is gone, by the PR that contains
   the mission-declared head commit (resolution `commit_association`); more than one
   candidate commits is an error, never a guess.
3. **Fingerprints are real bytes.** Each deliverable's `sha256` is computed from the
   file content fetched at the pinned commit
   (`GET /repos/{repo}/contents/{path}?ref={sha}`). Files above the GitHub inline
   limit (>1 MB) keep `sha256 = "missing"` but record the true `bytes` — see
   `tensorcad-series60/hull.obj` in mission 19694.
4. **CI is never upgraded by silence.** No check-runs ⇒ `not_run` (not a pass);
   any failure ⇒ `failed`; any pending ⇒ `inconclusive`.
5. **Self-sealing.** `integrity.bundle_sha256` is SHA-256 over the canonical JSON of
   the bundle minus `integrity`, so one flipped byte invalidates it offline.

## Usage

```bash
# real collection (read-only)
python -m tensorbench.cli collect --missions m19812,m19694,m18757 --out-dir evidence

# offline / no content download
python -m tensorbench.cli collect --missions m19812 --out-dir /tmp/ev --no-contents
```

Exit codes: `0` all bundles written, `2` at least one mission could not be collected
(successful bundles are still written; per-mission errors go to stderr).

Credentials: platform `username`/`password` from `/root/.eco_admin_creds.json` used
against `POST {base}/api/v1/auth/login`; GitHub token from the
`https://x-access-token:<token>@github.com` line of `/root/.git-credentials`, the
same convention the platform pusher uses. Tokens are held in memory only and are
never written into a bundle.

## Fixtures (real, not mocked)

`scripts/collect_evidence_fixtures.py` performs a live read-only collection and
writes, per mission, the raw upstream payloads (`tests/fixtures/recorded/m<id>.json`,
including the recorded file bytes used to recompute fingerprints) and the sealed
bundle (`tests/fixtures/real_missions/<id>.json`). `MANIFEST.json` lists missions,
SHAs and bundle digests.

Recorded by this mission (all live, `2026-11-14T09:19Z`):

| mission | repo | PR | commit | CI | deliverables | notable missing |
|---|---|---|---|---|---|---|
| 19812 | TensorCAD | #456 | 97bf6bb | not_run | 1 | `ci.check_runs` |
| 19694 | TensorCAD | #455 | f8fb2dd | not_run | 13 | `deliverables[1](hull.obj).sha256` (>1 MB) |
| 18757 | TensorFVM | #636 | 8dc2bb2 | not_run | 8 | `ci.check_runs` |
| 18685 | TensorFVM | #635 | b3f214c | not_run | 11 | `ci.check_runs` |
| 18524 | TensorFVM | #634 | 2e6f3ac | not_run | 9 | `ci.check_runs` |
| 20111 | TensorCAD | — | — | — | 0 | `pull_request`, `commit.sha`, `ci.conclusion`, `deliverables` |

`not_run` for CI is itself the honest finding: these repositories attach no
check-runs or commit statuses to the PR head, so CI success cannot be asserted.

## Tests

`tests/test_evidence_bundle.py` — schema validation of all 6 real bundles, digest
self-consistency, one-hex-character tamper detection, single-field tamper detection,
`pull_request == "missing"` negative case, unavailable-fingerprint handling,
mission/id mismatch rejection, CI aggregation table.

`tests/test_collect_cli.py` — offline interface-contract tests that replay the **real
recorded payloads** through `collect._request_json` and assert the shipping client
reproduces the recorded bundle field-by-field (mission, commit, PR, CI, deliverable
SHA-256); nonexistent mission id error; CLI writes one bundle per mission and keeps
going after a failure with exit 2; id parsing; creds-file login; git-credentials token.

## Pre-flight checks (三查)

- `negative_knowledge_ledger`: `GET /api/v1/tensor/negative-knowledge` reachable
  (100 entries). Keyword filtering (`q=TensorBench`) is not honoured by this API
  version (the query returns the unfiltered ledger), so no prior TensorBench entry
  could be isolated by keyword; entries inspected are mission-loop/gate failures of
  other repositories.
- `knowledge_base` capability and `feature_ledger` (PROD-AE anchor): **not exposed**
  by the running API version (`/tensor/capability*`, `/tensor/feature_ledger` ⇒ 404,
  OpenAPI document disabled). Status: WITHHELD — not queried, not claimed.
- Repository ground truth instead of a claimed ledger: `git log` (188 commits,
  merges #3, #10–#18) plus module inventory, which is what falsified the empty-repo
  premise.

## Self-verification checklist

| Acceptance item | How verified | Result |
|---|---|---|
| ① bundle schema with mission/PR/commit/CI/deliverable SHA-256/timestamp/missing | `schemas/evidence_bundle.json` + `jsonschema.Draft202012Validator.check_schema` and validation of 6 real bundles | PASS |
| ② read-only platform client, creds-file login, deliverable fingerprints | live collection of 6 missions via `/auth/login` + `/tensor/missions/{id}` + contents API | PASS |
| ③ GitHub PR `head=agent/m<id>`, commit, CI conclusion | 5/6 bundles resolve `branch_head` with exact head SHA; `not_run` recorded where no CI exists | PASS |
| ④ `tensorbench collect --missions m1,m2` → `evidence/<mid>.json` | live run + CLI tests (`evidence/19812.json`) | PASS |
| ⑤ `products/STATUS.json` AE/BE/RA/PV × `code_implemented`/`scenario_validated` | file present; `scenario_validated=false` everywhere; baseline premise rejection documented | PASS (with documented deviation on AE/BE `code_implemented`) |
| ⑥ ≥5 real bundles + negative + tamper tests | 6 bundles; `test_mission_without_pull_request_records_pr_as_missing`; `test_one_byte_fingerprint_tamper_changes_digest_and_is_detected` | PASS |
| implementation/test separation, no mock substitution | tests read live bundles or replay recorded real payloads; no hand-written fake mission payload is used to assert a positive result | PASS |
| commit SHA + input fingerprints retained | `commit.sha`, `source_fingerprints.*`, `integrity.bundle_sha256`, `fixture.recorded_raw_sha256` | PASS |

## Limitations

- CI association is per-commit check-runs/statuses only; workflow-run logs are not collected.
- Deliverables are limited to `--max-deliverables` (default 25) PR files; files >1 MB
  have no SHA-256 (recorded `bytes` only).
- Mission 20111 demonstrates the no-PR path; the platform does not store
  platform-side deliverable fingerprints, so all fingerprints come from GitHub bytes.
- `scenario_validated` remains false for every product line: no independent review
  receipt exists yet.