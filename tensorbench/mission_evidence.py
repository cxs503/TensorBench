"""Build an auditable Agent Achievement evidence bundle from read-only snapshots.

This adapter deliberately does not fetch data, execute candidate code, infer
acceptance criteria, or assign achievement grades. It normalizes snapshots
collected from TensorPlatform and GitHub into the existing evaluator contract.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from .achievement import AchievementInputError, evaluate_work_package


def _sha256(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AchievementInputError(f"{name} must be an object")
    return value


def _status_to_test_state(value: Any) -> str:
    state = str(value or "").lower()
    if state in {"success", "successful", "passed"}:
        return "passed"
    if state in {"failure", "failed", "error", "timed_out", "action_required", "startup_failure"}:
        return "failed"
    if state in {"queued", "in_progress", "pending", "waiting", "requested"}:
        return "not_run"
    return "inconclusive"


def build_mission_evidence_bundle(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize mission + PR + CI snapshots into an evaluator input bundle.

    Required input keys:
      mission: TensorPlatform mission row (id, repo, goal, status, claimed_by)
      pull_request: GitHub PR object, including head.sha and changed_files/files
      checks: GitHub check-runs and/or commit statuses for the PR head
      acceptance_criteria: optional predeclared criterion objects

    When criteria are absent, a synthetic criterion is emitted without test IDs;
    the evaluator therefore returns inconclusive rather than treating CI success
    as proof that the mission goal was achieved.
    """
    root = _mapping(snapshot, "snapshot")
    mission = _mapping(root.get("mission"), "mission")
    pr = _mapping(root.get("pull_request"), "pull_request")
    checks_payload = root.get("checks") or {}
    checks_payload = _mapping(checks_payload, "checks")

    mission_id = mission.get("id")
    if mission_id is None:
        raise AchievementInputError("mission.id is required")
    repo = str(mission.get("repo") or "").strip()
    if not repo:
        raise AchievementInputError("mission.repo is required")
    goal = str(mission.get("goal") or "").strip()
    if not goal:
        raise AchievementInputError("mission.goal is required")

    head = pr.get("head") if isinstance(pr.get("head"), Mapping) else {}
    revision = str(head.get("sha") or pr.get("head_sha") or "").strip()
    if len(revision) not in {40, 64} or any(ch not in "0123456789abcdefABCDEF" for ch in revision):
        raise AchievementInputError("pull_request.head.sha must be an immutable Git SHA")

    pr_number = pr.get("number")
    pr_url = pr.get("html_url") or pr.get("url")
    files = pr.get("files") or pr.get("changed_files_list") or []
    if not isinstance(files, list):
        raise AchievementInputError("pull_request.files must be an array")
    changed_files = []
    for item in files:
        item = _mapping(item, "pull_request.files[]")
        filename = item.get("filename") or item.get("path")
        if not isinstance(filename, str) or not filename.strip():
            raise AchievementInputError("each changed file requires filename")
        changed_files.append({
            "path": filename,
            "status": item.get("status", "modified"),
            "additions": item.get("additions"),
            "deletions": item.get("deletions"),
            "changes": item.get("changes"),
        })

    artifacts: list[dict[str, Any]] = []
    pr_artifact = {
        "kind": "diff",
        "pr_number": pr_number,
        "pr_url": pr_url,
        "head_sha": revision,
        "base_sha": (pr.get("base") or {}).get("sha") if isinstance(pr.get("base"), Mapping) else None,
        "changed_files": changed_files,
        "merged": bool(pr.get("merged", False)),
        "state": pr.get("state"),
    }
    pr_ref = f"github://{repo}/pull/{pr_number or 'unknown'}@{revision}"
    artifacts.append({
        "artifact_ref": pr_ref,
        "kind": "diff",
        "sha256": _sha256(pr_artifact),
        "source_revision": revision,
    })

    check_runs = checks_payload.get("check_runs") or []
    statuses = checks_payload.get("statuses") or []
    if not isinstance(check_runs, list) or not isinstance(statuses, list):
        raise AchievementInputError("checks.check_runs and checks.statuses must be arrays")

    tests: list[dict[str, Any]] = []
    for index, raw in enumerate(check_runs):
        item = _mapping(raw, "checks.check_runs[]")
        check_sha = str(item.get("head_sha") or item.get("head_commit", {}).get("id") or "")
        conclusion = item.get("conclusion") or item.get("status")
        state = _status_to_test_state(conclusion)
        test_id = f"check-run-{item.get('id') or index}"
        ref = f"github://{repo}/check-runs/{item.get('id') or index}@{check_sha or 'unknown'}"
        artifacts.append({
            "artifact_ref": ref,
            "kind": "check_run",
            "sha256": _sha256(item),
            "source_revision": check_sha or "0" * 40,
        })
        tests.append({
            "test_id": test_id,
            "status": state,
            "commit_sha": check_sha,
            "artifact_refs": [ref],
            "name": item.get("name") or item.get("display_title"),
            "external_id": item.get("external_id"),
        })

    for index, raw in enumerate(statuses):
        item = _mapping(raw, "checks.statuses[]")
        status_sha = str(item.get("sha") or "")
        state = _status_to_test_state(item.get("state"))
        test_id = f"commit-status-{item.get('id') or index}"
        ref = f"github://{repo}/statuses/{item.get('id') or index}@{status_sha or 'unknown'}"
        artifacts.append({
            "artifact_ref": ref,
            "kind": "check_run",
            "sha256": _sha256(item),
            "source_revision": status_sha or "0" * 40,
        })
        tests.append({
            "test_id": test_id,
            "status": state,
            "commit_sha": status_sha,
            "artifact_refs": [ref],
            "name": item.get("context") or item.get("name"),
            "target_url": item.get("target_url"),
        })

    supplied_criteria = root.get("acceptance_criteria")
    if supplied_criteria is None:
        supplied_criteria = mission.get("acceptance_criteria")
    if supplied_criteria is None and isinstance(mission.get("result"), Mapping):
        supplied_criteria = mission["result"].get("acceptance_criteria")
    if supplied_criteria is None:
        # Deliberately not evaluable: mission goal text is not an acceptance test.
        supplied_criteria = [{
            "criterion_id": "mission-goal-not-formalized",
            "statement": goal,
            "required": True,
            "requires_code": True,
            "requires_test": True,
            "evidence_refs": [pr_ref],
            "test_ids": [],
        }]
    if not isinstance(supplied_criteria, list) or not supplied_criteria:
        raise AchievementInputError("acceptance_criteria must be a non-empty array when supplied")

    bundle = {
        "work_package_id": f"tensorplatform-mission-{mission_id}",
        "candidate_revision": revision,
        "acceptance_criteria": supplied_criteria,
        "changed_files": changed_files,
        "tests": tests,
        "artifacts": artifacts,
        "mission": {
            "mission_id": mission_id,
            "repo": repo,
            "status": mission.get("status"),
            "contributor": mission.get("claimed_by"),
            "goal": goal,
            "pull_request_number": pr_number,
            "pull_request_url": pr_url,
        },
        "collection": {
            "mode": "read_only_snapshot_normalization",
            "mission_sha256": _sha256(mission),
            "pull_request_sha256": _sha256(pr),
            "checks_sha256": _sha256(checks_payload),
            "acceptance_criteria_source": (
                "supplied" if root.get("acceptance_criteria") is not None
                or mission.get("acceptance_criteria") is not None
                or (isinstance(mission.get("result"), Mapping)
                    and mission["result"].get("acceptance_criteria") is not None)
                else "not_declared"
            ),
        },
    }
    return bundle


def evaluate_mission_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Build and evaluate a snapshot; non-succeeded missions cannot pass."""
    bundle = build_mission_evidence_bundle(snapshot)
    report = evaluate_work_package(bundle)
    mission_status = str(bundle["mission"].get("status") or "").lower()
    if mission_status != "succeeded":
        report["checks"].append({
            "check_id": "mission.status",
            "version": "0.1.0",
            "method": "deterministic_rule",
            "state": "inconclusive",
            "required": True,
            "details": f"Mission status is {mission_status or 'missing'}, not succeeded.",
        })
        report["overall_status"] = "failed" if report["overall_status"] == "failed" else "inconclusive"
    report["summary"]["mission_id"] = bundle["mission"]["mission_id"]
    report["summary"]["mission_status"] = mission_status or None
    report["summary"]["pull_request_number"] = bundle["mission"]["pull_request_number"]
    report["summary"]["acceptance_criteria_source"] = bundle["collection"]["acceptance_criteria_source"]
    report["provenance"]["collection"] = bundle["collection"]
    return {"bundle": bundle, "report": report}
