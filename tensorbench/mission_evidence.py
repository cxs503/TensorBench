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


def _looks_like_test_check(item: Mapping[str, Any]) -> bool:
    label = " ".join(str(item.get(key) or "") for key in ("name", "context", "display_title", "workflow_name")).lower()
    return any(token in label for token in ("test", "pytest", "unittest", "tox", "coverage", "nose"))


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
        if _looks_like_test_check(item):
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
        if _looks_like_test_check(item):
            tests.append({
                "test_id": test_id,
                "status": state,
                "commit_sha": status_sha,
                "artifact_refs": [ref],
                "name": item.get("context") or item.get("name"),
                "target_url": item.get("target_url"),
            })

    collection_metadata = root.get("collection_metadata") or {}
    if not isinstance(collection_metadata, Mapping):
        raise AchievementInputError("collection_metadata must be an object")

    # The mission row is authoritative even when its criteria list is empty.
    # Never replace an explicit empty contract with agent-authored result data.
    if "acceptance_criteria" in mission:
        supplied_criteria = mission.get("acceptance_criteria")
        criteria_payload_source = "mission_snapshot"
    elif "acceptance_criteria" in root:
        supplied_criteria = root.get("acceptance_criteria")
        criteria_payload_source = str(collection_metadata.get("acceptance_criteria_payload_source") or "snapshot_supplied")
    else:
        legacy_result = mission.get("result")
        legacy_evidence = legacy_result.get("evidence") if isinstance(legacy_result, Mapping) else None
        supplied_criteria = (
            legacy_evidence.get("acceptance_criteria")
            if isinstance(legacy_evidence, Mapping) else None
        )
        if supplied_criteria is None and isinstance(legacy_result, Mapping):
            supplied_criteria = legacy_result.get("acceptance_criteria")
        criteria_payload_source = "legacy_completion_evidence" if supplied_criteria is not None else "not_declared"

    if supplied_criteria is not None and not isinstance(supplied_criteria, list):
        raise AchievementInputError("acceptance_criteria must be an array")
    if supplied_criteria is None:
        supplied_criteria = []

    freeze_source = str(
        mission.get("acceptance_criteria_freeze_source")
        or collection_metadata.get("acceptance_criteria_source")
        or "legacy_unfrozen"
    )
    expected_criteria_sha256 = (
        mission.get("acceptance_criteria_sha256")
        or collection_metadata.get("acceptance_criteria_sha256")
    )
    observed_criteria_sha256 = _sha256(supplied_criteria)
    if freeze_source in {"mission_created", "legacy_start"} and expected_criteria_sha256:
        criteria_integrity = (
            "verified" if observed_criteria_sha256 == str(expected_criteria_sha256).strip()
            else "mismatch"
        )
    else:
        criteria_integrity = "inconclusive"

    if supplied_criteria:
        criteria_status = (
            "declared" if freeze_source == "mission_created" and criteria_integrity == "verified"
            else "legacy_frozen_at_start" if freeze_source == "legacy_start" and criteria_integrity == "verified"
            else "legacy_unverified"
        )
    else:
        criteria_status = "not_declared"
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
            "acceptance_criteria_source": criteria_status,
            "acceptance_criteria_payload_source": criteria_payload_source,
            "acceptance_criteria_freeze_source": freeze_source,
            "acceptance_criteria_sha256": expected_criteria_sha256,
            "acceptance_criteria_observed_sha256": observed_criteria_sha256,
            "acceptance_criteria_integrity": criteria_integrity,
            "collector_metadata": collection_metadata,
        },
    }
    return bundle


def evaluate_mission_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate completed candidates; owner approval may still be pending."""
    bundle = build_mission_evidence_bundle(snapshot)
    report = evaluate_work_package(bundle)
    mission_status = str(bundle["mission"].get("status") or "").lower()
    if mission_status not in {"succeeded", "awaiting_acceptance"}:
        report["checks"].append({
            "check_id": "mission.status",
            "version": "0.1.0",
            "method": "deterministic_rule",
            "state": "inconclusive",
            "required": True,
            "details": (
                f"Mission status is {mission_status or 'missing'}; expected a completed "
                "candidate (awaiting_acceptance or succeeded)."
            ),
        })
        report["overall_status"] = "failed" if report["overall_status"] == "failed" else "inconclusive"
    report["summary"]["mission_id"] = bundle["mission"]["mission_id"]
    report["summary"]["mission_status"] = mission_status or None
    report["summary"]["pull_request_number"] = bundle["mission"]["pull_request_number"]
    criteria_status = bundle["collection"]["acceptance_criteria_source"]
    criteria_integrity = bundle["collection"]["acceptance_criteria_integrity"]
    if criteria_integrity == "mismatch":
        criteria_state = "failed"
        report["overall_status"] = "failed"
    elif criteria_status != "declared" or criteria_integrity != "verified":
        criteria_state = "inconclusive"
        if report["overall_status"] != "failed":
            report["overall_status"] = "inconclusive"
    else:
        criteria_state = "passed"
    report["checks"].append({
        "check_id": "mission.acceptance_criteria_integrity",
        "version": "1.0.0",
        "method": "deterministic_rule",
        "state": criteria_state,
        "required": True,
        "details": (
            f"criteria status={criteria_status}; integrity={criteria_integrity}; "
            f"freeze_source={bundle['collection']['acceptance_criteria_freeze_source']}"
        ),
    })
    report["summary"]["acceptance_criteria_source"] = criteria_status
    report["summary"]["acceptance_criteria_integrity"] = criteria_integrity
    report["provenance"]["collection"] = bundle["collection"]
    return {"bundle": bundle, "report": report}
