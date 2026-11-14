"""Structural tests for shared evidence-product contracts."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = {
    "evidence": ROOT / "schemas" / "evidence-item.schema.json",
    "report": ROOT / "schemas" / "validation-report.schema.json",
    "asset": ROOT / "schemas" / "asset-record.schema.json",
}


@pytest.mark.parametrize("schema_path", SCHEMAS.values(), ids=SCHEMAS.keys())
def test_product_schema_is_valid_json_schema(schema_path: Path) -> None:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)


def test_evidence_requires_source_and_provenance() -> None:
    schema = json.loads(SCHEMAS["evidence"].read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    valid = {
        "evidence_id": "ev-001",
        "source_type": "file",
        "source_ref": "artifact://sha256/example",
        "sha256": "a" * 64,
        "provenance": {"source_owner": "fixture-suite"},
    }
    assert validator.is_valid(valid)
    assert not validator.is_valid({**valid, "provenance": {}})
    assert not validator.is_valid({**valid, "sha256": "not-a-digest"})


def test_report_does_not_accept_implicit_pass_states() -> None:
    schema = json.loads(SCHEMAS["report"].read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    report = {
        "schema_version": "0.1.0",
        "product_id": "research-audit",
        "product_version": "0.1.0",
        "run_id": "run-fixture-001",
        "created_at": "2026-11-14T00:00:00Z",
        "input_refs": ["artifact://report.pdf"],
        "checks": [{
            "check_id": "citation-support",
            "version": "0.1.0",
            "method": "model_assisted",
            "state": "inconclusive",
        }],
        "findings": [],
        "overall_status": "inconclusive",
        "provenance": {"input_fingerprints": {"report": "sha256:" + "a" * 64}},
    }
    assert validator.is_valid(report)
    assert not validator.is_valid({**report, "overall_status": "passed", "schema_version": "0.2"})
