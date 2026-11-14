"""Write benchmark evidence back into the platform evaluation loop.

The loop this module closes::

    benchmark spec -> run (runner) -> result JSON -> comparison (compare.py)
        -> outcome_evaluations payload (S-grade evidence)
        -> tensor_capability_deltas payload (real numbers, not adjectives)
        -> credit / S-grade review consume the same record

Two payload builders and one thin HTTP client live here. Builders are pure
functions (no network, no database) so their output can be inspected, diffed and
tested; the client only knows how to authenticate and POST.

Contract notes, taken from the platform's own evaluation API:

* ``grade_reason`` needs >= 50 non-whitespace characters;
* evidence references must use a whitelisted kind (``benchmark`` / ``run`` /
  ``artifact`` are the relevant ones here);
* the reviewer must differ from the contributor;
* ``S2``/``S4`` require a baseline, ``S5`` requires a scope, and the five-element
  evidence chain must be present or the evidence level is capped at ``E1``.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Mapping

from .compare import comparison_summary_text

#: Evidence kinds accepted by the platform evaluation API.
EVIDENCE_KIND_BENCHMARK = "benchmark"
EVIDENCE_KIND_RUN = "run"
EVIDENCE_KIND_ARTIFACT = "artifact"

DEFAULT_API_BASE = "http://127.0.0.1:8010/api/v1"


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def default_artifact_refs(result_path: str | Path, comparison_path: str | Path | None = None) -> list[dict[str, str]]:
    """Artifact references (path + sha256) for the run record and its comparison."""
    refs: list[dict[str, str]] = []
    for raw in (result_path, comparison_path):
        if raw is None:
            continue
        path = Path(raw).resolve()
        refs.append({"path": str(path), "sha256": _file_sha256(path), "size_bytes": path.stat().st_size})
    return refs


def _benchmark_ref(result: Mapping[str, Any]) -> str:
    bench = result.get("benchmark", {})
    work = result.get("workload", {})
    return (
        f"tensorbench://{bench.get('benchmark_id')}@{bench.get('version')}"
        f"/{work.get('workload_id')}@{work.get('version')}/run={result.get('run_id')}"
    )


def build_evidence_chain(
    result: Mapping[str, Any],
    reference: Mapping[str, Any] | None = None,
    report_id: int | str | None = None,
) -> dict[str, Any]:
    """Five-element chain: theory / code / config / data / report.

    The element shapes follow the platform's evidence-chain validators, which are
    stricter than "non-empty string": ``theory`` needs a URL/DOI/``derivation:``
    prefix, ``code`` a commit sha (optionally ``repo@sha``), ``config`` a
    ``sha256:<hex>`` hash, ``data`` a path or ``file:``/``run:`` anchor, and
    ``report`` a positive platform report id. A chain that violates those shapes is
    judged *invalid* and caps the evidence level at E1, which demotes an S3 claim to
    ``candidate`` - found the hard way by writing this file against the live API.
    """
    test_impl = result.get("implementation", {})
    provenance = result.get("provenance", {})
    acceptance = result.get("acceptance", {})
    reference = reference or {}

    theory = reference.get("theory_ref")
    if not theory:
        source = (acceptance.get("reference") or {}).get("source", "")
        theory = f"derivation:declared acceptance criteria ({source}) bounded before execution"
    revision = str(test_impl.get("revision") or "")
    code = (
        f"{test_impl.get('project')}@{revision}"
        if revision and revision.isalnum() and len(revision) >= 7
        else str(provenance.get("spec_sha256") or "")
    )
    config = f"sha256:{provenance.get('configuration_sha256')}"
    data_ref = reference.get("data_ref") or result.get("data_ref")
    if not data_ref:
        artifacts = result.get("artifacts") or []
        first = artifacts[0] if artifacts else {}
        data_ref = (
            f"file:{first.get('uri')}#sha256={first.get('sha256')}"
            if first.get("uri")
            else f"run:{result.get('run_id')}"
        )
    report = reference.get("report_ref") or report_id
    return {
        "theory": theory,
        "code": code,
        "config": config,
        "data": data_ref,
        "report": str(report) if report not in (None, "") else "",
    }


def build_evaluation_payload(
    result: Mapping[str, Any],
    comparison: Mapping[str, Any] | None = None,
    *,
    mission_id: int,
    contributor: str,
    reviewer: str,
    repo: str | None = None,
    grade: str | None = None,
    e_level: str | None = None,
    boundary: str | None = None,
    artifact_refs: list[dict[str, Any]] | None = None,
    report_ref: str | None = None,
    report_id: int | str | None = None,
) -> dict[str, Any]:
    """Build an ``outcome_evaluations`` write payload from a benchmark run.

    A benchmark that passed its predeclared criteria is eligible as ``S3`` gate
    evidence only when a comparison against a declared baseline exists; without a
    baseline the same evidence is registered as ``S2`` (baseline required) or
    ``S1`` and the reason string says so explicitly.
    """
    acceptance = result.get("acceptance", {})
    status = acceptance.get("status", "not_evaluated")
    score = result.get("score", {})
    metrics = {m["name"]: m for m in result.get("metrics", [])}
    primary = score.get("primary_metric") or {}

    if grade is None:
        if status != "passed":
            grade = "S1" if status == "not_evaluated" else "S-N"
        elif comparison is not None and comparison.get("comparable"):
            grade = "S3"
        else:
            grade = "S2"
    if e_level is None:
        chain = build_evidence_chain(result, {"report_ref": report_ref}, report_id)
        complete = all(chain.values())
        e_level = "E2" if (complete and status == "passed") else "E1"

    passed = acceptance.get("criteria_passed", 0)
    total = acceptance.get("criteria_total", 0)
    ratio_text = (
        f"{primary.get('name')}={primary.get('value'):.6g}{primary.get('unit') or ''}"
        if primary.get("value") is not None
        else "primary metric unavailable"
    )
    parts = [
        f"benchmark {result.get('benchmark', {}).get('benchmark_id')}@"
        f"{result.get('benchmark', {}).get('version')} run={result.get('run_id')}",
        f"predeclared criteria {passed}/{total} passed (status={status})",
        f"{ratio_text}",
        f"score={score.get('value')}",
    ]
    if comparison is not None:
        parts.append(f"comparison: {comparison_summary_text(comparison)}")
        parts.append(
            "comparability hard-checks "
            f"{'all true' if comparison.get('comparable') else 'FAILED: ' + '; '.join(comparison.get('disclosures') or [])}"
        )
    parts.append(
        "the pass state is limited to the declared tolerances, workload configuration and "
        "machine disclosed in the run record; it is not a general validation claim"
    )
    grade_reason = "; ".join(parts)
    if len("".join(grade_reason.split())) < 50:  # platform minimum, see module docstring
        grade_reason = grade_reason + "; reason padded with the run provenance hash " + str(
            (result.get("provenance") or {}).get("spec_sha256")
        )

    refs: list[dict[str, str]] = [
        {"kind": EVIDENCE_KIND_BENCHMARK, "ref": _benchmark_ref(result)},
        {"kind": EVIDENCE_KIND_RUN, "ref": str(result.get("run_id"))},
    ]
    for artifact in artifact_refs or []:
        refs.append({
            "kind": EVIDENCE_KIND_ARTIFACT,
            "ref": f"{artifact['path']}#sha256={artifact['sha256']}",
        })

    baseline_or_scope = None
    if comparison is not None:
        baseline_or_scope = (
            f"baseline_run={comparison.get('baseline_run')} "
            f"candidate_run={comparison.get('candidate_run')} "
            f"primary={comparison.get('primary_metric', {}).get('name')} "
            f"{comparison.get('primary_metric', {}).get('baseline')}->"
            f"{comparison.get('primary_metric', {}).get('candidate')} "
            f"ratio={comparison.get('primary_metric', {}).get('improvement_ratio')}"
        )

    if boundary is None:
        boundary = (
            "Scope: this benchmark's declared workload configuration, precision and the "
            "machine recorded in the run environment. Out of scope: other sizes, other "
            "hardware, and any claim about scientific validity beyond the declared criteria."
        )

    chain = build_evidence_chain(result, {"report_ref": report_ref}, report_id)
    return {
        "artifact_id": f"{result.get('benchmark', {}).get('benchmark_id')}@{result.get('benchmark', {}).get('version')}/{result.get('run_id')}",
        "mission_id": int(mission_id),
        "contributor": contributor,
        "grade": grade,
        "e_level": e_level,
        "grade_reason": grade_reason,
        "evidence_refs": refs,
        "reviewer": reviewer,
        "reviewer_kind": "auto_scan",
        "baseline_or_scope": baseline_or_scope,
        "boundary": boundary,
        "repo": repo,
        "evidence_chain": chain,
    }


def build_capability_delta(
    comparison: Mapping[str, Any],
    *,
    category: str | None = None,
    artifacts: list[str] | None = None,
    result: Mapping[str, Any] | None = None,
    summary_hint: str | None = None,
) -> dict[str, Any]:
    """Build a ``tensor_capability_deltas`` payload carrying the comparison numbers."""
    verdict = comparison["decision"]["verdict"]
    suggested = comparison["decision"].get("category_hint")
    category = category or suggested or "no_substantive_delta"
    primary = comparison.get("primary_metric") or {}
    ratio = primary.get("improvement_ratio")
    ratio_text = f"{ratio:.4f}x" if isinstance(ratio, (int, float)) else "n/a"
    score = comparison.get("score") or {}
    crit = comparison.get("criteria") or {}

    summary = summary_hint or (
        f"benchmark {comparison.get('benchmark', {}).get('benchmark_id')}: "
        f"{primary.get('name')} {primary.get('baseline')}->{primary.get('candidate')} "
        f"{primary.get('unit') or ''} (ratio {ratio_text}); "
        f"criteria {crit.get('baseline_status')}->{crit.get('candidate_status')}"
    )

    reason = (
        f"verdict={verdict}; thresholds={json.dumps(comparison['decision']['thresholds'], sort_keys=True)}; "
        f"score {score.get('baseline')}->{score.get('candidate')}; "
        f"baseline_run={comparison.get('baseline_run')} candidate_run={comparison.get('candidate_run')}; "
        f"comparable={comparison.get('comparable')}"
    )
    if not comparison.get("comparable"):
        reason += "; NOT comparable, no performance claim is booked: " + "; ".join(
            comparison.get("disclosures") or []
        )

    evidence: dict[str, Any] = {
        "benchmark": comparison.get("benchmark", {}),
        "baseline_run": comparison.get("baseline_run"),
        "candidate_run": comparison.get("candidate_run"),
        "baseline_implementation": comparison.get("baseline_implementation"),
        "candidate_implementation": comparison.get("candidate_implementation"),
        "primary_metric": primary,
        "score": score,
        "criteria": crit,
        "metric_deltas": comparison.get("metric_deltas"),
        "checks": comparison.get("checks"),
        "limits": comparison.get("interpretation_limits"),
    }
    if result is not None:
        evidence["candidate_acceptance"] = result.get("acceptance")
        evidence["candidate_provenance"] = result.get("provenance")

    credit_hint = {
        "grade_basis": "benchmark_pass_with_comparison" if comparison.get("comparable") else "none",
        "verdict": verdict,
        "numbers": {
            "primary_metric": primary.get("name"),
            "baseline": primary.get("baseline"),
            "candidate": primary.get("candidate"),
            "improvement_ratio": ratio,
            "score_delta": score.get("delta"),
        },
    }
    evidence["credit_hint"] = credit_hint

    return {
        "category": category,
        "summary": summary,
        "reason": reason,
        "artifacts": list(artifacts or []),
        "evidence": evidence,
        "credit_hint": credit_hint,
    }


class PlatformClient:
    """Minimal authenticated client for the platform evaluation API."""

    def __init__(self, base_url: str | None = None, token: str | None = None, timeout: float = 30.0):
        self.base_url = (base_url or os.environ.get("TENSOR_API_BASE") or DEFAULT_API_BASE).rstrip("/")
        self.token = token
        self.timeout = timeout

    # -- transport ---------------------------------------------------------
    def _request(self, method: str, path: str, body: Mapping[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                return {"status": response.status, "data": json.loads(raw) if raw else None}
        except urllib.error.HTTPError as exc:  # keep the body: rejection reasons matter
            raw = exc.read().decode("utf-8", "replace")
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = raw
            return {"status": exc.code, "data": parsed}
        except urllib.error.URLError as exc:
            raise RuntimeError(f"platform unreachable at {url}: {exc}") from exc

    def login(self, username: str | None = None, password: str | None = None) -> str:
        username = username or os.environ.get("TENSOR_AGENT_USER")
        password = password or os.environ.get("TENSOR_AGENT_PASS")
        if not username or not password:
            raise RuntimeError(
                "no platform credentials: pass --username/--password or set "
                "TENSOR_AGENT_USER / TENSOR_AGENT_PASS"
            )
        result = self._request("POST", "/auth/login", {"username": username, "password": password})
        if result["status"] != 200:
            raise RuntimeError(f"login failed: {result['status']} {result['data']}")
        data = result["data"] or {}
        token = data.get("access_token") or data.get("token")
        if not token:
            raise RuntimeError(f"login response carried no token: {sorted(data)}")
        self.token = token
        return token

    # -- endpoints ---------------------------------------------------------
    def post_evaluation(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/tensor/outcome-evaluations", payload)

    def get_evaluation(self, evaluation_id: str) -> dict[str, Any]:
        return self._request("GET", f"/tensor/outcome-evaluations/{evaluation_id}")

    def list_evaluations(self, mission_id: int | None = None, limit: int = 20) -> dict[str, Any]:
        query = f"?limit={int(limit)}"
        if mission_id is not None:
            query += f"&mission_id={int(mission_id)}"
        return self._request("GET", f"/tensor/outcome-evaluations{query}")

    def get_capability_delta(self, mission_id: int) -> dict[str, Any]:
        return self._request("GET", f"/tensor/missions/{int(mission_id)}/capability-delta")

def build_achievement_evaluation_payload(
    report: Mapping[str, Any],
    *,
    mission_id: int,
    contributor: str,
    reviewer: str,
    grade: str,
    e_level: str,
    report_path: str | Path,
    repo: str | None = None,
    baseline_or_scope: str | None = None,
    boundary: str | None = None,
    evidence_chain: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a human-reviewed platform evaluation from an achievement report.

    The deterministic evaluator supplies evidence completeness only. It never
    chooses the S/E grade or reviewer: those are mandatory caller decisions.
    """
    if report.get("product_id") != "agent-achievement-evaluator":
        raise ValueError("report is not an Agent Achievement Evaluator report")
    if report.get("overall_status") != "passed":
        raise ValueError("only passed achievement reports can be submitted")
    if not reviewer.strip() or reviewer.strip().casefold() == contributor.strip().casefold():
        raise ValueError("reviewer must be present and differ from contributor")
    if grade not in {"S1", "S2", "S3", "S4", "S5", "S-N"}:
        raise ValueError("grade must be an explicit S1-S5 or S-N reviewer decision")
    if e_level not in {"E1", "E2", "E3", "E4"}:
        raise ValueError("e_level must be an explicit E1-E4 reviewer decision")
    if grade in {"S2", "S3", "S4", "S5", "S-N"} and not evidence_chain:
        raise ValueError("S2+ submissions require an explicit five-element evidence_chain")
    if grade in {"S2", "S4"} and not baseline_or_scope:
        raise ValueError(f"{grade} requires baseline_or_scope")
    if grade == "S5" and not baseline_or_scope:
        raise ValueError("S5 requires a novelty-search scope")

    summary = report.get("summary") or {}
    revision = str(summary.get("candidate_revision") or "")
    work_package = str(summary.get("work_package_id") or "")
    if not work_package or not revision:
        raise ValueError("achievement report lacks work-package or candidate revision")
    artifact_path = Path(report_path).resolve()
    if not artifact_path.is_file():
        raise ValueError(f"achievement report file does not exist: {artifact_path}")
    report_hash = _file_sha256(artifact_path)
    run_id = str(report.get("run_id") or "")
    if not run_id:
        raise ValueError("achievement report lacks run_id")

    grade_reason = (
        f"Agent Achievement Evaluator {report.get('product_version')} reports "
        f"{report.get('overall_status')} for work package {work_package}; "
        f"candidate revision {revision}; changed files={summary.get('changed_file_count')}; "
        f"code files={summary.get('code_file_count')}; acceptance criteria="
        f"{summary.get('acceptance_criteria_count')}; tests={summary.get('test_count')}. "
        "This records evidence completeness only, not independent functional or scientific correctness."
    )
    refs = [
        {"kind": EVIDENCE_KIND_RUN, "ref": run_id},
        {"kind": "commit", "ref": revision},
        {"kind": EVIDENCE_KIND_ARTIFACT, "ref": f"{artifact_path}#sha256={report_hash}"},
    ]
    for ref in report.get("evidence_refs") or []:
        refs.append({"kind": EVIDENCE_KIND_ARTIFACT, "ref": str(ref)})

    payload = {
        "artifact_id": f"agent-work-package:{work_package}@{revision}",
        "mission_id": int(mission_id),
        "contributor": contributor,
        "grade": grade,
        "e_level": e_level,
        "grade_reason": grade_reason,
        "evidence_refs": refs,
        "reviewer": reviewer,
        "reviewer_kind": "independent",
        "baseline_or_scope": baseline_or_scope,
        "boundary": boundary or (
            "Scope: revision-pinned work-package evidence completeness and linked test/CI records. "
            "Out of scope: independent execution, algorithmic correctness, scientific validity, "
            "security review, and production suitability."
        ),
        "repo": repo,
    }
    if evidence_chain:
        payload["evidence_chain"] = dict(evidence_chain)
    return payload
