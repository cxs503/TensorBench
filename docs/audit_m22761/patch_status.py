#!/usr/bin/env python3
"""Publish PV `scenario_validated=true` in products/STATUS.json (framework §3 step ⑤).

Single-purpose, idempotent patcher for mission m22761.  It touches only the PV
product entry and the PV line of `mission_baseline_reconciliation`; the AE / RA /
BE entries are re-serialised byte-identically (the file round-trips through
json.dumps(indent=2, ensure_ascii=False) unchanged, verified by the diff test in
tests/test_pv_status_publish.py).

Every value written here is bound to an existing artifact:

  validation_report_ref  TensorData@857a189:artifacts/pv-pilot/ex1_kcs/pilot_report.json
  review_receipt_ref     TensorData@857a189:artifacts/pv-pilot/ex1_kcs/review_receipt.json
  criteria_sha256        recomputed from criteria_freeze.json#criteria (canonical_sha256)
  reviewed_commit        18559035a5d8eb108055619f36191523e1a9364d  (TensorData#10)
  verdict                pass   (review receipt, six checks all pass, checks_not_run=[])

Run: python3 docs/audit_m22761/patch_status.py [--check]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATUS = ROOT / "products" / "STATUS.json"

REVIEWED_COMMIT = "18559035a5d8eb108055619f36191523e1a9364d"
ARTIFACT_COMMIT = "857a189ee66cfda0fc208556b1316e25ff2e2104"
CRITERIA_SHA256 = "06fc0ee0272ef5a9fc3e71fbe67335fa1f5389a65231f311df77c0f54368406d"
SCENARIO_ID = "pv-kcs-ex1-20261115-prereg-column-acceptance"
AS_OF = "2026-11-16"

IMPLEMENTED_EVIDENCE = [
    f"TensorData@{REVIEWED_COMMIT[:7]}:tensordata/quality/physics_csv.py"
    " — profile-driven physics CSV adapter (structure / axis / unit / physical-range rules)",
    f"TensorData@{REVIEWED_COMMIT[:7]}:tensordata/quality/units.py"
    " — unit registry with exact SI conversion factors and unit-suffix resolution",
    f"TensorData@{REVIEWED_COMMIT[:7]}:tensordata/quality/fields.py"
    " — numeric-column identification (symbol table, unit-less canonical-unit fallback)",
    f"TensorData@{REVIEWED_COMMIT[:7]}:tensordata/quality/{{engine,rules,profiles}}"
    " — quality engine plus registered tabular profile, reachable through"
    " POST /api/v1/artifacts/{artifact_id}/quality-checks",
    f"TensorData@{ARTIFACT_COMMIT[:7]}:scripts/pv_pilot_ex1_kcs.py"
    " — stage-3 pilot driver (criteria freeze, four negative injections, report)",
    f"TensorData@{REVIEWED_COMMIT[:7]}:tests/test_physics_csv_validator.py,"
    " tests/test_physics_field_inference.py, tests/test_physics_unit_conversion.py,"
    " tests/test_quality_engine.py — 96/96 pytest on the reviewed commit (review receipt,"
    " regression_scope)",
]

ACCEPTANCE_EVIDENCE = {
    "scenario_id": SCENARIO_ID,
    "validation_report_ref": (
        f"TensorData@{ARTIFACT_COMMIT}:artifacts/pv-pilot/ex1_kcs/pilot_report.json"
        "#sha256:7cbf516a9d563a983b705fea40d30cdf68a3ca25260b839ec203769d6a8f100a"
    ),
    "review_receipt_ref": (
        f"TensorData@{ARTIFACT_COMMIT}:artifacts/pv-pilot/ex1_kcs/review_receipt.json"
        "#sha256:db77659dc634f016226be6c6b4d720b6d46170eb70db4ad044c1aeca20fe491e"
    ),
    "criteria_sha256": CRITERIA_SHA256,
    "reviewed_commit": REVIEWED_COMMIT,
    "verdict": "pass",
}

NOT_IMPLEMENTED = [
    "NetCDF/HDF5/VTK field formats: not implemented — the adapter is CSV-only"
    " (declared scenario limit, pilot_report.json scenario.limits[0])",
    "Initial/boundary-condition compliance rules: not implemented",
    "Conservation-law residuals as a general profile: only the EX1 envelope closure"
    " (density / power / speed cross-column) is checked",
    "TensorLBM ship-flow end-to-end validation: no such scenario has been run",
    "Model accuracy vs towing tank (EFD): out of scope for this data-quality scenario,"
    " recorded as accepted_limitation in artifacts/pv-pilot/ex1_kcs/failure_records.json",
]

NEXT_GATE = (
    "Run a second, independent PV scenario on a TensorLBM flow export (NetCDF/VTK) with an"
    " EFD or analytic cross-check, which is also the precondition for claiming level 4"
    " (cross-validated) on the maturity ledger."
)

BASELINE_NOTE = (
    "Deviation from the mission baseline: the premise 'TensorData quality engine half-true'"
    " no longer holds for PV. The PV chain is implemented at TensorData@"
    f"{REVIEWED_COMMIT[:7]} and one permissioned real scenario (EX1/KCS prereg column"
    " acceptance) passed the frozen criteria set on 29/29 numeric columns with all four"
    " negative injections detected, under an independent review receipt (verdict=pass,"
    " six checks pass, checks_not_run=[]). code_implemented and scenario_validated are"
    " therefore both true for PV only; AE/RA/BE are unchanged."
)

RECONCILE_ADDENDUM = (
    " PV was reconciled to false/false on the same premise; mission m22761 publishes"
    f" code_implemented=true and scenario_validated=true for PV against the reviewed commit"
    f" {REVIEWED_COMMIT}, so reconciled.PV_code_implemented is corrected to true here."
)


def patched(payload: dict) -> dict:
    for product in payload["products"]:
        if product.get("id") != "PV":
            continue
        product["code_implemented"] = True
        product["scenario_validated"] = True
        product["acceptance_evidence"] = dict(ACCEPTANCE_EVIDENCE)
        product["implemented_evidence"] = list(IMPLEMENTED_EVIDENCE)
        product["not_implemented_or_unverified"] = list(NOT_IMPLEMENTED)
        product["external_partial_state"] = (
            "TensorData PV chain is implemented and scenario-validated for CSV column"
            " acceptance (physics CSV adapter + unit registry + field identification)."
            " Field-format (NetCDF/HDF5/VTK) and towing-tank accuracy remain unverified."
        )
        product["next_gate"] = NEXT_GATE
        product["baseline_note"] = BASELINE_NOTE
    payload["as_of"] = AS_OF
    recon = payload.get("mission_baseline_reconciliation") or {}
    (recon.get("reconciled") or {})["PV_code_implemented"] = True
    reason = recon.get("reason")
    if isinstance(reason, str) and "m22761" not in reason:
        recon["reason"] = reason.rstrip() + RECONCILE_ADDENDUM
    return payload


def main(argv: list[str]) -> int:
    raw = STATUS.read_text(encoding="utf-8")
    before = json.loads(raw)
    after = patched(json.loads(raw))
    rendered = json.dumps(after, indent=2, ensure_ascii=False) + "\n"
    assert json.dumps(before, indent=2, ensure_ascii=False) + "\n" == raw, (
        "STATUS.json does not round-trip; refusing to reformat the whole file"
    )
    others_before = {
        p["id"]: p for p in before["products"] if p["id"] != "PV"
    }
    others_after = {p["id"]: p for p in after["products"] if p["id"] != "PV"}
    assert others_before == others_after, "the patcher must not touch AE/RA/BE"
    if "--check" in argv:
        print("STATUS.json matches the published state:", rendered == raw)
        return 0 if rendered == raw else 1
    STATUS.write_text(rendered, encoding="utf-8")
    print(f"wrote {STATUS} ({len(rendered)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))