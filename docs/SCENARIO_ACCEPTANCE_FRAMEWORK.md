# Scenario acceptance framework (four product lines AE / RA / BE / PV)

**Status:** v1 · **Owner:** TensorBench · **Baseline:** `origin/main` = `adf6d025a1deb914bef7225911e1d89e26522a95` (merge #20) · **Scope:** AE · RA · BE · PV

This document closes the six-deliverable gap list for a common `scenario_validated` acceptance
framework. It is **not** a new framework, tool or repository: every element below is an
extension of an artifact that already exists in this repository. §1 is the audit (what exists,
with PR provenance), §2 lists exactly what was added and why it is GAP-level only, §3 is the
per-pilot procedure stage 3 must follow, §4–§7 are the receipt / record / value-evidence
conventions.

Vocabulary inherited unchanged from `docs/FOUR_PRODUCT_ACCEPTANCE_MATRIX.md` and
`products/STATUS.json` v2.0.0: `code_implemented` and `scenario_validated` are independent
fields; a unit-test suite never upgrades a line to `scenario_validated`; missing or unsupported
evidence is **inconclusive, never pass**.

---

## 1. Audit — six deliverables against the existing artifact set

Grade vocabulary: **REAL** (executable/validated artifact exists), **PARTIAL** (a real artifact
covers part of the deliverable), **GAP** (no artifact).

| # | Deliverable | Existing artifact (file) | Pr | Capability that actually exists | Grade | Gap |
|---|---|---|---|---|---|---|
| ① | Scenario specification (real scenario inputs + usage declaration) | `docs/BENCHMARK_SPEC.md` §1–§3, §6 (identity/workload/metrics/run protocol); `docs/FOUR_PRODUCT_ACCEPTANCE_MATRIX.md` §Mandatory acceptance record (bullet 1: immutable input fingerprints + source locators); `schemas/validation-report.schema.json` `input_refs`/`input_fingerprints` | #10, #15 | Benchmark-level workload declaration with input fingerprints; product-level reports carry input refs | **PARTIAL** | Benchmark spec is workload-shaped (one metric set, one spec file); there is no product-neutral `scenario` object and no "which real workflow does this run stand for" declaration, so a unit-test run is structurally indistinguishable from a real pilot |
| ② | Acceptance criteria pre-declared and frozen | `tensorbench/criteria.py` (predeclared-only evaluation, `canonical_sha256`, missing ⇒ `not_measured`, no post-hoc widening); `schemas/benchmark-result.schema.json` `acceptance.criteria[]` + `provenance.criteria_sha256`; `docs/PRODUCT_SHARED_CONTRACTS.md` §2 (versioned, declared before execution); frozen-criteria consumption path | #11, #17 | Machine-enforced predeclaration + criteria hash for benchmark runs | **PARTIAL** | The freeze is enforced for benchmarks; product scenario reports have no `criteria_freeze` block, so "criteria were declared before the run" is an assertion, not a machine-checkable fact |
| ③ | Evidence requirements (type / retention / fingerprint) | `schemas/evidence-item.schema.json` (`source_type`, `source_ref`, `sha256`, `locator`, `provenance`); `docs/PRODUCT_SHARED_CONTRACTS.md` §1, §6; `schemas/evidence_bundle.json` v1.0.0 (`missing[]`, `source_fingerprints`, `integrity.bundle_sha256`); `tensorbench/evidence_bundle.py`; `docs/EVIDENCE_BUNDLE.md` | #10, #11, #20 | Strict item contract, per-deliverable SHA-256, self-digest, explicit `missing` for absent evidence | **REAL** | None. §3 only cross-links it into the pilot checklist. |
| ④ | Independent review receipt (reviewer identity / re-execution requirement / PASS-FAIL / blocking conditions) | `schemas/validation-report.schema.json` `provenance.review_events` (unconstrained objects); `docs/INDEPENDENT_ISOLATED_TEST_RUNNER.md` (clean-environment re-execution, log artifacts, criterion attachment); `docs/FOUR_PRODUCT_ACCEPTANCE_MATRIX.md` (reviewer identity/role/decision/rationale bullet); m20192 six-check review paradigm (external record) | #11, #15, #17, #18 | Isolated re-run machinery + a place to park free-form review events | **PARTIAL** | No receipt contract: no required reviewer identity/role, no machine-checkable six checks, no PASS/FAIL semantics, no blocking-condition rule. An author could currently write "reviewed: ok" |
| ⑤ | Machine-readable acceptance status | `products/STATUS.json` v2.0.0 (`code_implemented` × `scenario_validated` for AE/RA/BE/PV, `release_rule`, baseline reconciliation); `docs/FOUR_PRODUCT_ACCEPTANCE_MATRIX.md` status vocabulary | #15, #20 | Truthful two-field status per line, consumed by humans and README | **PARTIAL** | No schema and no binding between a `true` field and the report/receipt that would justify it |
| ⑥ | Failure and regression records | `docs/AGENT_MISSION_EVIDENCE_COLLECTOR.md` (inconclusive rules, CI conclusions never upgraded); `schemas/evidence_bundle.json` `missing[]`; `tensorbench/contracts.py` (required check failed/unresolved ⇒ `passed` rejected); platform `negative_knowledge_ledger` (`GET /api/v1/tensor/negative-knowledge`, platform-of-record) | #11, #16, #20 | Non-upgrade rules exist; the platform ledger exists | **GAP** | No record *format*: nothing states which fields a failure/regression entry must carry, so pilots would invent one per product instead of feeding the platform ledger |

Supporting ground truth read for this audit: `agent-work-packages/FOUR_PRODUCT_FOUNDATION.md`
(#10, WP-A…WP-Q, exit criteria "no mock-only path represented as a completed feature",
"a failed/inconclusive required check cannot be converted to pass by an LLM summary"),
`docs/PRODUCT_SHARED_CONTRACTS.md` (#17, frozen-consumption), `docs/EVIDENCE_BUNDLE.md` +
`schemas/evidence_bundle.json` (m20135 / #20 AE-01 evidence bundle contract),
`docs/AGENT_MISSION_EVIDENCE_COLLECTOR.md` + `tensorbench/collect.py` (#16).

**Conclusion:** ③ is already REAL; ①②④⑤ are PARTIAL and fail exactly one test —
*machine-checkability*; ⑥ is a true GAP. No deliverable requires a new subsystem.
AE-01 (#20, `adf6d02`) passed independent review as **evidence-collection infrastructure**;
under this framework that does not make AE `scenario_validated=true` — see §8.

---

## 2. What was added (GAP-level only) — and what was deliberately not added

| Deliverable | Change | Kind | Why this is the minimum |
|---|---|---|---|
| ① | `schemas/validation-report.schema.json#/$defs/scenario` (optional `scenario` property): `scenario_id`, prose `usage_declaration`, `inputs[]` (`kind`, `ref`, `sha256`, optional `locator`/`permission_ref`), `permission_basis` (`public / licensed / internal_consent / synthetic_labelled / quarantined`), `environment`, `limits[]` | extend existing schema | Reuses the report contract already emitted by all four lines; no second report format |
| ② | `…/$defs/criteriaFreeze`: `criteria_ref`, `criteria_sha256`, `frozen_at`, `frozen_by`, `spec_ref`, `amendments[]`; rules *scenario ⇒ criteria_freeze*, *`frozen_at` ≤ `created_at`*, *any `amend_at` > `created_at` invalidates the claim* | extend existing schema + runtime rules | Reuses `criteria.py` hashing convention; the freeze becomes checkable instead of asserted |
| ④ | `…/$defs/reviewReceipt`: `reviewer{handle,role,affiliation,conflicts_declared}`, `independence`, `reviewed_commit`, `six_checks[6]` (closed enum), `rerun{command,exit_code,environment,log_ref,log_sha256,started_at}`, `checks_performed[]`, `checks_not_run[]`, `blocking_conditions[]`, `verdict{pass,fail,changes_requested,escalate}`, `signed_at`; rules *scenario ⇒ review_receipt*, *verdict=pass ⇒ independent + all six passed + exit_code 0 + no blockers + report passed*, *verdict≠pass ⇒ report not passed* | extend existing schema + runtime rules | Reuses `provenance.review_events` slot as the formal home; no review service, no queue, no new state machine |
| ⑤ | `schemas/acceptance-status.schema.json` — validates `products/STATUS.json` v2.0.0 verbatim; optional `acceptance_evidence{validation_report_ref, review_receipt_ref, criteria_sha256, reviewed_commit, verdict}` per product; rules *`scenario_validated=true` ⇒ both refs present and verdict∈{pass}*, *`code_implemented=false` ⇒ `scenario_validated=false`*, *all four lines declared*, *verdict=pass ⇒ `scenario_validated=true`* | new schema in the existing `schemas/` family, wired into the existing validator | The status file already exists and is the contract; it simply had no schema. Rejected alternative: a second status file |
| ⑥ | §5 of this document: field-level format mapped onto the platform `negative_knowledge_ledger` | documentation convention only (zero tooling) | The platform ledger is the system of record; duplicating it as a repo schema would create a second ledger |

Runtime wiring (already-existing validator, no new tool):

- `tensorbench/contracts.py`: `SCHEMA_FILES` gains `"status": "acceptance-status.schema.json"`;
  new `_report_acceptance_errors()` and `_status_errors()` semantic passes; constants
  `SIX_REVIEW_CHECKS` and `NON_INDEPENDENT`.
- `tensorbench/cli.py`: existing `validate --kind {evidence,report,asset}` gains `status`.
- `products/STATUS.json`: `acceptance_framework` pointer + per-product `acceptance_evidence`
  (all `null` today — no scenario run has happened, so `scenario_validated=false` stays true).
- Backwards compatibility: every new report field is optional. A report **without** `scenario`
  validates exactly as before (product-internal check reports are unaffected); supplying
  `scenario` is what turns a report into an acceptance claim and pulls in ② and ④.

Machine check (one command, existing CLI):

```bash
python -m tensorbench.cli validate --kind status --input products/STATUS.json
python -m tensorbench.cli validate --kind report --input <pilot-report>.json
```

**Explicitly not built:** no new repo, no new service, no review queue, no scoring engine, no
ledger copy, no status generator script, no CI gate beyond the existing test suite.

**Evidence for this document itself.** `docs/scenario_acceptance_audit/make_figure.py` executes
16 bypass attempts against the runtime validator (drop the receipt, drop the freeze, self-review,
author-signed gate, skipped six-check, non-zero rerun, undeclared unknowns, failing verdict,
quarantined/synthetic inputs, post-run freeze, post-run widening, unfingerprinted input, forged
`scenario_validated=true`, validated-without-code, pass-verdict-without-claim) plus one honest
control. Recorded result in `numbers.json`: **16/16 rejected, control accepted, `products/STATUS.json`
valid**; `acceptance_probe.png` plots the audit→closure grade transition next to the per-attempt
verdicts. `tests/test_scenario_acceptance.py` re-derives those counts from the live validator, so the
published numbers cannot drift from behaviour.

---

## 3. Per-pilot procedure (stage 3 fills this in; nothing here is automatic)

1. **Scenario specification (①).** Emit a report whose `scenario` block names the real workflow
   (`usage_declaration`), pins every input with a SHA-256 (`public` / `licensed` /
   `internal_consent` for real pilots; `synthetic_labelled` only for adversarial or regression
   runs, `quarantined` never supports a pass), and states `limits[]`.
   *A unit test, a fixture replay or a hand-written sample is not a scenario.*
2. **Freeze the criteria (②).** Copy the acceptance criteria from
   `docs/FOUR_PRODUCT_ACCEPTANCE_MATRIX.md` + the product PRD into a criteria file, hash it with
   `tensorbench.criteria.canonical_sha256`, and record `criteria_freeze`. Any later amendment
   must appear in `amendments[]` with timestamp and reason. A widened tolerance after the run is
   rejected by the validator (`amend_at` later than `created_at`), and a `frozen_at` later than the
   run's `created_at` is rejected outright — neither is a review judgement call.
3. **Collect evidence (③).** Real inputs + run outputs + logs, each as an
   `schemas/evidence-item.schema.json` item; absent items go into `missing[]` (evidence bundle
   contract) and force `inconclusive`, never `passed`.
4. **Independent review (④).** A reviewer who did not author the run re-executes it in a clean
   environment and files a `review_receipt`. The six checks and their blocking conditions:

| `six_checks.check_id` | Question the reviewer answers by re-execution | Blocking condition |
|---|---|---|
| `artifact_identity` | Do the reviewed commit SHA and every artifact/input fingerprint match the run being claimed? | Any mismatch, or a claim bound to a moveable ref instead of a SHA |
| `criteria_frozen_before_run` | Was `criteria_sha256` frozen before `created_at`, with no silent amendment? | Post-hoc criteria edit, or a hash that does not resolve |
| `evidence_traceability` | Does every finding resolve to a retrievable, digest-verified evidence item? | A finding whose evidence cannot be retrieved or re-hashed |
| `independent_rerun` | Did the reviewer themselves run the declared command and get the declared verdict? | Log read only, or re-run cannot reproduce the verdict |
| `failure_record` | Are failures, skips and unmeasured checks recorded as such (⑥ record filed)? | A failure/`not_measured` presented as pass, or a swallowed error |
| `regression_scope` | Do the previously passing checks in the affected scope still pass? | Regression in adjacent declared behavior, or scope not stated |

   `verdict=pass` additionally requires `independence ∈ {independent_party}`,
   `rerun.exit_code = 0`, empty `checks_not_run`/`blocking_conditions`, and a report whose
   `overall_status` is `passed`. The developer of the product may not sign its own release gate
   (`FOUR_PRODUCT_FOUNDATION.md`, WP-Q).
5. **Publish status (⑤).** Only after a passed receipt: set `scenario_validated=true` and fill
   `acceptance_evidence` (report ref, receipt ref, `criteria_sha256`, `reviewed_commit`,
   `verdict=pass`). `validate --kind status` must return `valid`.
6. **Record failures and regressions (⑥).** Every `fail` / `changes_requested` / `escalate`, and
   every honest-FAIL mission, files one record per §5 — including the pilots that fail. A pilot
   that produces no record is an unrecorded pilot, not a successful one.

Stage-3 pilot report skeleton (fill, do not invent):

```json
{
  "scenario": {"scenario_id": "<line>-<yyyymmdd>-<slug>", "usage_declaration": "<real workflow>",
               "permission_basis": "internal_consent", "inputs": [], "limits": []},
  "criteria_freeze": {"criteria_ref": "", "criteria_sha256": "", "frozen_at": "", "frozen_by": ""},
  "review_receipt": {"reviewer": {"handle": "", "role": "independent_qa"},
                     "independence": "independent_party", "reviewed_commit": "",
                     "six_checks": [], "rerun": {"command": "", "exit_code": 0, "environment": ""},
                     "blocking_conditions": [], "verdict": "pass", "signed_at": ""}
}
```

---

## 4. Acceptance semantics (one page, inherited not invented)

- `passed` requires every *applicable required* check to be `passed`; `failed` if any required
  check fails; `not_measured`/`inconclusive`/missing ⇒ `inconclusive` or `partial`, never
  `passed` (`docs/PRODUCT_SHARED_CONTRACTS.md` §4, enforced in `tensorbench/contracts.py`).
- `code_implemented=true` never implies `scenario_validated=true` (`products/STATUS.json`
  `release_rule`).
- A passing CI/PR snapshot proves recorded checks passed on one revision; it does not prove the
  feature is correct (`docs/AGENT_MISSION_EVIDENCE_COLLECTOR.md`).
- `synthetic_labelled` and `quarantined` scenario inputs can never carry a `passed` scenario.
- Model-assisted checks remain advisory unless calibrated on a labelled set
  (`docs/PRODUCT_SHARED_CONTRACTS.md` §2).

---

## 5. Failure and regression record format (⑥)

Platform `negative_knowledge_ledger` is the system of record. A repo-side record is a pointer +
the fields the ledger needs, so a pilot can be filed without inventing a second ledger. Mandatory
fields and the ledger mapping:

| Repo field | Platform ledger field | Rule |
|---|---|---|
| `keywords` | `keywords` | Product line + component + symptom, e.g. `["AE","evidence_bundle","missing-pr"]` |
| `anchor` | anchor / feature slug | The work-package or GAP id the attempt belonged to (`GAP-ACCEPT-①`…`⑥` as applicable) |
| `category` | category | `fail` (honest-FAIL run), `regression` (previously passing behavior broke), `defect` (product defect found in review), `gap` (missing capability) |
| `fail_stage` | `fail_stage` | Pipeline stage reached: `input` / `criteria` / `execution` / `evidence` / `review` / `status` |
| `failure_reason` | `failure_reason` | One sentence, mechanism-level ("OCR absent ⇒ scanned page yields no text item"), never "did not work" |
| `repro_cmd` | `repro_cmd` | Exact command + commit SHA; must be runnable by the reviewer |
| `evidence_refs` | `evidence_refs` | Report/receipt/log refs with SHA-256 |
| `affects` | — (repo only) | Deliverables/checks invalidated, so the same acceptance claim is not retried blind |
| `resolution` | — | `open` / `mitigated` / `accepted_limitation` / `superseded`, with the record that closed it |
| `cited_kb` | `cited_kb` | Ledger ids consulted before the attempt (pre-flight三查), so a retry shows it read the prior lesson |

Example (template; not a fabricated result — this repo has no filed pilot record yet):

```json
{
  "keywords": ["<line>", "<component>", "<symptom>"],
  "anchor": "GAP-ACCEPT-<n>",
  "category": "fail",
  "fail_stage": "evidence",
  "failure_reason": "<mechanism, one sentence>",
  "repro_cmd": "<command>  # <40-hex commit>",
  "evidence_refs": ["<path>#sha256:<64-hex>"],
  "affects": ["<check_id>"],
  "resolution": "open",
  "cited_kb": []
}
```

Rules: one record per failed attempt or discovered regression, filed at the time of the run by
the agent that ran it; `honest-FAIL` is a correct outcome and must be recorded, never retried
silently; a `regression` record must name the last commit where the behavior passed.

---

## 6. Six-dimension value evidence record (mandatory for every stage-3 real pilot)

Pure documentation convention, zero tooling. One block per pilot, appended to the pilot report's
`summary` object (the report schema already allows arbitrary `summary` keys) and summarised in
the mission report. Empty or unevidenced dimensions are written as `unknown` — never estimated.

| Dimension | Field | What must be recorded | How it is evidenced |
|---|---|---|---|
| 问题价值 (problem value) | `value.problem` | Which real, recurring decision the pilot changes (who decides what today, and what was wrong/expensive about it) | Named stakeholder workflow + the cost/risk it removes; not "AI for X" |
| 自动化程度 (automation) | `value.automation` | Which steps ran unattended vs. by hand, as a step count | Step list with `auto`/`manual` marks; `auto_steps/total_steps` |
| 质量对照 (quality vs. baseline) | `value.quality` | Per-key-quantity comparison against the frozen criteria and, where one exists, against a human or reference baseline; include the miss rate | The numbers table from the pilot report, error per item, `criteria_passed/criteria_total` |
| 成本 (cost) | `value.cost` | Wall-clock, human review minutes, and compute (cores×minutes) split per stage | Timestamps + reviewer log + `run_compute` usage receipt |
| 复现性 (reproducibility) | `value.reproducibility` | Whether an independent `rerun` reproduced the verdict, and the exact command + commit | `review_receipt.rerun` and `independent_rerun` check |
| 交付意愿 (delivery willingness) | `value.delivery` | Whether the consuming owner accepts the output as-is, with conditions and next increment | Owner statement/record reference; absence is `unknown`, not "planned" |

Admissibility: a pilot with any dimension `unknown` may still be accepted as `partial`, but it
cannot be promoted to a calibrated/operational claim (G3/G4 in
`docs/FOUR_PRODUCT_ACCEPTANCE_MATRIX.md`).

---

## 7. Known limits of this framework

- It makes claims *checkable*; it does not make them *true*. A dishonest reviewer can still sign
  a receipt — the record then carries the reviewer's identity, which is the accountability handle.
- The six checks are structural. Domain sufficiency (is this scenario representative?) stays with
  the product owner and WP-Q independent QA.
- `scenario_validated` remains `false` for all four lines: no pilot has been run. The added
  schema proves the status file *can* be checked, not that any line is validated.
- The `synthetic_labelled`/`quarantined` refusal rules are enforced by the runtime validator; they
  are not a substitute for permission review (`docs/PRODUCT_SHARED_CONTRACTS.md` §6).
- No retention/encryption mechanism is added: storage controls remain as in
  `docs/PRODUCT_SHARED_CONTRACTS.md` §6.

---

## 8. Current four-line state and the next gate

| Line | `code_implemented` | `scenario_validated` | Last independent review | Next gate |
|---|---:|---:|---|---|
| AE | true | false | AE-01 evidence infrastructure: #20 (`adf6d02`), six checks passed (external report) | One closed mission set collected read-only + reviewer receipt |
| BE | true | false | none on a real document bundle | Permissioned multi-document PDF → review → reconcile run |
| RA | false | false | none (engine lives in TensorKnowledge) | Land audit engine upstream, then one permissioned report+bibliography bundle |
| PV | false | false | none (engine lives in TensorData, half-true) | One explicit conservation profile on a real TensorLBM export |

Next acceptance gate for **this** work package: an independent reviewer applies §2–§3 to the diff
itself (identity of reviewed commit, non-breaking behaviour of the report schema, the status
rules catching a forged `scenario_validated=true`, and the failure-records convention actually
pointing at the platform ledger) and files a `review_receipt` — until then this framework is
`code_implemented` for the framework artifacts and `scenario_validated=false` for the framework
itself.