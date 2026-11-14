"""Bind retained isolated-run logs to an Agent Achievement evidence bundle."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .achievement import AchievementInputError


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def attach_isolated_run(
    bundle: dict[str, Any],
    report: dict[str, Any],
    *,
    report_path: str | Path,
    test_id: str,
    criterion_ids: list[str],
) -> dict[str, Any]:
    """Verify log fingerprints and attach the run to explicitly selected criteria."""
    if not isinstance(bundle, dict) or not isinstance(report, dict):
        raise AchievementInputError("bundle and isolated run report must be JSON objects")
    revision = str(bundle.get("candidate_revision") or "")
    if report.get("candidate_revision") != revision:
        raise AchievementInputError("isolated run revision does not match evidence bundle")
    if report.get("status") not in {"passed", "failed", "timed_out"}:
        raise AchievementInputError("isolated run report has an unsupported status")
    if not test_id.strip() or not criterion_ids:
        raise AchievementInputError("test_id and at least one criterion_id are required")

    criteria = bundle.get("acceptance_criteria")
    artifacts = bundle.setdefault("artifacts", [])
    tests = bundle.setdefault("tests", [])
    if not isinstance(criteria, list) or not isinstance(artifacts, list) or not isinstance(tests, list):
        raise AchievementInputError("bundle criteria, artifacts and tests must be arrays")
    criterion_map = {
        str(item.get("criterion_id")): item
        for item in criteria if isinstance(item, dict) and item.get("criterion_id")
    }
    if len(criterion_map) != len(criteria):
        raise AchievementInputError("bundle contains invalid or duplicate criterion IDs")
    missing = [cid for cid in criterion_ids if cid not in criterion_map]
    if missing:
        raise AchievementInputError(f"unknown criterion IDs: {missing}")
    if any(isinstance(item, dict) and item.get("test_id") == test_id for item in tests):
        raise AchievementInputError(f"test_id already exists: {test_id}")

    report_file = Path(report_path).resolve(strict=True)
    try:
        disk_report = json.loads(report_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AchievementInputError(f"cannot read isolated report file: {exc}") from exc
    if disk_report != report:
        raise AchievementInputError("isolated report object does not match the report file")
    report_hash = _file_sha256(report_file)
    run_ref = f"tensorbench://isolated-run/{revision}/{test_id}/report"
    new_artifacts = [{
        "artifact_ref": run_ref,
        "kind": "isolated_execution_report",
        "sha256": report_hash,
        "source_revision": revision,
        "path": str(report_file),
    }]
    log_refs: list[str] = []
    for stream_name in ("stdout", "stderr"):
        stream = report.get(stream_name)
        if not isinstance(stream, dict) or not isinstance(stream.get("path"), str):
            raise AchievementInputError(f"isolated report is missing {stream_name} log path")
        path = Path(stream["path"]).resolve(strict=True)
        digest = _file_sha256(path)
        if digest != stream.get("sha256"):
            raise AchievementInputError(f"{stream_name} log SHA-256 mismatch")
        ref = f"tensorbench://isolated-run/{revision}/{test_id}/{stream_name}"
        log_refs.append(ref)
        new_artifacts.append({
            "artifact_ref": ref,
            "kind": f"isolated_{stream_name}_log",
            "sha256": digest,
            "source_revision": revision,
            "path": str(path),
        })

    existing_refs = {str(item.get("artifact_ref")) for item in artifacts if isinstance(item, dict)}
    if existing_refs.intersection(item["artifact_ref"] for item in new_artifacts):
        raise AchievementInputError("isolated run artifact reference already exists")
    artifacts.extend(new_artifacts)
    state = {"passed": "passed", "failed": "failed", "timed_out": "not_run"}[report["status"]]
    tests.append({
        "test_id": test_id,
        "status": state,
        "commit_sha": revision,
        "artifact_refs": [run_ref, *log_refs],
        "name": "Independent isolated test re-execution",
        "command": report.get("command"),
        "runner_image": report.get("image"),
        "runner_method": report.get("method"),
        "exit_code": report.get("exit_code"),
    })
    for criterion_id in criterion_ids:
        ids = criterion_map[criterion_id].setdefault("test_ids", [])
        if not isinstance(ids, list):
            raise AchievementInputError(f"criterion {criterion_id} test_ids must be an array")
        if test_id not in ids:
            ids.append(test_id)

    collection = bundle.setdefault("collection", {})
    if not isinstance(collection, dict):
        raise AchievementInputError("bundle collection metadata must be an object")
    runs = collection.setdefault("isolated_runs", [])
    if not isinstance(runs, list):
        raise AchievementInputError("bundle isolated_runs metadata must be an array")
    runs.append({
        "test_id": test_id,
        "report_ref": run_ref,
        "report_sha256": report_hash,
        "candidate_revision": revision,
        "status": report["status"],
    })
    return bundle


def attach_isolated_run_files(
    bundle_path: str | Path,
    report_path: str | Path,
    *,
    test_id: str,
    criterion_ids: list[str],
    output_path: str | Path,
) -> dict[str, Any]:
    bundle = json.loads(Path(bundle_path).read_text(encoding="utf-8"))
    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    updated = attach_isolated_run(
        bundle, report, report_path=report_path,
        test_id=test_id, criterion_ids=criterion_ids,
    )
    Path(output_path).write_text(
        json.dumps(updated, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return updated
