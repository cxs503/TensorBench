# Adversarial Review — m22060 PROD-BE Pilot (BP-20261115-tensorai-bp-field-extraction)

**Reviewer:** qwen3.6-plus (independent, agent mission 22509)
**Reviewed commit:** 8c18865cb8b9f2fde39ff61d889d99d810c9942f (Merge #22)
**Author commit:** 5f8655543dc08faf62e4237543d36c2c9fba0b73 (m22060 deliverables)
**Pre-merge worktree:** 0feace24d7b12a5f54189d2e47c2e2620d580b75
**Verdict:** **pass** (all six checks passed; no blocking conditions)

---

## 1. Artifact Identity (①) — PASSED

| Check | Result | Evidence |
|---|---|---|
| PDF sha256 recomputed | `91f9d4a4bbf9689414a152ff7d10c7066054d799c5bc6a3c3b230d9894c472dd` ✓ | `sha256sum /root/tp-agent/work/pilot_inputs_1115/TensorAI_BP.pdf` |
| PDF never in git | Confirmed: full blob search across all commits found zero matches | `git log --all --objects` + blob scan |
| Merge commit contains deliverables | 21 files added in 5f86555, merged at 8c18865 | `git show 8c18865 --stat` |
| 10 published artifact hashes | All match actual file bytes | Independent sha256sum verification |
| 9 private artifact hashes | All match actual file bytes | Independent sha256sum verification |

**No defects found.** The PDF is correctly kept outside the repository; only its fingerprint is published.

---

## 2. Criteria Frozen Before Run (②) — PASSED

| Check | Result |
|---|---|
| criteria_sha256 recomputed | `4bd2e5208cb92500d95efb1cc1a1d3eaa8a1183a61bb24417b35707c6f3dcc5d` ✓ |
| frozen_at ≤ created_at | `2026-11-15T15:34:01Z` ≤ `2026-11-15T15:38:48Z` ✓ |
| No amendments | `amendments: []` ✓ |
| Runner enforces freeze | Code verified: refuses if hash differs or frozen_at > run_started_at |

**No defects found.** The freeze mechanism is machine-enforced, not merely asserted.

---

## 3. Evidence Traceability (③) — PASSED

Independently verified 10 fields against the actual PDF using pypdf:

| Field | Page | Offset | Actual Text | Match |
|---|---|---|---|---|
| document_version | 1 | [109:113] | "V1.0" | ✓ |
| document_issue_date | 1 | [116:124] | "2026年11月" | ✓ |
| document_title | 1 | [57:71] | "Tensor 系列商业计划书" | ✓ |
| ratio_block#早期 | 10 | [514:528] | "30%\n55%\n15%\n0%" | ✓ |
| roadmap_window#基础 | 12 | [64:68] | "0–12" | ✓ |
| table_label_percent#早期 | 10 | [514:516] | "30" | ✓ |
| financing_stage | 13 | [57:69] | "种子轮或 Pre-A 轮" | ✓ |
| legal_disclaimer | 19 | [904:915] | "本文件为商业计划讨论稿" | ✓ |

All 22 structured record fields carry page_number, start_offset, end_offset, page_text_sha256, and value_sha256. The quality_spotcheck independently confirms 22/22 agree over 9 fields via a second code path (no shared regexes).

**No defects found.**

---

## 4. Independent Rerun (④) — PASSED

### Full pilot chain rerun
- **Command:** `python scripts/run_bp_pilot.py run --pdf <private>/TensorAI_BP.pdf`
- **Result:** 13/13 checks passed, identical to original run
- **Field spectrum:** 9/10 fields with ≥1 proposal (threshold ≥8) ✓
- **funding_amount:** 0 proposals (correctly absent) ✓
- **overall_status:** partial ✓
- **receipt_verdict:** changes_requested ✓

### Independent spotcheck (second code path)
- **Command:** `python scripts/bp_pilot_verify.py --pdf <private>/TensorAI_BP.pdf`
- **Result:** 22/22 checks agree over 9 fields ✓

### Table arithmetic invariants
| Invariant | Expected | Measured | Deviation |
|---|---|---|---|
| funding-use sum | 100% | 100% | 0% ✓ |
| revenue row 1 sum | 100% | 100% | 0% ✓ |
| revenue row 2 sum | 100% | 100% | 0% ✓ |
| revenue row 3 sum | 100% | 100% | 0% ✓ |
| roadmap span | [0, 36] | [0, 36] | 0% ✓ |
| roadmap contiguity | contiguous | contiguous | 0% ✓ |

**No defects found.** All claims are reproduced exactly.

---

## 5. Failure Record (⑤) — PASSED

### Negative path (4/4 cases)
| Case | Exit Code | Artifact Written | Declared Error | Result |
|---|---|---|---|---|
| truncated_body | 2 | No | PdfEvidenceError | ✓ |
| non_pdf_bytes | 2 | No | PdfEvidenceError | ✓ |
| zero_byte | 2 | No | PdfEvidenceError | ✓ |
| header_only | 2 | No | PdfEvidenceError | ✓ |

### Failure records
4 records filed in §5 format with all required fields (keywords, anchor, category, fail_stage, failure_reason, repro_cmd, evidence_refs, affects, resolution, cited_kb).

### Overall status honesty
- `overall_status: partial` — correctly NOT inflated to "passed"
- Honest declaration: "no independent party re-executed the run" and "no labelled ground truth exists"
- The author's self-review correctly declares `verdict: changes_requested` with blocking conditions

**No defects found.** The honest-FAIL discipline is correctly applied.

---

## 6. Regression Scope (⑥) — PASSED

| Module | Tests | Passed | Failed | Errors |
|---|---|---|---|---|
| test_bp_pilot_artifacts.py | 16 | 16 | 0 | 0 |
| test_business_pdf_fields.py | (part of 73) | — | 0 | 0 |
| test_business_evidence.py | (part of 73) | — | 0 | 0 |
| test_product_contract_schemas.py | (part of 73) | — | 0 | 0 |
| test_scenario_acceptance.py | (part of 73) | — | 0 | 0 |
| test_pdf_evidence.py | (part of 73) | — | 0 | 0 |
| **Total** | **89** | **89** | **0** | **0** |

**No defects found.** Zero regressions.

---

## Findings (Non-Blocking)

| # | Severity | Finding | Impact |
|---|---|---|---|
| 1 | info | validation_report.json references pre-merge commit 0feace24, not merge commit 8c18865 | Expected — run was on worktree before merge |
| 2 | info | table_label_percent captures only first column in multi-column tables | Known limitation, documented, filed as defect |
| 3 | info | market_reference requires parenthesised year; 2/5 references dropped | Known limitation, documented, filed as defect |
| 4 | info | Platform negative-knowledge ledger API returned 405 (read-only) | Platform limitation, not deliverable defect |

---

## Disposition

**APPROVE** — All six checks passed independently. No blocking correctness or security issues found. The deliverable honestly declares its limitations (partial status, no independent review at time of authoring, no labelled ground truth) and does not overstate its claims.

### Remediation (none required for pass)
- The platform negative-knowledge ledger submission remains open (API 405). This is a platform-side issue, not a deliverable defect.
- The `table_label_percent` and `market_reference` limitations are correctly filed as `accepted_limitation` defect records.

---

## Independence Limitations

- This review was performed on the same machine where the original run was executed (same Python/pypdf versions). A truly isolated environment (different machine, different OS) was not available.
- The PDF content was accessible for verification (private but available at `/root/tp-agent/work/pilot_inputs_1115/`). The review did not attempt to extract additional fields beyond what the declared spectra cover.
- No human ground-truth labelling was available; accuracy claims are limited to self-consistency and re-derivability, not semantic correctness.
