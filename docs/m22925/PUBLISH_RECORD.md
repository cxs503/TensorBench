# BE line publishes `scenario_validated=true` (mission m22925)

Framework: `docs/SCENARIO_ACCEPTANCE_FRAMEWORK.md` §3 step **⑤ Publish status**.
Product line: **BE — Business Evidence Engine** (`cxs503/TensorBench`).
Date: 2026-11-16. Only BE was touched; AE / RA / PV records are byte-identical.

## 1. Three published facts

| Fact | Value | Where it comes from |
|---|---|---|
| `scenario_validated` | `true` | independent review receipt verdict `pass` (§3.4 preconditions re-checked in §5 below) |
| `acceptance_evidence.scenario_id` | `BE-20261115-tensorai-bp-field-extraction` | `validation_report.json` → `scenario.scenario_id` |
| `code_implemented` | `true` | unchanged from the pre-mission baseline (code was already committed and tested) |

## 2. Evidence binding (commit-pinned, recomputed in this worktree)

| Field | Bound artefact | SHA-256 (recomputed with `git show <commit>:<path> \| sha256sum`) |
|---|---|---|
| `validation_report_ref` | `TensorBench@8c18865cb8b9f2fde39ff61d889d99d810c9942f:docs/pilots/BP-20261115-tensorai-bp-field-extraction/validation_report.json` | `f9b88fec299c09435355d5d0eaea5df6191312f524c79cf8d9df1e0138e49428` |
| `review_receipt_ref` | `TensorBench@ee5d8289af0e6431e6eef7ccd9825300e0be0f90:docs/pilots/BP-20261115-tensorai-bp-field-extraction/review_receipt_amended.json` | `51d7210f016fdb192a204cee377628e6e221fac3ef16b3cea3b7367e68c14cdd` |
| `criteria_sha256` | `criteria_v1.md` @ reviewed commit (raw byte hash; equals `criteria_freeze.json#criteria_sha256`) | `4bd2e5208cb92500d95efb1cc1a1d3eaa8a1183a61bb24417b35707c6f3dcc5d` |
| `reviewed_commit` | PR #22 merge (mission m22060 deliverables) | `8c18865cb8b9f2fde39ff61d889d99d810c9942f` |
| `verdict` | amended review receipt (missions m22509 → m22762) | `pass` |
| `maturity_verdict_ref` | ledger row | `tensorplatform:tensor_maturity_verdicts#id=911 (repo=TensorBench, mission_id=22060, level=3, gate_state=pending)` |

Why two commits: the review receipt was **amended** (mission m22762) after the pilot merge, so the
receipt's first appearance on `main` is merge `ee5d828` while the reviewed pilot work is `8c18865`.
Both refs resolve on `origin/main`; both blob hashes were recomputed here, not copied.

`maturity_verdict_ref` is a **new optional** field on `acceptanceEvidence`
(`schemas/acceptance-status.schema.json`): the closed object keeps rejecting unknown keys, and the
three other product lines simply do not carry it. It exists so the published claim points at the
ledger row instead of describing it in prose.

## 3. The ledger row: the brief said 909, the row is 911

The mission brief asked to bind "verdict 909 level3". **No row 909 exists.** Verified against the
platform database (`public.tensor_maturity_verdicts`, 756 rows, sequence at 915):

```
id=908  TensorData   mission 22061  level 2  pv-pilot-review（m22510 回执补录）
id=909  — absent —   (id gaps at 902 and 909; sequence advanced past them)
id=910  TensorLBM    mission 22754  level 2  xval-r2
id=911  TensorBench  mission 22060  level 3  be-pilot-review（m22762 amended 回执补录）  <- the BE pilot row
```

Row 911's own evidence names exactly this pilot: `receipt=docs/pilots/BP-.../review_receipt_amended.json`,
`verdict=pass`, `independent` independence, `checks_not_run=[]`, `rerun_exit=0`,
`reviewed_commit=8c18865…`. Publishing therefore binds **id=911**; fabricating or back-filling a
row 909 would have been new evidence rather than a citation of existing evidence. The discrepancy
is pinned as a test (`tests/test_be_scenario_publish.py::test_brief_row_number_909_does_not_exist`)
so it cannot be silently "fixed" by pointing the claim at the wrong row.

`gate_state=pending` is left untouched: gate promotion is a board decision, not an author's.

## 4. What was *not* re-done here

The pilot was not re-run. This mission re-executed the **guards**: status contract validation, ref
resolution against git blobs, criteria-hash recomputation, receipt-precondition re-evaluation and
ledger agreement. The pilot's own evidence and its independent review are cited, not regenerated —
the reviewed scenario is per-input-fingerprint, so re-running on a different copy would invalidate it.

## 5. §3.4 pass preconditions, re-checked from the receipt bytes

| Precondition | Observed | Checked by |
|---|---|---|
| independence declared, not a self review | `independence: independent`, reviewer `qwen3.6-plus` (mission 22509 ≠ author 22060) | `check_verdict_row.check_receipt` |
| `verdict = pass` | `pass` | same |
| six checks all pass | `artifact_identity`, `criteria_frozen_before_run`, `evidence_traceability`, `independent_rerun`, `failure_record`, `regression_scope` → all `passed` | same |
| `rerun.exit_code = 0` | `0` (13/13 criteria reproduced) | same |
| `checks_not_run` empty | `[]` (two amended items moved to `findings/limits` with reasons) | same |
| `blocking_conditions` empty | `[]` | same |

