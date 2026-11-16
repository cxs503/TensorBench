#!/usr/bin/env python3
"""Publish the BE line as scenario-validated in ``products/STATUS.json`` (mission m22925).

Framework: ``docs/SCENARIO_ACCEPTANCE_FRAMEWORK.md`` §3 step ⑤ (Publish status).

Only the BE product record is rewritten. Every reference written here points at bytes that
already exist on ``origin/main``; nothing is fabricated. The script is idempotent and supports
``--check`` so a reviewer can prove the file is already at the published state.

    python3 docs/m22925/patch_status.py            # apply
    python3 docs/m22925/patch_status.py --check    # exit 0 iff already published

Evidence identity (recomputed in this worktree with ``git show <commit>:<path> | sha256sum``):

* ``validation_report.json``  @ 8c18865cb8b9f2fde39ff61d889d99d810c9942f
  -> f9b88fec299c09435355d5d0eaea5df6191312f524c79cf8d9df1e0138e49428
* ``review_receipt_amended.json`` @ ee5d8289af0e6431e6eef7ccd9825300e0be0f90
  -> 51d7210f016fdb192a204cee377628e6e221fac3ef16b3cea3b7367e68c14cdd
* ``criteria_v1.md`` (frozen criteria object) -> 4bd2e5208cb92500d95efb1cc1a1d3eaa8a1183a61bb24417b35707c6f3dcc5d
  (recomputed as a raw byte sha256; it equals ``criteria_freeze.json#criteria_sha256``)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATUS = ROOT / "products" / "STATUS.json"

PILOT = "docs/pilots/BP-20261115-tensorai-bp-field-extraction"
REVIEWED_COMMIT = "8c18865cb8b9f2fde39ff61d889d99d810c9942f"
RECEIPT_COMMIT = "ee5d8289af0e6431e6eef7ccd9825300e0be0f90"

BE_STATE = {
    "code_implemented": True,
    "scenario_validated": True,
    "acceptance_evidence": {
        "scenario_id": "BE-20261115-tensorai-bp-field-extraction",
        "validation_report_ref": (
            f"TensorBench@{REVIEWED_COMMIT}:{PILOT}/validation_report.json"
            "#sha256:f9b88fec299c09435355d5d0eaea5df6191312f524c79cf8d9df1e0138e49428"
        ),
        "review_receipt_ref": (
            f"TensorBench@{RECEIPT_COMMIT}:{PILOT}/review_receipt_amended.json"
            "#sha256:51d7210f016fdb192a204cee377628e6e221fac3ef16b3cea3b7367e68c14cdd"
        ),
        "criteria_sha256": "4bd2e5208cb92500d95efb1cc1a1d3eaa8a1183a61bb24417b35707c6f3dcc5d",
        "reviewed_commit": REVIEWED_COMMIT,
        "verdict": "pass",
        "maturity_verdict_ref": (
            "tensorplatform:tensor_maturity_verdicts#id=911"
            " (repo=TensorBench, mission_id=22060, level=3, gate_state=pending)"
        ),
    },
    "implemented_evidence": [
        "tensorbench/pdf_evidence.py bounded PDF ingestion with per-page text + page_text_sha256 + file fingerprint",
        "tensorbench/business_pdf_fields.py declared spectra (trade_documents_v1, business_plan_v1) -> rule-based page-addressable field proposals, reviewer decisions, evidence-record/document emitters",
        "tensorbench/business_evidence.py normalized-record reconciliation (Decimal tolerance, cross-document checks)",
        "CLI: extract-pdf / propose-pdf-fields / review-pdf-fields / reconcile-business",
        "docs/pilots/BP-20261115-tensorai-bp-field-extraction/ — stage-3 pilot on one real permissioned business plan (19 pages, 9/10 fields, 22/22 locators, 4/4 negative cases, 13/13 frozen criteria)",
        "Independent six-check review receipt: docs/pilots/BP-20261115-tensorai-bp-field-extraction/review_receipt_amended.json (verdict=pass, checks_not_run=[], blocking_conditions=[])",
        "docs/m22925/DEMO.md + docs/m22925/demo/ — end-to-end demo chain re-run with committed artifacts",
        "tests/test_pdf_evidence.py, tests/test_business_pdf_fields.py, tests/test_business_evidence.py, tests/test_bp_pilot_artifacts.py, tests/test_be_scenario_publish.py",
    ],
    "external_partial_state": (
        "BE is scenario-validated for one document: single-language, single-layout business-plan PDF, "
        "extraction is rule-based (no OCR, no table cell reconstruction), and the pilot's own overall_status "
        "is 'partial' because no labelled ground truth corpus exists. Publication rests on the independent "
        "six-check receipt (verdict=pass), not on a ground-truth accuracy claim."
    ),
    "not_implemented_or_unverified": [
        "OCR / scanned-document ingestion: not implemented",
        "Reliable table/line-item cell extraction beyond label-line + value-line shapes: not implemented",
        "Multi-document bundle orchestration in one command: the reconciler accepts a bundle, the extraction chain does not assemble one automatically",
        "Field/market accuracy against a labelled ground-truth corpus: no labelled corpus exists for this document type (pilot overall_status=partial)",
        "Customer-grade privacy/security verification: the pilot ran under internal_consent with a private bundle outside the repo; no security audit was performed",
        "Cross-language / cross-layout generalisation: unverified (one document, one language, one layout)",
    ],
    "next_gate": (
        "Run a second, permissioned document of a different layout (or a labelled holdout) and measure field "
        "precision/recall against ground truth; that is also the precondition for level 4 on the maturity ledger."
    ),
    "baseline_note": (
        "Deviation from the mission baseline: BE scenario_validated was false because no independent review "
        "existed. Review mission m22509 produced a six-check passing receipt (amended by m22762: two items resolved, "
        "checks_not_run=[]), and the pilot row (tensor_maturity_verdicts id=911, level=3) records it. This mission "
        "publishes the status only; it re-ran the guards, not the pilot. code_implemented=true is unchanged from "
        "the pre-mission baseline."
    ),
}


def published(product: dict) -> bool:
    return all(product.get(key) == value for key, value in BE_STATE.items())


def main(argv: list[str]) -> int:
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    products = status.get("products") or []
    target = next((p for p in products if p.get("id") == "BE"), None)
    if target is None:
        print("STATUS.json has no BE product record", file=sys.stderr)
        return 2
    if "--check" in argv[1:]:
        if published(target):
            print("BE record already at the published state")
            return 0
        print("BE record is NOT at the published state", file=sys.stderr)
        return 1
    target.update(BE_STATE)
    keys = ["id", "name", "repository", *BE_STATE.keys()]
    ordered = {key: target[key] for key in keys if key in target}
    for key, value in target.items():
        if key not in ordered:
            ordered[key] = value
    products[products.index(target)] = ordered
    status["products"] = products
    STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("patched products/STATUS.json: BE scenario_validated=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))