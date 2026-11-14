"""Evidence-completeness evaluator for agent work packages.

This module checks whether predeclared acceptance criteria are backed by
revision-pinned code/test/artifact evidence. It does not execute untrusted code
or independently prove algorithmic/scientific correctness.
"""
from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any


class AchievementInputError(ValueError):
    """Invalid agent achievement evidence bundle."""


_DOC_SUFFIXES = {".md", ".rst", ".txt", ".adoc"}


def _digest(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _is_code_path(path: str) -> bool:
    normalized = path.replace("\\", "/").lower()
    if normalized.startswith(("docs/", "documentation/")):
        return False
    suffix = Path(normalized).suffix
    return suffix not in _DOC_SUFFIXES and suffix not in {".png", ".jpg", ".jpeg", ".svg", ".pdf"}


def evaluate_work_package(bundle: Any) -> dict[str, Any]:
    """Evaluate a revision-pinned work-package evidence bundle."""
    if not isinstance(bundle, dict):
        raise AchievementInputError("input root must be a JSON object")
    for key in ("work_package_id", "candidate_revision", "acceptance_criteria", "changed_files", "tests", "artifacts"):
        if key not in bundle:
            raise AchievementInputError(f"{key} is required")
    criteria, changed_files, tests, artifacts = (
        bundle["acceptance_criteria"], bundle["changed_files"], bundle["tests"], bundle["artifacts"]
    )
    if not isinstance(criteria, list) or not criteria:
        raise AchievementInputError("acceptance_criteria must be a non-empty array")
    if not all(isinstance(items, list) for items in (changed_files, tests, artifacts)):
        raise AchievementInputError("changed_files, tests and artifacts must be arrays")
    revision = str(bundle["candidate_revision"]).strip()
    if not re.fullmatch(r"(?:[a-fA-F0-9]{40}|[a-fA-F0-9]{64})", revision):
        raise AchievementInputError("candidate_revision must be a 40- or 64-character Git SHA")
    if not isinstance(bundle["work_package_id"], str) or not bundle["work_package_id"].strip():
        raise AchievementInputError("work_package_id must be a non-empty string")
    criterion_ids: set[str] = set()
    for criterion in criteria:
        if not isinstance(criterion, dict) or not criterion.get("criterion_id"):
            raise AchievementInputError("each acceptance criterion requires criterion_id")
        criterion_id = str(criterion["criterion_id"])
        if criterion_id in criterion_ids:
            raise AchievementInputError(f"duplicate criterion_id: {criterion_id}")
        criterion_ids.add(criterion_id)
    for changed_file in changed_files:
        if not isinstance(changed_file, dict) or not isinstance(changed_file.get("path"), str) or not changed_file["path"].strip():
            raise AchievementInputError("each changed_file requires a non-empty path")

    artifact_map: dict[str, dict[str, Any]] = {}
    artifact_revision_mismatch: set[str] = set()
    for artifact in artifacts:
        if not isinstance(artifact, dict) or not artifact.get("artifact_ref"):
            raise AchievementInputError("each artifact requires artifact_ref")
        if not isinstance(artifact.get("kind"), str) or not artifact["kind"].strip():
            raise AchievementInputError(f"artifact {artifact['artifact_ref']} requires a non-empty kind")
        ref = str(artifact["artifact_ref"])
        if ref in artifact_map:
            raise AchievementInputError(f"duplicate artifact_ref: {ref}")
        digest = str(artifact.get("sha256") or "")
        if not re.fullmatch(r"[a-fA-F0-9]{64}", digest):
            raise AchievementInputError(f"artifact {ref} requires a valid SHA-256")
        artifact_map[ref] = artifact
        if artifact.get("source_revision") != revision:
            artifact_revision_mismatch.add(ref)

    test_map: dict[str, dict[str, Any]] = {}
    for test in tests:
        if not isinstance(test, dict) or not test.get("test_id"):
            raise AchievementInputError("each test requires test_id")
        test_id = str(test["test_id"])
        if test_id in test_map:
            raise AchievementInputError(f"duplicate test_id: {test_id}")
        if test.get("status") not in {"passed", "failed", "not_run", "inconclusive"}:
            raise AchievementInputError(f"test {test_id} has invalid status")
        test_map[test_id] = test

    evidence_refs = sorted(artifact_map)
    checks: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []

    def record(check_id: str, state: str, details: str, *, required: bool = True,
               severity: str = "medium", refs: list[str] | None = None) -> None:
        checks.append({
            "check_id": check_id,
            "version": "0.1.0",
            "method": "deterministic_rule",
            "state": state,
            "required": required,
            "details": details,
        })
        if state in {"failed", "inconclusive"}:
            findings.append({
                "finding_id": f"{check_id}:{len(findings) + 1}",
                "check_id": check_id,
                "status": "confirmed" if state == "failed" else "inconclusive",
                "severity": severity if state == "failed" else "info",
                "summary": details,
                "rationale": details,
                "evidence_refs": refs or [],
                "review_state": "unreviewed",
                "limitations": ["Evidence completeness is not proof of functional or domain correctness."],
            })

    code_files = [
        item for item in changed_files
        if isinstance(item, dict) and item.get("path") and _is_code_path(str(item["path"]))
    ]
    code_required = any(
        isinstance(item, dict) and item.get("requires_code", False) for item in criteria
    )
    if code_files:
        record("candidate.code_delta", "passed",
               f"{len(code_files)} non-documentation changed file(s) are recorded.")
    elif code_required:
        record("candidate.code_delta", "failed",
               "No code/configuration changes are recorded; candidate appears documentation-only or empty.",
               severity="high")
    else:
        record("candidate.code_delta", "not_applicable",
               "No acceptance criterion requires implementation code.")

    for criterion in criteria:
        cid = str(criterion["criterion_id"])
        required = bool(criterion.get("required", True))
        refs = criterion.get("evidence_refs") or []
        missing_refs = [ref for ref in refs if ref not in artifact_map]
        stale_refs = [ref for ref in refs if ref in artifact_revision_mismatch]
        if not refs:
            record(f"criterion.{cid}.evidence", "inconclusive",
                   f"Criterion {cid} has no linked evidence artifact.", required=required)
        elif missing_refs:
            record(f"criterion.{cid}.evidence", "inconclusive",
                   f"Criterion {cid} references missing artifacts: {missing_refs}.",
                   required=required, refs=[ref for ref in refs if ref in artifact_map])
        elif stale_refs:
            record(f"criterion.{cid}.evidence", "inconclusive",
                   f"Criterion {cid} references artifacts not pinned to candidate revision {revision}: {stale_refs}.",
                   required=required, refs=refs)
        else:
            record(f"criterion.{cid}.evidence", "passed",
                   f"Criterion {cid} resolves to {len(refs)} artifact(s).", required=required, refs=refs)

        if criterion.get("requires_code", False) and not code_files:
            record(f"criterion.{cid}.implementation", "failed",
                   f"Criterion {cid} requires implementation code, but no code delta is recorded.",
                   required=required, severity="high")

        if criterion.get("requires_test", True):
            test_ids = criterion.get("test_ids") or []
            if not test_ids:
                record(f"criterion.{cid}.tests", "inconclusive",
                       f"Criterion {cid} requires test evidence but has no linked test_ids.",
                       required=required, refs=refs)
                continue
            for test_id in test_ids:
                test = test_map.get(str(test_id))
                if test is None:
                    record(f"criterion.{cid}.test.{test_id}", "inconclusive",
                           f"Criterion {cid} references missing test {test_id!r}.",
                           required=required, refs=refs)
                    continue
                test_refs = test.get("artifact_refs") or []
                unresolved_refs = [ref for ref in test_refs if ref not in artifact_map]
                if test.get("commit_sha") != revision:
                    record(f"criterion.{cid}.test.{test_id}", "inconclusive",
                           f"Test {test_id} is not pinned to candidate revision {revision}.",
                           required=required, refs=[ref for ref in test_refs if ref in artifact_map])
                elif test.get("status") == "failed":
                    record(f"criterion.{cid}.test.{test_id}", "failed",
                           f"Required test {test_id} failed.", required=required,
                           severity="high", refs=[ref for ref in test_refs if ref in artifact_map])
                elif test.get("status") != "passed":
                    record(f"criterion.{cid}.test.{test_id}", "inconclusive",
                           f"Required test {test_id} status is {test.get('status')!r}.",
                           required=required, refs=[ref for ref in test_refs if ref in artifact_map])
                elif not test_refs or unresolved_refs:
                    record(f"criterion.{cid}.test.{test_id}", "inconclusive",
                           f"Test {test_id} lacks resolvable run-log/artifact evidence.",
                           required=required, refs=[ref for ref in test_refs if ref in artifact_map])
                elif any(artifact_map[ref].get("kind") not in {
                    "test_log", "workflow_log", "check_run", "test_report", "ci_run"
                } for ref in test_refs):
                    record(f"criterion.{cid}.test.{test_id}", "inconclusive",
                           f"Test {test_id} references artifacts that are not identified as test/CI evidence.",
                           required=required, refs=test_refs)
                else:
                    record(f"criterion.{cid}.test.{test_id}", "passed",
                           f"Test {test_id} passed on the exact candidate revision.",
                           required=required, refs=test_refs)

    required_failed = any(c["required"] and c["state"] == "failed" for c in checks)
    required_unresolved = any(c["required"] and c["state"] in {"inconclusive", "not_measured"} for c in checks)
    overall = "failed" if required_failed else "inconclusive" if required_unresolved else "passed"
    digest = _digest(bundle)
    now = datetime.now(UTC).replace(microsecond=0).isoformat()
    return {
        "schema_version": "0.1.0",
        "product_id": "agent-achievement-evaluator",
        "product_version": "0.1.0",
        "run_id": f"achievement-{digest[:16]}",
        "created_at": now,
        "input_refs": [str(bundle.get("work_package_id"))],
        "input_fingerprints": {"bundle_sha256": digest},
        "checks": checks,
        "findings": findings,
        "evidence_refs": evidence_refs,
        "overall_status": overall,
        "summary": {
            "work_package_id": bundle["work_package_id"],
            "candidate_revision": revision,
            "changed_file_count": len(changed_files),
            "code_file_count": len(code_files),
            "acceptance_criteria_count": len(criteria),
            "test_count": len(tests),
            "scope": "revision-pinned evidence completeness; not independent functional or domain correctness",
        },
        "provenance": {
            "input_fingerprints": {"bundle_sha256": digest},
            "candidate_revision": revision,
        },
    }


def evaluate_file(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        bundle = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AchievementInputError(f"cannot read work-package bundle {source}: {exc}") from exc
    return evaluate_work_package(bundle)