Honest counterweight: the pilot's `overall_status` is **`partial`**, and it stays `partial`. Its
declared limits (one document, one language, one layout; no OCR; no labelled ground truth) are
unchanged and are carried into `products/STATUS.json` `external_partial_state` and
`not_implemented_or_unverified`. Publication rests on the six-check receipt, not on an accuracy
claim that no ground truth can support.

## 6. Three-layer distinction (L1 / L2 / L3) — what is actually evidenced

| Layer | Meaning | BE state after this mission | Evidence |
|---|---|---|---|
| **L1 — unit-tested** | declared behaviour covered by automated tests | **evidenced** | pilot review `regression_scope`: 73 passed / 0 failed on 5 modules; this mission adds `tests/test_be_scenario_publish.py` (12 guards) and the demo integrity test |
| **L2 — implementation + entry + run artifacts** | real deterministic input→compute→output path, a documented entry, retained artifacts | **evidenced** | `tensorbench/pdf_evidence.py`, `business_pdf_fields.py`, `business_evidence.py`; CLI `extract-pdf`/`propose-pdf-fields`/`review-pdf-fields`/`reconcile-business`; pilot artifacts (`validation_report.json`, `numbers.json`, `quality_spotcheck.json`, `failure_records.json`); demo artifacts `docs/m22925/demo/` |
| **L3 — integrated caller** | an outside consumer calls the product surface | **ledger-asserted, not evidenced here** | ledger row 911 records `level=3`, but its `evidence` object carries no `integration_callers` list, so the derivation cannot be reproduced from the row. What *is* verifiable: the only in-repo caller is the pilot driver `scripts/run_bp_pilot.py`; no requirement/consumer record exists. Treat L3 as the board's grading, not as this mission's finding |

L4 (cross-validated) is not claimed: no labelled ground truth and no human baseline exist for this
document type, so no accuracy anchor can be stated (see `docs/m22925/value_evidence.json`).

## 7. Regression checks run in this worktree

| Check | Result |
|---|---|
| `python -m tensorbench validate --kind status` | `valid`, `error_count: 0` |
| `python3 docs/m22925/patch_status.py --check` | idempotent (already at the published state) |
| `python3 docs/m22925/check_verdict_row.py` | 5/5 bindings `passed` (refs, criteria hash, receipt preconditions, ledger row) |
| `python3 -m pytest tests/test_be_scenario_publish.py -q` | 12 passed |
| `python3 -m pytest -q` | full suite green |
| `python3 docs/m22925/run_demo.py` | 5 CLI stages, consistent bundle `passed`, mismatch bundle `failed` on `invoice.purchase_order_match` |
| `python -m tensorbench --version` | `tensorbench 0.2.0` |

Two pre-existing red tests surfaced while publishing; both were repaired, not silenced:

* `docs/pilots/BP-.../evidence_bundle.json` recorded a stale sha256 for `failure_records.json`
  (`bb7866ac…` vs actual `6a013bc9…`): mission m22762 amended the failure records without refreshing
  the bundle digest, so `test_evidence_bundle_digests_resolve_to_the_published_bytes` was already
  failing on `origin/main`. The digest was recomputed from the bytes; the other 9 artifacts were
  already consistent and no pilot content changed.
* `tests/test_scenario_acceptance.py` and `docs/scenario_acceptance_audit/make_figure.py` built their
  "pass verdict, claim off" bypass case on `products[1]` — the BE line. Once BE legitimately carries
  `verdict=pass`, that case stops being a forgery. Both now pick an unpublished line by id;
  `numbers.json` was regenerated by `make_figure.py` (probe exit 0), so the published probe numbers
  still match a fresh probe instead of being hand-edited.

Final full suite: **203 passed, 0 failed**; `check_verdict_row.py` 5/5 passed; the BE pilot's own
`overall_status` stays `partial`.

## 8. Commercial value evidence

Six dimensions per `docs/SCENARIO_ACCEPTANCE_FRAMEWORK.md` §6, recorded in
`docs/m22925/value_evidence.json`: problem, automation (9 auto / 1 manual step, ratio 0.90),
quality (13/13 frozen criteria, 9/10 fields, 22/22 locators, 22/22 spot-check, 0 % table
deviation), cost (pilot chain 6 s wall clock, 1 core ≈ 0.1 core-min; demo chain 1.281 s),
reproducibility (independent rerun exit 0, 13/13 reproduced), delivery (**unknown** — no
consuming-owner statement exists). Unknown dimensions stay unknown: miss rate, human baseline,
reviewer minutes and delivery willingness. Per §6 that keeps BE at a partial/level-3 claim and
blocks promotion to calibrated/operational.

## 9. Packaging increment (this mission)

* `CHANGELOG.md` added; version `0.1.0 → 0.2.0` in `pyproject.toml` and `tensorbench/__init__.py`.
* `tensorbench --version` added to the CLI (the version was previously only importable).
* `docs/m22925/DEMO.md` — onboarding quickstart that walks extract → propose → review → reconcile
  with the real commands and the real numbers from a committed run.
* `docs/business-evidence-pdf-ingestion.md` now points at the quickstart.
* `docs/m22925/demo/` — committed artifacts of a real run (synthetic 1-page invoice, 5 stages,
  consistent + mismatch bundles), timings, artifact sha256s.

## 10. Reproduce everything

```bash
python3 docs/m22925/patch_status.py --check          # status file is at the published state
python3 docs/m22925/check_verdict_row.py             # 5 bindings passed (needs the platform DB)
python3 -m tensorbench validate --kind status
python3 docs/m22925/run_demo.py                      # rewrites docs/m22925/demo/*
python3 -m pytest tests/test_be_scenario_publish.py -q
```