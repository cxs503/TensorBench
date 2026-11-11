"""Comparison of two benchmark results into real, publishable delta numbers.

This is the module that makes a capability delta quantitative instead of
rhetorical: it pairs a baseline run with a candidate run of the same benchmark,
refuses pairs that are not comparable, and emits the exact numbers (primary
metric ratio, score change, criteria pass/fail transition) that later land in the
platform's ``tensor_capability_deltas`` and ``outcome_evaluations`` records.

Honesty rules baked in:

* a pair that fails any hard comparability check is reported as ``incomparable``
  and yields no category hint;
* a performance improvement in a run whose correctness gate failed is reported as
  a regression, never as an improvement;
* "unchanged" is a first-class verdict — it maps to ``no_substantive_delta``.
"""
from __future__ import annotations

import json
from typing import Any, Mapping

#: Hard comparability checks: a mismatch makes the pair incomparable.
_HARD_CHECKS = (
    ("benchmark.benchmark_id", "benchmark.benchmark_id"),
    ("benchmark.version", "benchmark.version"),
    ("workload.workload_id", "workload.workload_id"),
    ("workload.version", "workload.version"),
    ("provenance.configuration_sha256", "workload configuration"),
    ("provenance.criteria_sha256", "acceptance criteria"),
    ("environment.precision", "precision mode"),
)

#: Soft checks: a mismatch is disclosed but does not block the comparison.
_SOFT_CHECKS = (
    ("environment.architecture", "architecture"),
    ("environment.os", "operating system"),
    ("workload.repetitions", "repetition count"),
)

VERDICT_CATEGORY = {
    "improved": "capability_extension",
    "fixed": "defect_fix",
    "regressed": "falsified_hypothesis",
    "unchanged": "no_substantive_delta",
    "still_failing": "no_substantive_delta",
    "incomparable": None,
}

DEFAULT_MIN_RELATIVE_IMPROVEMENT = 0.10
DEFAULT_REGRESSION_TOLERANCE = 0.02


def _get(obj: Mapping[str, Any], dotted: str) -> Any:
    node: Any = obj
    for part in dotted.split("."):
        if not isinstance(node, Mapping) or part not in node:
            return None
        node = node[part]
    return node


