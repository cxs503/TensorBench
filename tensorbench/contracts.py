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
}


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
        checks = payload.get("checks", [])
        findings = payload.get("findings", [])
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
        if payload.get("source_type") == "url" and not provenance.get("source_version"):
            errors.append("URL evidence requires provenance.source_version or a captured snapshot")
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
