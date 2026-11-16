"""Guards for the published BE ``scenario_validated=true`` claim (framework §3 step ⑤).

Mission m22925 publishes the Business Evidence Engine line as scenario-validated on the
strength of the m22509 independent six-check receipt (amended by m22762) and the maturity
ledger row that records it. ``products/STATUS.json`` is a claim file, so each claim must stay
re-bindable to the bytes that justify it:

* the status contract is re-validated through the real CLI entry point;
* every pinned ref resolves on ``origin/main`` and its blob hashes to the declared sha256;
* ``criteria_sha256`` is recomputed from the frozen criteria file at the reviewed commit;
* the receipt still satisfies the pass preconditions (verdict / independence / ``checks_not_run``
  / ``blocking_conditions`` / six checks / rerun exit);
* the ``maturity_verdict_ref`` row still agrees with the status file (skipped when the platform
  database is unreachable — a skipped ledger check is *not* a passed one);
* the onboarding demo artifacts are intact.

Repository-level checks skip when the git history they need is absent, instead of pretending.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = ROOT / "products" / "STATUS.json"
CHECKER_PATH = ROOT / "docs" / "m22925" / "check_verdict_row.py"
DEMO_DIR = ROOT / "docs" / "m22925" / "demo"


def _load_checker():
    spec = importlib.util.spec_from_file_location("m22925_check_verdict_row", CHECKER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def checker():
    if not CHECKER_PATH.exists():  # pragma: no cover - the file ships with the mission
        pytest.skip("docs/m22925/check_verdict_row.py is absent")
    return _load_checker()


def _status() -> dict:
    return json.loads(STATUS_PATH.read_text(encoding="utf-8"))


def _be() -> dict:
    return {p["id"]: p for p in _status()["products"]}["BE"]


def _require_origin_main() -> None:
    proc = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--verify", "origin/main"],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        pytest.skip("origin/main is not available in this checkout")


def test_status_contract_validates_through_cli():
    proc = subprocess.run([sys.executable, "-m", "tensorbench", "validate", "--kind", "status"],
                          cwd=ROOT, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["status"] == "valid"
    assert payload["error_count"] == 0


def test_be_is_published_with_a_passing_verdict():
    be = _be()
    assert be["code_implemented"] is True
    assert be["scenario_validated"] is True
    evidence = be["acceptance_evidence"]
    assert evidence["verdict"] == "pass"
    assert evidence["scenario_id"] == "BE-20261115-tensorai-bp-field-extraction"
    assert evidence["reviewed_commit"] == "8c18865cb8b9f2fde39ff61d889d99d810c9942f"


def test_every_acceptance_ref_is_commit_pinned(checker):
    _require_origin_main()
    results = checker.check_refs(_be())
    assert [r["state"] for r in results] == ["passed", "passed"], results
    for result in results:
        assert result["commit_on_main"] is True
        assert result["recomputed_sha256"] == result["declared_sha256"]


def test_criteria_hash_is_recomputed_not_copied(checker):
    _require_origin_main()
    result = checker.check_criteria(_be())
    assert result["state"] == "passed", result
    assert result["recomputed"] == result["status_declared"] == result["freeze_declared"]


def test_receipt_still_meets_the_pass_preconditions(checker):
    _require_origin_main()
    result = checker.check_receipt(_be())
    assert result["state"] == "passed", result["problems"]
    assert result["rerun_exit_code"] == 0
    assert result["independence"] and not result["independence"].startswith("self")
    assert result["amendments"] >= 1  # the amended receipt is the one bound, not the first draft


def test_ledger_row_agrees_with_the_published_claim(checker):
    result = checker.check_ledger(_be())
    if result["state"] == "unknown":
        pytest.skip(f"platform database unreachable: {result['note']}")
    assert result["state"] == "passed", result["problems"]
    assert result["row"]["level"] == 3
    assert result["row"]["mission_id"] == 22060


def test_brief_row_number_909_does_not_exist(checker, monkeypatch):
    """The mission brief cited ledger row 909; the BE row is 911.

    Pinned as a test so the discrepancy cannot be quietly "fixed" by pointing the published
    claim at a row that does not carry this pilot's evidence.
    """
    be = json.loads(json.dumps(_be()))
    be["acceptance_evidence"]["maturity_verdict_ref"] = "tensorplatform:tensor_maturity_verdicts#id=909"
    result = checker.check_ledger(be)
    if result["state"] == "unknown":
        pytest.skip(f"platform database unreachable: {result['note']}")
    assert result["state"] == "failed"
    assert "does not exist" in result["note"]


def test_row_mismatch_is_detected_not_smoothed(checker):
    """A forged ledger reference must fail the check rather than pass by proximity."""
    be = json.loads(json.dumps(_be()))
    be["acceptance_evidence"]["maturity_verdict_ref"] = "tensorplatform:tensor_maturity_verdicts#id=908"
    result = checker.check_ledger(be)
    if result["state"] == "unknown":
        pytest.skip(f"platform database unreachable: {result['note']}")
    assert result["state"] == "failed"
    assert any("repo" in problem or "mission_id" in problem for problem in result["problems"])


def test_only_be_carries_a_ledger_reference():
    """Publishing BE must not have rewritten the other three lines."""
    products = {p["id"]: p for p in _status()["products"]}
    assert "maturity_verdict_ref" in products["BE"]["acceptance_evidence"]
    for other in ("AE", "RA", "PV"):
        assert "maturity_verdict_ref" not in products[other]["acceptance_evidence"]


def test_status_schema_still_rejects_unknown_evidence_keys():
    """The optional ledger pointer is additive; the closed object stays closed."""
    from tensorbench.contracts import validate_payload

    forged = json.loads(json.dumps(_status()))
    be = next(p for p in forged["products"] if p["id"] == "BE")
    be["acceptance_evidence"]["verdict_row_hint"] = "id=909"
    errors = validate_payload("status", forged)
    assert any("verdict_row_hint" in error or "additional" in error.lower() for error in errors)


def test_demo_artifacts_are_intact():
    timing_path = DEMO_DIR / "timing.json"
    if not timing_path.exists():
        pytest.skip("demo artifacts are absent")
    timing = json.loads(timing_path.read_text(encoding="utf-8"))
    import hashlib

    for name, declared in timing["artifacts"].items():
        path = DEMO_DIR / name
        assert path.exists(), f"{name} missing from the demo bundle"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == declared, f"{name} hash drift"
    assert timing["reconciliation"]["consistent_bundle"]["overall_status"] == "passed"
    assert timing["reconciliation"]["mismatch_bundle"]["overall_status"] == "failed"
    assert timing["input"]["synthetic"] is True


def test_version_is_published_from_one_place():
    import tensorbench

    assert tensorbench.__version__ == "0.2.0"
    proc = subprocess.run([sys.executable, "-m", "tensorbench", "--version"],
                          cwd=ROOT, capture_output=True, text=True)
    assert proc.returncode == 0
    assert "0.2.0" in proc.stdout