def _metric_map(result: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {m["name"]: m for m in result.get("metrics", [])}


def _relative_change(baseline: float, candidate: float) -> float | None:
    if baseline == 0:
        return None
    return (candidate - baseline) / abs(baseline)


def compare_results(
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    min_relative_improvement: float | None = None,
    regression_tolerance: float | None = None,
    hypothesis: str | None = None,
) -> dict[str, Any]:
    """Compare a candidate run against a baseline run of the same benchmark."""
    if baseline.get("run_id") == candidate.get("run_id"):
        raise ValueError("baseline and candidate must be different runs")

    checks: list[dict[str, Any]] = []
    comparable = True
    for dotted, label in _HARD_CHECKS:
        left, right = _get(baseline, dotted), _get(candidate, dotted)
        ok = left == right and left not in (None, "")
        checks.append({"check": label, "hard": True, "ok": bool(ok),
                       "baseline": left, "candidate": right})
        comparable = comparable and ok
    for dotted, label in _SOFT_CHECKS:
        left, right = _get(baseline, dotted), _get(candidate, dotted)
        checks.append({"check": label, "hard": False, "ok": left == right,
                       "baseline": left, "candidate": right})

    metrics_base = _metric_map(baseline)
    metrics_cand = _metric_map(candidate)
    metric_deltas: list[dict[str, Any]] = []
    for name in sorted(set(metrics_base) & set(metrics_cand)):
        b = float(metrics_base[name]["value"])
        c = float(metrics_cand[name]["value"])
        better = metrics_cand[name].get("better") or metrics_base[name].get("better")
        change = _relative_change(b, c)
        improvement = None
        if change is not None and better in ("higher", "lower"):
            improvement = change if better == "higher" else -change
        metric_deltas.append({
            "name": name,
            "unit": metrics_cand[name].get("unit", ""),
            "better": better,
            "baseline": b,
            "candidate": c,
            "absolute_change": c - b,
            "relative_change": change,
            "improvement_ratio": (1.0 + improvement) if improvement is not None else None,
        })

    primary_name = None
    for source in (candidate, baseline):
        primary = (source.get("score") or {}).get("primary_metric") or {}
        if primary.get("name"):
            primary_name = primary["name"]
            break
    if primary_name is None:
        primary_name = "wall_time"

    primary_delta = next((d for d in metric_deltas if d["name"] == primary_name), None)
    primary_ratio = primary_delta["improvement_ratio"] if primary_delta else None

    threshold = (
        DEFAULT_MIN_RELATIVE_IMPROVEMENT
        if min_relative_improvement is None
        else float(min_relative_improvement)
    )
    tolerance = (
        DEFAULT_REGRESSION_TOLERANCE if regression_tolerance is None else float(regression_tolerance)
    )

    base_status = (baseline.get("acceptance") or {}).get("status", "not_evaluated")
    cand_status = (candidate.get("acceptance") or {}).get("status", "not_evaluated")

    if not comparable:
        verdict = "incomparable"
    elif base_status == "passed" and cand_status == "failed":
        verdict = "regressed"
    elif base_status in ("failed", "not_evaluated") and cand_status == "passed":
        verdict = "fixed"
    elif base_status == "failed" and cand_status == "failed":
        verdict = "still_failing"
    elif primary_ratio is None:
        verdict = "unchanged"
    elif primary_ratio - 1.0 >= threshold:
        verdict = "improved"
    elif primary_ratio - 1.0 <= -tolerance:
        verdict = "regressed"
    else:
        verdict = "unchanged"

    base_score = (baseline.get("score") or {}).get("value")
    cand_score = (candidate.get("score") or {}).get("value")

    return {
        "schema": "tensorbench.comparison/1.0",
        "comparable": comparable,
        "checks": checks,
        "disclosures": [f"{c['check']} differs: {c['baseline']} -> {c['candidate']}"
                        for c in checks if not c["ok"]],
        "benchmark": candidate.get("benchmark", {}),
        "baseline_run": baseline.get("run_id"),
        "candidate_run": candidate.get("run_id"),
        "baseline_implementation": baseline.get("implementation", {}),
        "candidate_implementation": candidate.get("implementation", {}),
        "primary_metric": {
            "name": primary_name,
            "unit": primary_delta["unit"] if primary_delta else "",
            "better": primary_delta["better"] if primary_delta else None,
            "baseline": primary_delta["baseline"] if primary_delta else None,
            "candidate": primary_delta["candidate"] if primary_delta else None,
            "improvement_ratio": primary_ratio,
            "relative_change": primary_delta["relative_change"] if primary_delta else None,
        },
        "score": {
            "baseline": base_score,
            "candidate": cand_score,
            "delta": (cand_score - base_score)
            if (base_score is not None and cand_score is not None) else None,
        },
        "criteria": {
            "baseline_status": base_status,
            "candidate_status": cand_status,
            "baseline_passed": (baseline.get("acceptance") or {}).get("criteria_passed"),
            "baseline_total": (baseline.get("acceptance") or {}).get("criteria_total"),
            "candidate_passed": (candidate.get("acceptance") or {}).get("criteria_passed"),
            "candidate_total": (candidate.get("acceptance") or {}).get("criteria_total"),
        },
        "metric_deltas": metric_deltas,
        "decision": {
            "thresholds": {
                "min_relative_improvement": threshold,
                "regression_tolerance": tolerance,
                "source": "CLI/spec declaration, applied before inspecting results",
            },
            "verdict": verdict,
            "category_hint": VERDICT_CATEGORY[verdict],
            "hypothesis": hypothesis,
        },
        "interpretation_limits": [
            "Correlation only: a single revision change is not isolated by this comparison.",
            "Performance numbers are machine- and load-dependent; ratios are only valid "
            "when the comparability checks above are all true.",
            "Criteria 'passed' means the declared tolerances were met, not that the "
            "numeric method is validated in general.",
        ],
    }


def comparison_summary_text(comparison: Mapping[str, Any]) -> str:
    """One-line human summary containing the numbers (used in platform records)."""
    verdict = comparison["decision"]["verdict"]
    primary = comparison.get("primary_metric") or {}
    ratio = primary.get("improvement_ratio")
    ratio_text = f"{ratio:.4f}x" if isinstance(ratio, (int, float)) else "n/a"
    return (
        f"verdict={verdict}; primary={primary.get('name')} "
        f"{primary.get('baseline')}->{primary.get('candidate')} {primary.get('unit')} "
        f"(ratio={ratio_text}); criteria {comparison['criteria']['baseline_status']}"
        f"->{comparison['criteria']['candidate_status']}"
    )


def load_result(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)