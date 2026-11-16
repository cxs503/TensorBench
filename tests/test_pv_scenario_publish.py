"""Guards for the published PV ``scenario_validated=true`` claim (framework §3 step ⑤).

Mission m22761 publishes the Physics Dataset Validator line as scenario-validated.
`products/STATUS.json` is a claim file, so the claim must stay bound to the artifacts
that justify it. These tests do two things:

* re-validate the status contract through the real CLI entry point
  (``python -m tensorbench validate --kind status``);
* re-derive the binding from the artefact side when the TensorData checkout is
  available — receipt bytes against the recorded sha256, the six checks, the
  reviewer's independence/rerun, and ``criteria_sha256`` recomputed from the frozen
  criteria object. If the checkout is absent the binding tests skip instead of
  pretending to have verified anything.

Override the checkout with ``TENSORDATA_REPO=/path/to/TensorData``.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from tensorbench.criteria import canonical_sha256

ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = ROOT / "products" / "STATUS.json"
TENSORDATA = Path(os.environ.get("TENSORDATA_REPO", "/srv/tensor/workspace/TensorData"))

REF_PATTERN = re.compile(r"^(?P<repo>[^@]+)@(?P<commit>[0-9a-f]{40}):(?P<path>.+?)#sha256:(?P<sha>[0-9a-f]{64})$")
SIX_CHECKS = {
    "artifact_identity",
    "criteria_frozen_before_run",
    "evidence_traceability",
    "independent_rerun",
    "failure_record",
    "regression_scope",
}


def _status() -> dict:
    return json.loads(STATUS_PATH.read_text(encoding="utf-8"))


def _pv() -> dict:
    products = {p["id"]: p for p in _status()["products"]}
    return products["PV"]


def _parse_ref(ref: str) -> dict:
    match = REF_PATTERN.match(ref)
    assert match, f"evidence ref is not a pinned ref: {ref!r}"
    return match.groupdict()


def _git_show(commit_and_path: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(TENSORDATA), "show", commit_and_path],
        check=True,
        capture_output=True,
    ).stdout


requires_tensordata = pytest.mark.skipif(
    not (TENSORDATA / ".git").exists(),
    reason=f"TensorData checkout not available at {TENSORDATA}",
)


def test_published_status_is_valid_via_module_entry_point() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "tensorbench", "validate", "--kind", "status"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "valid"
    assert payload["errors"] == []


def test_other_kinds_still_require_explicit_input() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "tensorbench", "validate", "--kind", "report"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "--input is required" in result.stderr


def test_pv_claim_carries_complete_acceptance_evidence() -> None:
    pv = _pv()
    assert pv["code_implemented"] is True
    assert pv["scenario_validated"] is True
    evidence = pv["acceptance_evidence"]
    assert evidence["verdict"] == "pass"
    assert re.fullmatch(r"[0-9a-f]{64}", evidence["criteria_sha256"])
    assert re.fullmatch(r"[0-9a-f]{40}", evidence["reviewed_commit"])
    assert evidence["scenario_id"].startswith("pv-")
    _parse_ref(evidence["validation_report_ref"])
    _parse_ref(evidence["review_receipt_ref"])


def test_publisher_patch_is_idempotent() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "docs" / "audit_m22761" / "patch_status.py"), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@requires_tensordata
@pytest.mark.parametrize("field", ["validation_report_ref", "review_receipt_ref"])
def test_recorded_refs_resolve_to_the_recorded_bytes(field: str) -> None:
    ref = _parse_ref(_pv()["acceptance_evidence"][field])
    assert ref["repo"] == "TensorData"
    blob = _git_show(f"{ref['commit']}:{ref['path']}")
    assert hashlib.sha256(blob).hexdigest() == ref["sha"], f"{field} sha256 drift"


@requires_tensordata
def test_review_receipt_authorises_a_pass() -> None:
    ref = _parse_ref(_pv()["acceptance_evidence"]["review_receipt_ref"])
    receipt = json.loads(_git_show(f"{ref['commit']}:{ref['path']}"))

    assert receipt["verdict"] == "pass"
    assert receipt["overall_status"] == "passed"
    assert receipt["reviewer"]["independence"] == "independent_party"
    assert receipt["checks_not_run"] == []
    assert receipt["blocking_conditions"] == []
    assert receipt["mission_id"] == 22061

    checks = {check["check_id"]: check for check in receipt["six_checks"]}
    assert set(checks) == SIX_CHECKS
    assert all(check["verdict"] == "pass" for check in checks.values())
    assert checks["independent_rerun"]["evidence"]["exit_code"] == 0
    assert checks["regression_scope"]["evidence"]["pytest_failed"] == 0

    # the receipt must review the same commit the status file claims
    assert receipt["reviewed_commit"] == _pv()["acceptance_evidence"]["reviewed_commit"]


@requires_tensordata
def test_criteria_sha256_recomputes_from_the_frozen_criteria() -> None:
    receipt_ref = _parse_ref(_pv()["acceptance_evidence"]["review_receipt_ref"])
    freeze_path = receipt_ref["path"].replace("review_receipt.json", "criteria_freeze.json")
    freeze = json.loads(_git_show(f"{receipt_ref['commit']}:{freeze_path}"))
    assert canonical_sha256(freeze["criteria"]) == _pv()["acceptance_evidence"]["criteria_sha256"]


@requires_tensordata
def test_pilot_report_belongs_to_the_same_scenario_and_commit() -> None:
    evidence = _pv()["acceptance_evidence"]
    ref = _parse_ref(evidence["validation_report_ref"])
    report = json.loads(_git_show(f"{ref['commit']}:{ref['path']}"))
    assert report["scenario"]["scenario_id"] == evidence["scenario_id"]
    assert report["criteria_freeze"]["criteria_sha256"] == evidence["criteria_sha256"]