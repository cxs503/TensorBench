"""Tests for criteria evaluation, repeated runs, comparison and platform write-back.

Everything here uses synthetic metric names, so the suite stays free of domain
semantics; the reference stencil workload is exercised separately in
``test_reference_workload.py``.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema
import pytest

from tensorbench.cli import main as cli_main
from tensorbench.compare import compare_results
from tensorbench.criteria import aggregate, canonical_sha256, compute_score, evaluate_criteria
from tensorbench.publish import build_capability_delta, build_evaluation_payload
from tensorbench.runner import run_benchmark

SCHEMA_PATH = Path(__file__).parents[1] / "schemas" / "benchmark-result.schema.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

WORKLOAD = """
import json, pathlib, sys
out = pathlib.Path(sys.argv[1])
value = float(sys.argv[2])
out.write_text(json.dumps({"metrics": {"error": value, "score_points": 42.0}}))
"""


def make_spec(tmp_path: Path, *, value: float = 0.01, threshold: float = 0.02,
              repetitions: int = 1, warmup: int = 0, metrics_file: str = "metrics.json") -> dict:
    script = tmp_path / "workload.py"
    script.write_text(WORKLOAD, encoding="utf-8")
    out = tmp_path / metrics_file
    spec = {
        "benchmark": {"benchmark_id": "synthetic.bench", "version": "1.0.0"},
        "implementation": {"project": "synthetic impl"},
        "workload": {
            "workload_id": "synthetic-workload",
            "version": "1.0.0",
            "command": [sys.executable, str(script), str(out), str(value)],
            "cwd": str(tmp_path),
            "precision": "float64",
            "primary_metric": "score_points",
            "configuration": {"value": value},
            "output": {"metrics_file": metrics_file},
        },
        "metrics": [
            {"name": "error", "unit": "relative", "kind": "derived", "aggregation": "max", "better": "lower"},
            {"name": "score_points", "unit": "points", "kind": "measured", "aggregation": "median", "better": "higher"},
        ],
        "acceptance": {
            "criteria": [
                {"criterion_id": "tolerance", "metric": "error", "comparator": "<=", "threshold": threshold}
            ],
            "reference": {"kind": "synthetic", "source": "unit-test fixture"},
        },
        "protocol": {"warmup": warmup, "repetitions": repetitions},
        "execution": {"timeout_seconds": 60},
    }
    return spec


def memory_spec(*, threshold: float = 1.0) -> dict:
    """Specification dict used for pure-function tests; touches no filesystem."""
    return {
        "benchmark": {"benchmark_id": "synthetic.bench", "version": "1.0.0"},
        "implementation": {"project": "synthetic impl"},
        "workload": {
            "workload_id": "synthetic-workload",
            "version": "1.0.0",
            "command": ["true"],
            "cwd": ".",
            "precision": "float64",
            "primary_metric": "score_points",
            "configuration": {"value": 0.01},
        },
        "metrics": [
            {"name": "error", "unit": "relative", "kind": "derived", "aggregation": "max", "better": "lower"},
            {"name": "score_points", "unit": "points", "kind": "measured", "aggregation": "median", "better": "higher"},
        ],
        "acceptance": {
            "criteria": [
                {"criterion_id": "tolerance", "metric": "error", "comparator": "<=", "threshold": threshold}
            ],
            "reference": {"kind": "synthetic", "source": "unit-test fixture"},
        },
    }


# ─────────────────────────── criteria ───────────────────────────

def test_criteria_pass_fail_and_not_measured():
    spec = memory_spec(threshold=0.5)
    passed = evaluate_criteria(spec, {"error": 0.4})
    assert passed["status"] == "passed"
    assert passed["criteria"][0]["state"] == "passed"

    failed = evaluate_criteria(spec, {"error": 0.6})
    assert failed["status"] == "failed"

    missing = evaluate_criteria(spec, {})
    assert missing["status"] == "not_evaluated"
    assert missing["criteria"][0]["state"] == "not_measured"
    assert missing["criteria"][0]["passed"] is None


def test_no_declared_criteria_is_not_a_pass():
    spec = memory_spec()
    spec["acceptance"] = {"criteria": []}
    verdict = evaluate_criteria(spec, {"error": 1e9})
    assert verdict["status"] == "not_evaluated"
    score = compute_score(spec, verdict, {"error": 1e9})
    assert score["value"] is None  # never silently 1.0


def test_aggregations_and_configuration_hash():
    assert aggregate([1.0, 3.0], "median") == 2.0
    assert aggregate([1.0, 2.0, 9.0], "median") == 2.0
    assert aggregate([1.0, 3.0], "mean") == 2.0
    assert aggregate([5.0], "single_run") == 5.0
    with pytest.raises(ValueError):
        aggregate([1.0, 2.0], "single_run")
    assert canonical_sha256({"a": 1, "b": 2}) == canonical_sha256({"b": 2, "a": 1})


# ─────────────────────────── runner ───────────────────────────

def test_repeated_run_records_samples_and_schema_valid(tmp_path):
    spec = make_spec(tmp_path, repetitions=3, warmup=1)
    result = run_benchmark(spec, tmp_path / "out")

    assert result["execution"]["status"] == "success"
    assert result["acceptance"]["status"] == "passed"
    assert result["score"]["value"] == 1.0
    error_metric = next(m for m in result["metrics"] if m["name"] == "error")
    assert len(error_metric["samples"]) == 3
    assert error_metric["aggregation"] == "max"
    assert result["workload"]["repetitions"] == 3
    assert result["validation"]["correctness"] == "passed"

    persisted = json.loads(next((tmp_path / "out").glob("*.result.json")).read_text())
    jsonschema.validate(persisted, SCHEMA)
    # warm-up repetitions stay out of the measured samples
    assert persisted["provenance"]["configuration_sha256"] == canonical_sha256({"value": 0.01})
    assert len(list((tmp_path / "out").glob("*.warm1.stdout.log"))) == 1


def test_failed_criterion_makes_run_not_correct(tmp_path):
    spec = make_spec(tmp_path, value=0.9, threshold=0.1)
    result = run_benchmark(spec, tmp_path / "out")
    assert result["execution"]["status"] == "success"  # the process succeeded
    assert result["acceptance"]["status"] == "failed"  # the benchmark did not
    assert result["validation"]["correctness"] == "failed"
    assert result["score"]["value"] == 0.0
    jsonschema.validate(json.loads(next((tmp_path / "out").glob("*.result.json")).read_text()), SCHEMA)


def test_metrics_file_must_be_declared(tmp_path):
    spec = make_spec(tmp_path, metrics_file="metrics.json")
    spec["metrics"] = [m for m in spec["metrics"] if m["name"] != "score_points"]
    result = run_benchmark(spec, tmp_path / "out")
    assert "score_points" in result["execution"]["notes"]


# ─────────────────────────── comparison ───────────────────────────

def _result(run_id: str, *, error: float, points: float, threshold: float = 1.0) -> dict:
    spec = memory_spec(threshold=threshold)
    metrics = {
        "wall_time": 1.0,
        "error": error,
        "score_points": points,
    }
    acceptance = evaluate_criteria(spec, metrics)
    return {
        "run_id": run_id,
        "benchmark": {"benchmark_id": "synthetic.bench", "version": "1.0.0"},
        "implementation": {"project": "impl", "revision": "a" * 40},
        "workload": {"workload_id": "synthetic-workload", "version": "1.0.0", "repetitions": 1},
        "environment": {"architecture": "loongarch64", "os": "linux", "precision": "float64"},
        "provenance": {
            "configuration_sha256": canonical_sha256({"value": 0.01}),
            "criteria_sha256": canonical_sha256(spec["acceptance"]["criteria"]),
            "spec_sha256": canonical_sha256(spec),
        },
        "metrics": [
            {"name": "score_points", "value": points, "unit": "points", "kind": "measured",
             "better": "higher", "aggregation": "median"},
            {"name": "wall_time", "value": 1.0, "unit": "seconds", "kind": "measured",
             "aggregation": "single_run"},
        ],
        "acceptance": acceptance,
        "score": compute_score(spec, acceptance, metrics),
    }


def test_comparison_improved_requires_threshold():
    base = _result("run-a", error=0.1, points=100.0)
    better = _result("run-b", error=0.1, points=150.0)
    comparison = compare_results(base, better)
    assert comparison["comparable"] is True
    assert comparison["decision"]["verdict"] == "improved"
    assert comparison["decision"]["category_hint"] == "capability_extension"
    assert comparison["primary_metric"]["improvement_ratio"] == pytest.approx(1.5)
    assert comparison["score"]["delta"] == 0.0


def test_comparison_unchanged_is_a_real_verdict():
    base = _result("run-a", error=0.1, points=100.0)
    same = _result("run-b", error=0.1, points=101.0)
    comparison = compare_results(base, same)
    assert comparison["decision"]["verdict"] == "unchanged"
    assert comparison["decision"]["category_hint"] == "no_substantive_delta"


def test_performance_win_with_failed_correctness_is_a_regression():
    base = _result("run-a", error=0.1, points=100.0)
    broken = _result("run-b", error=5.0, points=900.0, threshold=1.0)
    assert broken["acceptance"]["status"] == "failed"
    comparison = compare_results(base, broken)
    assert comparison["decision"]["verdict"] == "regressed"
    assert comparison["decision"]["category_hint"] == "falsified_hypothesis"


def test_different_configuration_is_incomparable():
    base = _result("run-a", error=0.1, points=100.0)
    other = _result("run-b", error=0.1, points=150.0)
    other["provenance"]["configuration_sha256"] = canonical_sha256({"value": 99})
    comparison = compare_results(base, other)
    assert comparison["comparable"] is False
    assert comparison["decision"]["verdict"] == "incomparable"
    assert comparison["decision"]["category_hint"] is None
    assert any("workload configuration" in d for d in comparison["disclosures"])


# ─────────────────────────── publish payloads ───────────────────────────

def test_evaluation_payload_satisfies_platform_rules():
    base = _result("run-a", error=0.1, points=100.0)
    better = _result("run-b", error=0.1, points=150.0)
    comparison = compare_results(base, better)
    payload = build_evaluation_payload(
        better, comparison, mission_id=7, contributor="agent-x", reviewer="auditor-y",
        artifact_refs=[{"path": "/tmp/x.result.json", "sha256": "a" * 64}], report_id=4242,
    )
    assert payload["grade"] == "S3"
    assert payload["e_level"] == "E2"
    assert len("".join(payload["grade_reason"].split())) >= 50
    assert payload["reviewer"] != payload["contributor"]
    assert {r["kind"] for r in payload["evidence_refs"]} == {"benchmark", "run", "artifact"}
    assert all(payload["evidence_chain"].values())
    assert payload["evidence_chain"]["report"] == "4242"
    assert payload["evidence_chain"]["config"].startswith("sha256:")
    assert "1.5" in payload["baseline_or_scope"] or "1.5" in json.dumps(payload)


def test_no_baseline_benchmark_is_not_promoted_to_s3():
    result = _result("run-a", error=0.1, points=100.0)
    payload = build_evaluation_payload(result, None, mission_id=7, contributor="agent-x",
                                       reviewer="auditor-y", report_id=4242)
    assert payload["grade"] == "S2"  # S3 requires a declared, comparable baseline
    assert payload["e_level"] == "E2"


def test_missing_report_id_caps_evidence_level():
    result = _result("run-a", error=0.1, points=100.0)
    payload = build_evaluation_payload(result, None, mission_id=7, contributor="agent-x",
                                       reviewer="auditor-y")
    assert payload["evidence_chain"]["report"] == ""
    assert payload["e_level"] == "E1"  # an incomplete chain must not claim E2


def test_failed_benchmark_goes_to_negative_track():
    result = _result("run-a", error=9.0, points=10.0, threshold=1.0)
    assert result["acceptance"]["status"] == "failed"
    payload = build_evaluation_payload(result, None, mission_id=7, contributor="agent-x",
                                       reviewer="auditor-y", report_id=4242)
    assert payload["grade"] == "S-N"
    assert payload["e_level"] == "E1" or payload["e_level"] == "E2"


def test_capability_delta_carries_real_numbers():
    base = _result("run-a", error=0.1, points=100.0)
    better = _result("run-b", error=0.1, points=150.0)
    comparison = compare_results(base, better)
    delta = build_capability_delta(comparison, result=better)
    assert delta["category"] == "capability_extension"
    assert delta["evidence"]["primary_metric"]["improvement_ratio"] == pytest.approx(1.5)
    assert "150" in delta["summary"]
    assert delta["credit_hint"]["numbers"]["improvement_ratio"] == pytest.approx(1.5)


# ─────────────────────────── CLI ───────────────────────────

def test_cli_run_compare_publish_dry_run(tmp_path, capsys, monkeypatch):
    spec = make_spec(tmp_path)
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    out = tmp_path / "runs"
    monkeypatch.setattr(sys, "argv", ["tensorbench", "run", "--spec", str(spec_path),
                                      "--output", str(out)])
    assert cli_main() == 0
    result_path = next(out.glob("*.result.json"))

    comparison_path = tmp_path / "comparison.json"
    monkeypatch.setattr(sys, "argv", ["tensorbench", "compare", "--baseline", str(result_path),
                                      "--candidate", str(result_path)])
    # identical runs are rejected up front
    assert cli_main() == 2

    monkeypatch.setattr(sys, "argv", [
        "tensorbench", "publish", "--result", str(result_path), "--mission-id", "3",
        "--contributor", "agent-x", "--reviewer", "auditor-y", "--output", str(tmp_path / "pub"),
    ])
    assert cli_main() == 0
    bundle = json.loads(next((tmp_path / "pub").glob("*.publish.json")).read_text())
    assert bundle["evaluation"]["mission_id"] == 3
    assert bundle["comparison"] is None
    assert comparison_path.exists() is False