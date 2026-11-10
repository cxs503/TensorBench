"""A small, explicit local runner for reproducible benchmark commands.

The runner intentionally uses argv execution (never a shell), records failures,
and writes one JSON result plus stdout/stderr artifacts per run.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import shlex
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_revision(cwd: Path) -> tuple[str, bool | None]:
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip() != ""
        return revision, dirty
    except (OSError, subprocess.SubprocessError):
        return "unknown", None


def _validate_spec(spec: dict[str, Any]) -> None:
    for section, keys in {
        "benchmark": ("benchmark_id", "version"),
        "workload": ("workload_id", "version", "command"),
    }.items():
        value = spec.get(section)
        if not isinstance(value, dict):
            raise ValueError(f"spec.{section} must be an object")
        for key in keys:
            if key not in value:
                raise ValueError(f"spec.{section}.{key} is required")
    command = spec["workload"]["command"]
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(part, str) and part for part in command)
    ):
        raise ValueError("spec.workload.command must be a non-empty string array")
    timeout = spec.get("execution", {}).get("timeout_seconds", 300)
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ValueError("spec.execution.timeout_seconds must be positive")


def run_benchmark(
    spec: dict[str, Any],
    output_dir: str | Path,
    *,
    implementation_project: str | None = None,
    implementation_revision: str | None = None,
) -> dict[str, Any]:
    """Execute one benchmark specification and persist its evidence record."""
    _validate_spec(spec)

    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)

    workload = spec["workload"]
    execution_config = spec.get("execution", {})
    command = workload["command"]
    cwd = Path(workload.get("cwd", ".")).resolve()
    if not cwd.is_dir():
        raise ValueError(f"workload cwd does not exist or is not a directory: {cwd}")

    timeout = float(execution_config.get("timeout_seconds", 300))
    run_id = f"tb-{uuid.uuid4().hex}"
    stdout_path = output / f"{run_id}.stdout.log"
    stderr_path = output / f"{run_id}.stderr.log"
    result_path = output / f"{run_id}.result.json"

    revision, dirty = _git_revision(cwd)
    started_at = _utc_now()
    started = time.perf_counter()
    exit_code: int | None = None
    status = "failed"
    stdout = b""
    stderr = b""
    failure_note: str | None = None

    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env={**os.environ, **execution_config.get("env", {})},
            capture_output=True,
            timeout=timeout,
            check=False,
            shell=False,
        )
        stdout = completed.stdout
        stderr = completed.stderr
        exit_code = completed.returncode
        status = "success" if exit_code == 0 else "failed"
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or b""
        stderr = exc.stderr or b""
        status = "timeout"
        failure_note = f"Command exceeded timeout of {timeout} seconds"
    except OSError as exc:
        status = "failed"
        failure_note = f"Unable to start command: {exc}"

    duration = time.perf_counter() - started
    ended_at = _utc_now()
    stdout_path.write_bytes(stdout)
    stderr_path.write_bytes(stderr)

    artifacts = []
    for path in (stdout_path, stderr_path):
        artifacts.append(
            {
                "name": path.name,
                "uri": path.name,
                "media_type": "text/plain",
                "sha256": _sha256(path),
                "size_bytes": path.stat().st_size,
            }
        )

    result: dict[str, Any] = {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "benchmark": {
            "benchmark_id": spec["benchmark"]["benchmark_id"],
            "version": spec["benchmark"]["version"],
        },
        "implementation": {
            "project": implementation_project or spec.get("implementation", {}).get("project", "unknown"),
            "revision": implementation_revision or spec.get("implementation", {}).get("revision", revision),
            "dirty": dirty,
        },
        "workload": {
            "workload_id": workload["workload_id"],
            "version": workload["version"],
            "dataset_refs": workload.get("dataset_refs", []),
            "configuration": workload.get("configuration", {}),
        },
        "environment": {
            "os": platform.platform(),
            "architecture": platform.machine(),
            "cpu": platform.processor() or "unknown",
            "cpu_cores": os.cpu_count() or 1,
            "runtime": {"python": platform.python_version()},
            "precision": workload.get("precision", "not_declared"),
        },
        "execution": {
            "status": status,
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_seconds": duration,
            "exit_code": exit_code,
            "command": shlex.join(command),
            "timeout_seconds": timeout,
            "notes": failure_note or "",
        },
        "metrics": [
            {
                "name": "wall_time",
                "value": duration,
                "unit": "seconds",
                "kind": "measured",
                "aggregation": "single_run",
                "better": "lower",
                "method": "time.perf_counter around subprocess execution",
            }
        ],
        "artifacts": artifacts,
        "validation": {
            "schema": "not_checked",
            "execution": "passed" if status == "success" else "failed",
            "correctness": "not_checked",
            "reproducibility": "not_checked",
            "comparability": "not_checked",
            "details": "Execution status is not a scientific correctness or reproducibility verdict.",
        },
    }

    result_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return result
