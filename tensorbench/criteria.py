"""Acceptance-criteria evaluation and benchmark scoring.

A run that "executed successfully" is not a benchmark that "passed". This module
turns a benchmark specification's declared acceptance criteria into an executable
verdict, and produces a deterministic score object that later stages (comparison,
platform write-back) can consume as real numbers.

Design rules:

* **Predeclared only.** Criteria come from the specification, never from the
  observed output. Nothing here can widen a tolerance after the fact.
* **Missing data is not a pass.** A criterion whose metric was not produced is
  ``not_measured`` and cannot yield ``passed``.
* **No domain semantics.** Comparators are numeric; the meaning of a metric is
  supplied by the benchmark owner in the specification.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

#: Comparators allowed in a criterion. Kept deliberately small: every one is
#: checkable without domain knowledge.
COMPARATORS: dict[str, Any] = {
    "<=": lambda value, threshold: value <= threshold,
    "<": lambda value, threshold: value < threshold,
    ">=": lambda value, threshold: value >= threshold,
    ">": lambda value, threshold: value > threshold,
}

#: Aggregations allowed when collapsing repeated samples into one value.
AGGREGATIONS = ("single_run", "mean", "median", "min", "max")


def canonical_json(obj: Any) -> str:
    """Stable JSON text for hashing (sorted keys, no whitespace, UTF-8 safe)."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def canonical_sha256(obj: Any) -> str:
    """Content hash used to prove two runs shared the same declared configuration."""
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def aggregate(samples: list[float], method: str) -> float:
    """Collapse repeated samples. ``median`` for even counts averages the middle two."""
    if not samples:
        raise ValueError("cannot aggregate an empty sample list")
    if method == "single_run":
        if len(samples) != 1:
            raise ValueError("aggregation 'single_run' requires exactly one sample")
        return float(samples[0])
    if method == "mean":
        return float(sum(samples) / len(samples))
    if method == "min":
        return float(min(samples))
    if method == "max":
        return float(max(samples))
    if method == "median":
        ordered = sorted(float(s) for s in samples)
        mid = len(ordered) // 2
        if len(ordered) % 2:
            return ordered[mid]
        return (ordered[mid - 1] + ordered[mid]) / 2.0
    raise ValueError(f"unsupported aggregation: {method!r}")


def metric_contracts(spec: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Declared metric contracts from ``spec.metrics`` keyed by metric name."""
    declared = spec.get("metrics") or []
    if not isinstance(declared, list):
        raise ValueError("spec.metrics must be an array")
    out: dict[str, dict[str, Any]] = {}
    for item in declared:
        if not isinstance(item, dict) or not item.get("name"):
            raise ValueError("each spec.metrics entry must be an object with a name")
        out[str(item["name"])] = dict(item)
    return out


def _coerce_number(value: Any, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{where} must be a number, got {type(value).__name__}")
    return float(value)


def evaluate_criteria(spec: Mapping[str, Any], metrics: Mapping[str, float]) -> dict[str, Any]:
    """Run the declared acceptance criteria against the measured metrics.

    Returns a record with ``status`` in ``passed`` / ``failed`` / ``not_evaluated``.
    ``not_evaluated`` means the benchmark declared no correctness criteria at all:
    such a benchmark is performance-only and must not be cited as validated.
    """
    acceptance = spec.get("acceptance") or {}
    criteria = acceptance.get("criteria") or []
    if not isinstance(criteria, list):
        raise ValueError("spec.acceptance.criteria must be an array")

    results: list[dict[str, Any]] = []
    for index, criterion in enumerate(criteria):
        if not isinstance(criterion, dict):
            raise ValueError(f"spec.acceptance.criteria[{index}] must be an object")
        criterion_id = str(criterion.get("criterion_id") or f"criterion-{index + 1}")
        metric = criterion.get("metric")
        comparator = criterion.get("comparator")
        if not metric:
            raise ValueError(f"{criterion_id}: 'metric' is required")
        if comparator not in COMPARATORS:
            raise ValueError(
                f"{criterion_id}: comparator must be one of {sorted(COMPARATORS)}"
            )
        threshold = _coerce_number(criterion.get("threshold"), f"{criterion_id}.threshold")

        record: dict[str, Any] = {
            "criterion_id": criterion_id,
            "metric": metric,
            "comparator": comparator,
            "threshold": threshold,
            "unit": str(criterion.get("unit", "")),
            "rationale": str(criterion.get("rationale", "")),
        }
        if metric not in metrics:
            record.update({"value": None, "passed": None, "state": "not_measured"})
            results.append(record)
            continue
        value = _coerce_number(metrics[metric], f"metric {metric!r}")
        passed = bool(COMPARATORS[comparator](value, threshold))
        record.update({"value": value, "passed": passed, "state": "passed" if passed else "failed"})
        results.append(record)

    if not results:
        status = "not_evaluated"
    elif any(r["state"] == "failed" for r in results):
        status = "failed"
    elif any(r["state"] == "not_measured" for r in results):
        status = "not_evaluated"
    else:
        status = "passed"

    passed_count = sum(1 for r in results if r["state"] == "passed")
    return {
        "status": status,
        "criteria": results,
        "criteria_total": len(results),
        "criteria_passed": passed_count,
        "reference": acceptance.get("reference") or {},
        "method": (
            "Predeclared numeric comparisons in the benchmark specification; "
            "metrics are produced by the workload and never re-tuned after execution."
        ),
    }


def compute_score(
    spec: Mapping[str, Any],
    acceptance: Mapping[str, Any],
    metrics: Mapping[str, float],
) -> dict[str, Any]:
    """Deterministic score object: correctness gate ratio + primary metric.

    ``value`` is the fraction of declared criteria that passed, so it is directly
    comparable across revisions and usable as the numeric input of a capability
    delta. Benchmarks that declare no criteria get ``value: null`` — never 1.0.
    """
    total = int(acceptance.get("criteria_total") or 0)
    passed = int(acceptance.get("criteria_passed") or 0)
    status = acceptance.get("status")

    primary_name = (spec.get("workload") or {}).get("primary_metric")
    if not primary_name:
        contracts = metric_contracts(spec)
        for name, contract in contracts.items():
            if contract.get("better") in ("higher", "lower") and name != "wall_time":
                primary_name = name
                break
    primary: dict[str, Any] | None = None
    if primary_name:
        contract = metric_contracts(spec).get(primary_name, {})
        value = metrics.get(primary_name)
        if value is not None:
            primary = {
                "name": primary_name,
                "value": float(value),
                "unit": str(contract.get("unit", "")),
                "better": str(contract.get("better", "informational")),
            }

    return {
        "kind": "criteria_pass_ratio",
        "value": (passed / total) if total else None,
        "status": status,
        "criteria_total": total,
        "criteria_passed": passed,
        "primary_metric": primary,
        "method": (
            "value = criteria_passed / criteria_total (null when no criteria are declared). "
            "Primary metric is the declared workload.primary_metric, otherwise the first "
            "declared metric with a better-direction."
        ),
    }