"""Scenario acceptance framework contracts (AE/RA/BE/PV).

These tests assert invariants, not just execution: a pass may never be claimed
without a frozen criteria set and an independent review receipt that actually
re-ran the work, and ``scenario_validated=true`` in products/STATUS.json may
never appear without the report and receipt that justify it.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from tensorbench import cli
from tensorbench.contracts import SCHEMA_FILES, SIX_REVIEW_CHECKS, validate_payload

ROOT = Path(__file__).resolve().parents[1]
STATUS_FILE = ROOT / "products" / "STATUS.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def status() -> dict:
    return _load(STATUS_FILE)


def _report(**overrides) -> dict:
    report = {
        "schema_version": "0.1.0",
        "product_id": "agent-achievement-evaluator",
        "product_version": "0.1.0",
        "run_id": "run-scenario-001",
        "created_at": "2026-11-14T00:00:00Z",
        "input_refs": ["mission://20374"],
        "checks": [
            {
                "check_id": "mission-collected-read-only",
                "version": "0.1.0",
                "method": "deterministic_rule",
                "state": "passed",
                "required": True,
            }
        ],
        "findings": [],
        "overall_status": "passed",
        "provenance": {"input_fingerprints": {"mission": "sha256:" + "a" * 64}},
    }
    report.update(overrides)
    return report


def _scenario(**overrides) -> dict:
    scenario = {
        "scenario_id": "AE-20261114-closed-mission-set",
        "usage_declaration": "Accept one closed mission set as a real achievement-evaluation pilot.",
        "permission_basis": "internal_consent",
        "inputs": [
            {
                "input_id": "missions",
                "kind": "mission",
                "ref": "mission://20374",
                "sha256": "a" * 64,
            }
        ],
        "limits": ["one repository, six missions"],
    }
    scenario.update(overrides)
    return scenario


def _freeze(**overrides) -> dict:
    freeze = {
        "criteria_ref": "products/agent-achievement-evaluator/PRD.md#acceptance",
        "criteria_sha256": "b" * 64,
        "frozen_at": "2026-11-14T00:00:00Z",
        "frozen_by": "owner",
    }
    freeze.update(overrides)
    return freeze


def _receipt(**overrides) -> dict:
    receipt = {
        "reviewer": {"handle": "m20999", "role": "independent_qa"},
        "independence": "independent_party",
        "reviewed_commit": "c" * 40,
        "six_checks": [
            {"check_id": check_id, "state": "passed", "evidence_ref": f"evidence://{check_id}"}
            for check_id in SIX_REVIEW_CHECKS
        ],
        "rerun": {"command": "pytest -q", "exit_code": 0, "environment": "clean venv"},
        "checks_performed": ["pytest -q"],
        "checks_not_run": [],
        "blocking_conditions": [],
        "verdict": "pass",
        "signed_at": "2026-11-15T00:00:00Z",
    }
    receipt.update(overrides)
    return receipt


def _claim() -> dict:
    return _report(scenario=_scenario(), criteria_freeze=_freeze(), review_receipt=_receipt())


# --------------------------------------------------------------------------
# ⑤ machine-readable acceptance status
# --------------------------------------------------------------------------


def test_every_declared_schema_is_a_valid_json_schema() -> None:
    for filename in SCHEMA_FILES.values():
        Draft202012Validator.check_schema(_load(ROOT / "schemas" / filename))


def test_acceptance_status_contract_includes_the_status_file() -> None:
    assert SCHEMA_FILES["status"] == "acceptance-status.schema.json"


def test_products_status_is_valid(status: dict) -> None:
    assert validate_payload("status", status) == []


def test_status_cli_accepts_products_status(capsys, monkeypatch) -> None:
    monkeypatch.setattr(
        sys, "argv", ["tensorbench", "validate", "--kind", "status", "--input", str(STATUS_FILE)]
    )
    exit_code = cli.main()
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "valid"


def test_status_rejects_scenario_validated_without_evidence(status: dict) -> None:
    forged = copy.deepcopy(status)
    forged["products"][0]["scenario_validated"] = True
    errors = validate_payload("status", forged)
    assert any("acceptance_evidence.validation_report_ref" in e for e in errors)
    assert any("acceptance_evidence.review_receipt_ref" in e for e in errors)


def test_status_rejects_scenario_validated_on_missing_code(status: dict) -> None:
    forged = copy.deepcopy(status)
    product = next(p for p in forged["products"] if p["id"] == "RA")
    product["scenario_validated"] = True
    product["acceptance_evidence"] = {
        "validation_report_ref": "reports/ra-pilot.json",
        "review_receipt_ref": "reports/ra-receipt.json",
        "verdict": "pass",
    }
    errors = validate_payload("status", forged)
    assert any("requires code_implemented=true" in e for e in errors)


def test_status_rejects_passing_verdict_without_scenario_claim(status: dict) -> None:
    forged = copy.deepcopy(status)
    forged["products"][1]["acceptance_evidence"]["verdict"] = "pass"
    errors = validate_payload("status", forged)
    assert any("must set scenario_validated=true" in e for e in errors)


def test_status_rejects_non_passing_verdict_as_validated(status: dict) -> None:
    forged = copy.deepcopy(status)
    product = forged["products"][0]
    product["scenario_validated"] = True
    product["acceptance_evidence"] = {
        "validation_report_ref": "reports/ae-pilot.json",
        "review_receipt_ref": "reports/ae-receipt.json",
        "verdict": "changes_requested",
    }
    errors = validate_payload("status", forged)
    assert any("verdict=pass" in e for e in errors)


def test_status_requires_all_four_product_lines(status: dict) -> None:
    forged = copy.deepcopy(status)
    forged["products"] = [p for p in forged["products"] if p["id"] != "PV"]
    errors = validate_payload("status", forged)
    assert any("product line PV" in e for e in errors)


def test_status_rejects_unknown_product_field(status: dict) -> None:
    forged = copy.deepcopy(status)
    forged["products"][0]["scenario_validated_claim"] = True
    errors = validate_payload("status", forged)
    assert any("scenario_validated_claim" in e for e in errors)


# --------------------------------------------------------------------------
# ①②④ scenario claim ⇒ freeze + independent receipt
# --------------------------------------------------------------------------


def test_unit_level_report_stays_valid_without_scenario_blocks() -> None:
    """Backwards compatibility: product-internal check reports need no receipt."""
    assert validate_payload("report", _report()) == []


def test_scenario_claim_requires_frozen_criteria_and_receipt() -> None:
    errors = validate_payload("report", _report(scenario=_scenario()))
    assert any("criteria_freeze" in e for e in errors)
    assert any("review_receipt" in e for e in errors)


def test_complete_scenario_claim_is_accepted() -> None:
    assert validate_payload("report", _claim()) == []


def test_quarantined_inputs_cannot_pass() -> None:
    report = _claim()
    report["scenario"] = _scenario(permission_basis="quarantined")
    assert any("quarantined" in e for e in validate_payload("report", report))


def test_synthetic_inputs_cannot_pass_as_scenario_validation() -> None:
    report = _claim()
    report["scenario"] = _scenario(permission_basis="synthetic_labelled")
    assert any("synthetic_labelled" in e for e in validate_payload("report", report))


def test_self_review_cannot_pass() -> None:
    report = _claim()
    report["review_receipt"] = _receipt(independence="self_review")
    assert any("self_review" in e for e in validate_payload("report", report))


@pytest.mark.parametrize("check_id", SIX_REVIEW_CHECKS)
def test_each_six_check_must_pass_for_a_pass(check_id: str) -> None:
    receipt = _receipt()
    for check in receipt["six_checks"]:
        if check["check_id"] == check_id:
            check["state"] = "not_run"
    report = _claim()
    report["review_receipt"] = receipt
    assert any(check_id in e for e in validate_payload("report", report))


def test_receipt_must_carry_all_six_checks() -> None:
    receipt = _receipt()
    receipt["six_checks"] = receipt["six_checks"][:5]
    report = _claim()
    report["review_receipt"] = receipt
    errors = validate_payload("report", report)
    assert any("missing six_checks" in e for e in errors)


def test_receipt_rejects_unknown_check_id() -> None:
    receipt = _receipt()
    receipt["six_checks"][0]["check_id"] = "vibes"
    report = _claim()
    report["review_receipt"] = receipt
    errors = validate_payload("report", report)
    assert any("vibes" in e for e in errors)


def test_reviewer_rerun_must_exit_zero() -> None:
    report = _claim()
    report["review_receipt"] = _receipt(
        rerun={"command": "pytest -q", "exit_code": 1, "environment": "clean venv"}
    )
    assert any("rerun exit_code" in e for e in validate_payload("report", report))


def test_blocking_conditions_forbid_a_pass() -> None:
    report = _claim()
    report["review_receipt"] = _receipt(blocking_conditions=["evidence for check 3 missing"])
    assert any("blocking_conditions" in e for e in validate_payload("report", report))


def test_checks_not_run_forbid_a_pass() -> None:
    report = _claim()
    report["review_receipt"] = _receipt(checks_not_run=["regression suite"])
    assert any("checks_not_run" in e for e in validate_payload("report", report))


def test_failing_receipt_verdict_forbids_passed_report() -> None:
    report = _claim()
    report["review_receipt"] = _receipt(verdict="changes_requested")
    assert any("changes_requested" in e for e in validate_payload("report", report))


def test_receipt_pass_requires_passed_report() -> None:
    report = _claim()
    report["overall_status"] = "inconclusive"
    assert any("overall_status=passed" in e for e in validate_payload("report", report))


def test_receipt_requires_identity_and_commit() -> None:
    receipt = _receipt()
    del receipt["reviewer"]
    del receipt["reviewed_commit"]
    report = _claim()
    report["review_receipt"] = receipt
    errors = validate_payload("report", report)
    assert any("reviewer" in e for e in errors)
    assert any("reviewed_commit" in e for e in errors)


def test_scenario_inputs_must_be_fingerprinted() -> None:
    scenario = _scenario()
    del scenario["inputs"][0]["sha256"]
    report = _claim()
    report["scenario"] = scenario
    assert any("sha256" in e for e in validate_payload("report", report))


def test_scenario_requires_a_usage_declaration() -> None:
    scenario = _scenario()
    del scenario["usage_declaration"]
    report = _claim()
    report["scenario"] = scenario
    assert any("usage_declaration" in e for e in validate_payload("report", report))


def test_framework_document_names_the_machine_checkable_artifacts() -> None:
    """The mapping table must point at the artifacts this test suite enforces."""
    doc = (ROOT / "docs" / "SCENARIO_ACCEPTANCE_FRAMEWORK.md").read_text(encoding="utf-8")
    for needle in (
        "acceptance-status.schema.json",
        "$defs/reviewReceipt",
        "$defs/criteriaFreeze",
        "negative_knowledge_ledger",
        "value.reproducibility",
    ):
        assert needle in doc

def test_freeze_must_predate_the_run() -> None:
    report = _claim()
    report["criteria_freeze"] = _freeze(frozen_at="2026-11-16T00:00:00Z")
    assert any("frozen_at is later" in e for e in validate_payload("report", report))


def test_post_run_criteria_amendment_invalidates_the_claim() -> None:
    report = _claim()
    report["criteria_freeze"] = _freeze(
        amendments=[
            {"field": "tolerance", "reason": "widen to 20%", "amend_at": "2026-11-16T00:00:00Z"}
        ]
    )
    assert any("amended after the run" in e for e in validate_payload("report", report))


def test_pre_run_criteria_amendment_is_allowed() -> None:
    report = _claim()
    report["criteria_freeze"] = _freeze(
        amendments=[
            {"field": "tolerance", "reason": "typo in declared unit", "amend_at": "2026-11-13T00:00:00Z"}
        ]
    )
    assert validate_payload("report", report) == []


def test_receipt_must_declare_checks_not_run() -> None:
    receipt = _receipt()
    del receipt["checks_not_run"]
    report = _claim()
    report["review_receipt"] = receipt
    assert any("checks_not_run" in e for e in validate_payload("report", report))


@pytest.mark.parametrize(
    "payload",
    [
        {"scenario": "not-an-object", "criteria_freeze": "not-an-object", "review_receipt": "no"},
        {"scenario": {}, "criteria_freeze": {}, "review_receipt": {"six_checks": None}},
        {"checks": None, "findings": None},
    ],
)
def test_malformed_blocks_produce_errors_instead_of_exceptions(payload: dict) -> None:
    errors = validate_payload("report", _report(**payload))
    assert errors, "malformed acceptance blocks must be rejected, not ignored"


def test_malformed_status_products_do_not_raise() -> None:
    errors = validate_payload(
        "status",
        {
            "schema_version": "2.0.0",
            "as_of": "2026-11-14",
            "purpose": "x" * 20,
            "field_definitions": {"code_implemented": "a", "scenario_validated": "b"},
            "release_rule": "y" * 20,
            "products": None,
        },
    )
    assert errors


def test_author_cannot_sign_their_own_gate() -> None:
    report = _claim()
    report["review_receipt"] = _receipt(
        reviewer={"handle": "m20375", "role": "author"}, independence="independent_party"
    )
    assert any("author cannot sign" in e for e in validate_payload("report", report))


def _probe():
    import importlib.util

    path = ROOT / "docs" / "scenario_acceptance_audit" / "make_figure.py"
    spec = importlib.util.spec_from_file_location("acceptance_probe", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_published_bypass_numbers_match_a_fresh_probe() -> None:
    """numbers.json cannot drift away from what the validator actually does."""
    probe = _probe()
    cases = probe.bypass_cases()
    attacks = [(name, kind, payload, expected) for name, kind, payload, expected in cases
               if not name.startswith("control")]
    rejected = 0
    for name, kind, payload, expected in attacks:
        errors = validate_payload(kind, payload)
        assert errors, f"bypass case was accepted: {name}"
        assert any(token in e for e in errors for token in expected), (name, errors)
        rejected += 1
    numbers = json.loads(
        (ROOT / "docs" / "scenario_acceptance_audit" / "numbers.json").read_text(encoding="utf-8")
    )
    assert numbers["bypass_attempts"] == len(attacks)
    assert numbers["bypass_rejected"] == rejected
    assert numbers["bypass_rejection_rate"] == 1.0
    assert numbers["control_case_accepted"] is True
    assert numbers["honest_claim_accepted"] is True
    assert numbers["status_file_valid"] is True
    assert (ROOT / "docs" / "scenario_acceptance_audit" / "acceptance_probe.png").is_file()
