"""Runtime validation for TensorBench evidence-product contracts.

JSON Schema checks structure; semantic checks enforce evidence traceability and
prevent an inconclusive required check from being reported as a pass.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

SCHEMA_FILES = {
    "evidence": "evidence-item.schema.json",
    "report": "validation-report.schema.json",
    "asset": "asset-record.schema.json",
    "status": "acceptance-status.schema.json",
}

#: The six checks an independent review receipt must perform by re-execution.
SIX_REVIEW_CHECKS = (
    "artifact_identity",
    "criteria_frozen_before_run",
    "evidence_traceability",
    "independent_rerun",
    "failure_record",
    "regression_scope",
)

#: Independence grades that may never authorise a passing acceptance claim.
NON_INDEPENDENT = {"self_review", "same_owner"}


class ContractValidationError(ValueError):
    """Raised when a payload violates a TensorBench contract."""


def load_schema(kind: str, schema_dir: str | Path | None = None) -> dict[str, Any]:
    if kind not in SCHEMA_FILES:
        raise ContractValidationError(
            f"unknown contract {kind!r}; expected one of {', '.join(SCHEMA_FILES)}"
        )
    root = Path(schema_dir) if schema_dir else Path(__file__).resolve().parents[1] / "schemas"
    path = root / SCHEMA_FILES[kind]
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractValidationError(f"cannot load schema {path}: {exc}") from exc
    Draft202012Validator.check_schema(schema)
    return schema


def _semantic_errors(kind: str, payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if kind == "report":
        checks = payload.get("checks") or []
        findings = payload.get("findings") or []
        checks = [c for c in checks if isinstance(c, dict)]
        findings = [f for f in findings if isinstance(f, dict)]
        failed_required = [
            c.get("check_id", "<unknown>")
            for c in checks
            if c.get("required", True) and c.get("state") == "failed"
        ]
        unresolved_required = [
            c.get("check_id", "<unknown>")
            for c in checks
            if c.get("required", True)
            and c.get("state") in {"not_measured", "inconclusive"}
        ]
        if payload.get("overall_status") == "passed" and failed_required:
            errors.append(
                "overall_status cannot be passed: required checks failed: "
                + ", ".join(failed_required)
            )
        if payload.get("overall_status") == "passed" and unresolved_required:
            errors.append(
                "overall_status cannot be passed: required checks unresolved: "
                + ", ".join(unresolved_required)
            )
        if "evidence_refs" in payload:
            known_refs = set(payload["evidence_refs"])
            for finding in findings:
                for ref in finding.get("evidence_refs", []):
                    if ref not in known_refs:
                        errors.append(
                            f"finding {finding.get('finding_id', '<unknown>')} "
                            f"references evidence {ref!r} absent from report.evidence_refs"
                        )
                for ref in finding.get("counter_evidence_refs", []):
                    if ref not in known_refs:
                        errors.append(
                            f"finding {finding.get('finding_id', '<unknown>')} "
                            f"references counter-evidence {ref!r} absent from report.evidence_refs"
                        )
        errors.extend(_report_acceptance_errors(payload))
    elif kind == "status":
        errors.extend(_status_errors(payload))
    elif kind == "asset":
        maturity = payload.get("maturity")
        refs = payload.get("validation_report_refs", [])
        if maturity in {"A2_verified", "A3_reusable", "A4_adopted"} and not refs:
            errors.append(f"{maturity} assets require at least one validation_report_ref")
        if maturity in {"A3_reusable", "A4_adopted"} and not payload.get("source_revision"):
            errors.append(f"{maturity} assets require source_revision")
        if payload.get("rights_status") in {"unknown", "quarantined"} and maturity == "A4_adopted":
            errors.append("assets with unknown or quarantined rights cannot be A4_adopted")
    elif kind == "evidence":
        provenance = payload.get("provenance", {})
        if not isinstance(provenance, dict):
            provenance = {}
        if payload.get("source_type") == "url" and not provenance.get("source_version"):
            errors.append("URL evidence requires provenance.source_version or a captured snapshot")
    return errors


def _report_acceptance_errors(payload: dict[str, Any]) -> list[str]:
    """Bind a scenario acceptance claim to a frozen criteria set and a real review receipt."""
    errors: list[str] = []
    scenario = payload.get("scenario")
    receipt = payload.get("review_receipt")
    if scenario is not None and payload.get("criteria_freeze") is None:
        errors.append("scenario acceptance requires criteria_freeze: criteria must be declared before the run")
    if scenario is not None and receipt is None:
        errors.append("scenario acceptance requires review_receipt: an unreviewed run is not a validated scenario")
    freeze = payload.get("criteria_freeze")
    if isinstance(freeze, dict):
        errors.extend(_freeze_errors(freeze, payload.get("created_at")))
    if scenario is not None:
        basis = scenario.get("permission_basis") if isinstance(scenario, dict) else None
        if basis == "quarantined" and payload.get("overall_status") == "passed":
            errors.append("overall_status cannot be passed: scenario inputs are quarantined (rights unknown)")
        if basis == "synthetic_labelled" and payload.get("overall_status") == "passed":
            errors.append(
                "overall_status cannot be passed: synthetic_labelled inputs are admissible for "
                "adversarial/regression runs only, never as scenario validation"
            )
    if receipt is None:
        return errors
    if not isinstance(receipt, dict):
        errors.append("review_receipt must be an object")
        return errors

    verdict = receipt.get("verdict")
    independence = receipt.get("independence")
    checks = receipt.get("six_checks") or []
    checks = [c for c in checks if isinstance(c, dict)]
    by_id = {c.get("check_id"): c.get("state") for c in checks}
    missing = [cid for cid in SIX_REVIEW_CHECKS if cid not in by_id]
    if missing:
        errors.append("review_receipt is missing six_checks: " + ", ".join(missing))
    not_passed = [cid for cid in SIX_REVIEW_CHECKS if by_id.get(cid) not in {None, "passed"}]
    not_run = receipt.get("checks_not_run", []) or []
    blockers = receipt.get("blocking_conditions", []) or []
    rerun = receipt.get("rerun") if isinstance(receipt.get("rerun"), dict) else {}

    if verdict == "pass":
        reviewer = receipt.get("reviewer") if isinstance(receipt.get("reviewer"), dict) else {}
        if reviewer.get("role") == "author":
            errors.append(
                "review_receipt verdict cannot be pass: an author cannot sign the acceptance gate"
            )
        if independence in NON_INDEPENDENT:
            errors.append(
                f"review_receipt verdict cannot be pass: independence={independence} cannot authorise acceptance"
            )
        if not_passed:
            errors.append("review_receipt verdict cannot be pass: six_checks not passed: " + ", ".join(not_passed))
        if not_run:
            errors.append("review_receipt verdict cannot be pass: checks_not_run is not empty")
        if blockers:
            errors.append("review_receipt verdict cannot be pass: blocking_conditions is not empty")
        if rerun.get("exit_code") != 0:
            errors.append("review_receipt verdict cannot be pass: reviewer rerun exit_code is not 0")
        if payload.get("overall_status") != "passed":
            errors.append(
                "review_receipt verdict pass requires overall_status=passed "
                f"(got {payload.get('overall_status')!r})"
            )
    elif verdict in {"fail", "changes_requested", "escalate"}:
        if payload.get("overall_status") == "passed":
            errors.append(
                f"overall_status cannot be passed: review_receipt verdict is {verdict}"
            )
    return errors


def _parse_ts(value: Any) -> Any:
    """Parse an ISO-8601 timestamp; return None when it cannot be compared safely."""
    if not isinstance(value, str):
        return None
    from datetime import datetime, timezone

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _freeze_errors(freeze: dict[str, Any], created_at: Any) -> list[str]:
    """A freeze only means something if it predates the run and was not widened after it."""
    errors: list[str] = []
    run_at = _parse_ts(created_at)
    frozen_at = _parse_ts(freeze.get("frozen_at"))
    if run_at and frozen_at and frozen_at > run_at:
        errors.append(
            "criteria_freeze.frozen_at is later than report.created_at: criteria were not frozen before the run"
        )
    for amendment in freeze.get("amendments", []) or []:
        if not isinstance(amendment, dict):
            continue
        amend_at = _parse_ts(amendment.get("amend_at"))
        if run_at and amend_at and amend_at > run_at:
            errors.append(
                "criteria were amended after the run started "
                f"({amendment.get('field', '<unknown>')}): the frozen criteria do not cover this run"
            )
    return errors


def _status_errors(payload: dict[str, Any]) -> list[str]:
    """Cross-field rules for products/STATUS.json v2 (code_implemented vs scenario_validated)."""
    errors: list[str] = []
    products = payload.get("products") or []
    products = [p for p in products if isinstance(p, dict)] if isinstance(products, list) else []
    ids = [p.get("id") for p in products]
    for expected in ("AE", "RA", "BE", "PV"):
        if expected not in ids:
            errors.append(f"products must declare product line {expected}")
    for product in products:
        pid = product.get("id", "<unknown>")
        code = product.get("code_implemented")
        scenario = product.get("scenario_validated")
        evidence = product.get("acceptance_evidence")
        evidence = evidence if isinstance(evidence, dict) else {}
        if code is False and scenario is True:
            errors.append(
                f"{pid}: scenario_validated=true requires code_implemented=true "
                "(a scenario cannot run code that does not exist)"
            )
        if scenario is True:
            for field in ("validation_report_ref", "review_receipt_ref"):
                if not evidence.get(field):
                    errors.append(
                        f"{pid}: scenario_validated=true requires acceptance_evidence.{field}"
                    )
            if evidence.get("verdict") not in {None, "pass"}:
                errors.append(
                    f"{pid}: scenario_validated=true requires acceptance_evidence.verdict=pass "
                    f"(got {evidence.get('verdict')!r})"
                )
        if scenario is False and evidence.get("verdict") == "pass":
            errors.append(
                f"{pid}: a passing acceptance verdict must set scenario_validated=true"
            )
    return errors


def validate_payload(
    kind: str, payload: Any, schema_dir: str | Path | None = None
) -> list[str]:
    """Return all structural and semantic validation errors; [] means valid."""
    if not isinstance(payload, dict):
        return ["payload must be a JSON object"]
    schema = load_schema(kind, schema_dir)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = [
        f"{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in validator.iter_errors(payload)
    ]
    errors.extend(_semantic_errors(kind, payload))
    return sorted(set(errors))


def validate_file(
    kind: str, path: str | Path, schema_dir: str | Path | None = None
) -> dict[str, Any]:
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractValidationError(f"cannot read JSON input {source}: {exc}") from exc
    errors = validate_payload(kind, payload, schema_dir=schema_dir)
    return {
        "contract": kind,
        "input": str(source),
        "status": "valid" if not errors else "invalid",
        "error_count": len(errors),
        "errors": errors,
    }
