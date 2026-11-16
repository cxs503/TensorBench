# PV line publishes `scenario_validated=true` (mission m22761)

Framework: `docs/SCENARIO_ACCEPTANCE_FRAMEWORK.md` §3 step **⑤ Publish status**.
Product line: **PV — Physics Dataset Validator** (`cxs503/TensorData`).
Date: 2026-11-16. Only PV was touched; AE / RA / BE are byte-identical.

## 1. The three published facts

| Fact | Value | Where it comes from |
|---|---|---|
| `scenario_validated` | `true` | review receipt verdict `pass` (§3.4 preconditions all met) |
| `acceptance_evidence.scenario_id` | `pv-kcs-ex1-20261115-prereg-column-acceptance` | `pilot_report.json` → `scenario.scenario_id` |
| `code_implemented` | `true` | schema/contract rule `scenario_validated=true ⇒ code_implemented=true`; justified by committed code at the reviewed commit |

`code_implemented` had to move with the publish: `tensorbench/contracts.py::_status_errors`
rejects `code_implemented=false, scenario_validated=true`. It is not a courtesy upgrade — the
PV chain is committed at the reviewed commit and covered by 96/96 tests (review receipt,
`regression_scope`).

## 2. Evidence binding (every ref is commit-pinned, not a moving branch)

| Field | Bound artefact | SHA-256 |
|---|---|---|
| `validation_report_ref` | `TensorData@857a189ee66cfda0fc208556b1316e25ff2e2104:artifacts/pv-pilot/ex1_kcs/pilot_report.json` | `7cbf516a9d563a983b705fea40d30cdf68a3ca25260b839ec203769d6a8f100a` |
| `review_receipt_ref` | `TensorData@857a189ee66cfda0fc208556b1316e25ff2e2104:artifacts/pv-pilot/ex1_kcs/review_receipt.json` | `db77659dc634f016226be6c6b4d720b6d46170eb70db4ad044c1aeca20fe491e` |
| `criteria_sha256` | `artifacts/pv-pilot/ex1_kcs/criteria_freeze.json#criteria` | `06fc0ee0272ef5a9fc3e71fbe67335fa1f5389a65231f311df77c0f54368406d` |
| `reviewed_commit` | `TensorData` PR #10 (`agent/m22061`) merge commit | `18559035a5d8eb108055619f36191523e1a9364d` |
| `verdict` | review receipt (mission m22510) | `pass` |

All four SHA-256 values above were recomputed in this worktree, not copied:

* `criteria_sha256` recomputed with `tensorbench.criteria.canonical_sha256` over
  `criteria_freeze.json#criteria` → identical.
* receipt and report bytes obtained with `git -C <TensorData> show <commit>:<path>` and hashed
  → identical (the receipt bytes also equal the m22510 work copy byte for byte).

## 3. Why the receipt authorises a pass (§3.4 preconditions, re-checked here)

| Precondition | Observed |
|---|---|
| `independence ∈ {independent_party}` | `reviewer.independence = independent_party`, reviewer `qwen3.6-plus` (≠ author mission m22061) |
| `verdict = pass` | `pass`, `overall_status = passed` |
| `rerun.exit_code = 0` | `independent_rerun.evidence.exit_code = 0`, 11/11 criteria reproduced |
| `checks_not_run` empty | `[]` |
| `blocking_conditions` empty | `[]` |
| six checks all pass | `artifact_identity`, `criteria_frozen_before_run`, `evidence_traceability`, `independent_rerun`, `failure_record`, `regression_scope` — all `pass` |

The author (m22061) did **not** self-sign: the pilot report keeps `overall_status=inconclusive`
and lists `review_receipt`, `scenario_validated`, `efd_baseline_error` as acceptance blockers.

## 4. Regression checks run in this worktree

| Check | Result |
|---|---|
| `python -m tensorbench validate --kind status` | `status: valid`, `error_count: 0`, exit 0 |
| `python -m tensorbench validate --kind status --input products/STATUS.json` | `valid`, exit 0 |
| `python -m tensorbench validate --kind report` (no `--input`) | exit 2 with `--input is required` — the new default is scoped to `--kind status` |
| `python -m pytest -q` | **191 passed, 0 failed** (182 pre-existing + 9 new publish guards) |
| `docs/audit_m22761/patch_status.py --check` | idempotent (status file already at the published state) |
| ledger row | `id=908, repo=TensorData, scope='m22061 PROD-PV 试点验收', mission_id=22061, level=2, gate_state=pending` |

## 5. Two small enabling fixes (needed for §3.⑤ to be executable at all)

1. **`python -m tensorbench` did not exist.** The package had no `__main__.py`, so the framework's
   own `validate --kind status` command could only be run as `python -m tensorbench.cli` via the
   console script. Added `tensorbench/__main__.py` (4 lines, delegates to `cli.main`).
2. **`--input` was mandatory**, so the documented `validate --kind status` form could not work.
   `--input` now defaults to `products/STATUS.json` **only for `--kind status`** (an unambiguous
   canonical file); every other kind still fails closed with exit 2 and an explicit message.

## 6. Adversarial findings — what this publish does *not* claim

Ranked by materiality; none of them blocks §3.⑤ as written, all are visible to the board.

1. **[material] The receipt is not inside PR #10.** The task brief places the receipt "inside
   TensorData#10". It is not: PR #10 (`1855903`) carries code + the pilot report, and the receipt
   was committed later on `agent/m22510` as `857a189` (PR #11 lineage). Refs are therefore pinned to
   `857a189`, not `1855903`, and `reviewed_commit` stays `1855903` because that is what was reviewed.
   A reader who looks for the receipt at `1855903` will not find it.
2. **[material, structural] `pilot_report.json` still says `overall_status=inconclusive`.** §3.4
   speaks of "a report whose `overall_status` is `passed`". The *receipt* has
   `overall_status=passed`; the *author report* is immutably `inconclusive` because it was emitted
   before the review existed and one blocker (`efd_baseline_error`) is an accepted limitation. Two
   of its three blockers (`review_receipt`, `scenario_validated`) are exactly what this publish
   closes. Under the strictest reading — the validation report itself must be regenerated with the
   receipt attached — this publish should be held. That regeneration is impossible without
   re-running the pilot (forbidden here) and would move the reviewed commit.
3. **[material] Maturity level 2, not 3+.** The receipt has **no `level` field**, so no level could
   be "taken from the receipt". Applying the platform rubric that the gate enforces
   (`why` messages: L1 `tests` / L2 `+impl_files,entry,run_artifacts` / L3 `+integration_callers` /
   L4 `+benchmark,repro_cmd,external_anchor`) gives **L2**: the only caller of
   `validate_physics_csv` is the in-repo pilot driver, the physics path is not registered as a
   quality profile (`profiles/__init__.py` registers GENERAL/TABULAR only) so
   `POST /api/v1/artifacts/{id}/quality-checks` cannot reach it, and no ship-platform repo imports
   it (grep of three checkouts, zero hits). L4 is additionally barred by the absence of any EFD /
   analytic anchor for this scenario. Upgrade to L3 is one `UPDATE` away if the board accepts a
   same-repo driver consuming real platform exports as an integration caller.
4. **[minor] Two different pytest counts.** The receipt's "96/96" is *TensorData*'s suite at
   `1855903`; this worktree's 191 is *TensorBench*'s. Neither proves the other; both are recorded
   with the repo they belong to.
5. **[minor] The ledger gate has not graded the row yet** (`gate_state=pending`, `gate_level` null
   at publication time). The row is honest and complete; grading is the gate's call, not this
   mission's.
6. **[minor] Scenario scope is narrow and fingerprinted.** CSV only (no NetCDF/HDF5/VTK), unit-less
   column names fall back to a canonical unit at medium confidence, and acceptance is bound to the
   input file fingerprints — any regeneration of the platform exports invalidates the run. None of
   this is model accuracy, and the pilot declares that.

## 7. Files

| Path | Role |
|---|---|
| `products/STATUS.json` | the published claim (PV block + PV line of the baseline reconciliation) |
| `docs/audit_m22761/patch_status.py` | the single-purpose, idempotent patcher that produced it (`--check` for drift) |
| `docs/audit_m22761/verdict_evidence.json` | ledger evidence bundle (level derivation, refs, limits) |
| `docs/audit_m22761/insert_verdict.py`, `verdict.sql` | action ② — the missed `tensor_maturity_verdicts` row (id 908) |
| `tests/test_pv_scenario_publish.py` | 9 guards: CLI validity, ref→bytes SHA-256, receipt pass-preconditions, `criteria_sha256` recomputation, idempotency |
| `tensorbench/__main__.py`, `tensorbench/cli.py` | `python -m tensorbench validate --kind status` now runs with no arguments |