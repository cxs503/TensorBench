"""A small, explicit local runner for reproducible benchmark commands.

The runner intentionally uses argv execution (never a shell), records failures,
and writes one JSON result plus stdout/stderr artifacts per run.

Schema version 1.1.0 adds three things that make a run usable as *evidence*
rather than just a log:

* repeated execution (``spec.protocol.repetitions``) with per-repetition samples
  aggregated by the declared method;
* measurement extraction from a workload-written metrics file, constrained by the
  declared metric contracts (``spec.metrics``);
* acceptance-criteria evaluation and a deterministic score object, so a benchmark
  can report ``passed`` / ``failed`` / ``not_evaluated`` on its own terms.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import shlex
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .criteria import (
    AGGREGATIONS,
    aggregate,
    canonical_sha256,
    compute_score,
    evaluate_criteria,
    metric_contracts,
)

SCHEMA_VERSION = "1.1.0"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
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
        dirty = (
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=cwd,
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout.strip()
            != ""
        )
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

    protocol = spec.get("protocol") or {}
    if not isinstance(protocol, dict):
        raise ValueError("spec.protocol must be an object")
    repetitions = protocol.get("repetitions", 1)
    if isinstance(repetitions, bool) or not isinstance(repetitions, int) or repetitions < 1:
        raise ValueError("spec.protocol.repetitions must be a positive integer")

    output = spec["workload"].get("output") or {}
    if output and not isinstance(output, dict):
        raise ValueError("spec.workload.output must be an object")
    metrics_file = output.get("metrics_file")
    if metrics_file is not None and (not isinstance(metrics_file, str) or not metrics_file):
        raise ValueError("spec.workload.output.metrics_file must be a non-empty string")

    for name, contract in metric_contracts(spec).items():
        method = contract.get("aggregation", "median" if repetitions > 1 else "single_run")
        if method not in AGGREGATIONS:
            raise ValueError(
                f"spec.metrics[{name!r}].aggregation must be one of {list(AGGREGATIONS)}"
            )


def _read_metrics_file(path: Path) -> dict[str, float]:
    """Read a flat ``{name: number}`` or ``{"metrics": {...}}`` JSON payload."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read metrics file {path}: {exc}") from exc
    if isinstance(payload, dict) and isinstance(payload.get("metrics"), dict):
        payload = payload["metrics"]
    if not isinstance(payload, dict):
        raise ValueError(f"metrics file {path} must contain an object")
    out: dict[str, float] = {}
    for key, value in payload.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"metrics file {path}: {key!r} must be a number")
        out[str(key)] = float(value)
    if not out:
        raise ValueError(f"metrics file {path} contains no metrics")
    return out


def _run_once(
    command: list[str],
    cwd: Path,
    env: dict[str, str],
    timeout: float,
    stdout_path: Path,
    stderr_path: Path,
) -> dict[str, Any]:
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
            env=env,
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
    stdout_path.write_bytes(stdout)
    stderr_path.write_bytes(stderr)
    return {
        "status": status,
        "exit_code": exit_code,
        "duration_seconds": duration,
        "started_at": started_at,
        "ended_at": _utc_now(),
        "notes": failure_note or "",
    }


def run_benchmark(
    spec: dict[str, Any],
    output_dir: str | Path,
    *,
    implementation_project: str | None = None,
    implementation_revision: str | None = None,
    repetitions: int | None = None,
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
    protocol = spec.get("protocol") or {}
    repeats = int(repetitions or protocol.get("repetitions", 1))
    warmups = int(protocol.get("warmup", 0))
    if repeats < 1:
        raise ValueError("repetitions must be >= 1")

    metrics_file = (workload.get("output") or {}).get("metrics_file")
    declared = metric_contracts(spec)

    run_id = f"tb-{uuid.uuid4().hex}"
    result_path = output / f"{run_id}.result.json"
    env = {**os.environ, **execution_config.get("env", {})}

    revision, dirty = _git_revision(cwd)
    samples: dict[str, list[float]] = {}
    repetitions_log: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []
    overall_status = "success"
    notes: list[str] = []

    for index in range(warmups + repeats):
        warmup_only = index < warmups
        measured_index = index - warmups
        suffix = f".warm{index + 1}" if warmup_only else (f".r{measured_index + 1}" if repeats > 1 else "")
        stdout_path = output / f"{run_id}{suffix}.stdout.log"
        stderr_path = output / f"{run_id}{suffix}.stderr.log"
        if metrics_file:
            produced = Path(metrics_file)
            produced = produced if produced.is_absolute() else cwd / produced
            produced.unlink(missing_ok=True)  # never reuse a stale measurement

        record = _run_once(command, cwd, env, timeout, stdout_path, stderr_path)
        if warmup_only:
            if record["status"] != "success":
                overall_status = record["status"]
                notes.append(f"warm-up {index + 1}: {record['status']} {record['notes']}".strip())
            continue
        record["repetition"] = measured_index + 1
        samples.setdefault("wall_time", []).append(record["duration_seconds"])

        if record["status"] == "success" and metrics_file:
            produced = Path(metrics_file)
            produced = produced if produced.is_absolute() else cwd / produced
            try:
                measured = _read_metrics_file(produced)
            except ValueError as exc:
                record["status"] = "invalid"
                record["notes"] = (record["notes"] + "; " if record["notes"] else "") + str(exc)
                measured = {}
            for name, value in measured.items():
                samples.setdefault(name, []).append(value)
                if name not in declared:
                    notes.append(f"metric {name!r} was measured but not declared in spec.metrics")
        elif record["status"] == "success" and not metrics_file:
            notes.append("workload declared no metrics_file; only wall_time is recorded")

        repetitions_log.append(record)
        if record["status"] != "success" and overall_status == "success":
            overall_status = record["status"]
            if record["notes"]:
                notes.append(f"repetition {index + 1}: {record['notes']}")

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

    metrics: list[dict[str, Any]] = []
    for name, values in samples.items():
        contract = declared.get(name, {})
        method = contract.get("aggregation", "median" if repeats > 1 else "single_run")
        if repeats == 1 and method == "median":
            method = "single_run"
        entry: dict[str, Any] = {
            "name": name,
            "value": aggregate(values, method),
            "unit": str(contract.get("unit", "seconds" if name == "wall_time" else "unspecified")),
            "kind": str(contract.get("kind", "measured")),
            "aggregation": method,
            "samples": [float(v) for v in values],
        }
        if contract.get("better"):
            entry["better"] = contract["better"]
        entry["method"] = str(
            contract.get(
                "method",
                "time.perf_counter around subprocess execution"
                if name == "wall_time"
                else "workload-emitted metrics file",
            )
        )
        metrics.append(entry)
    metrics.sort(key=lambda m: (m["name"] != "wall_time", m["name"]))

    flat_metrics = {m["name"]: m["value"] for m in metrics}
    acceptance = evaluate_criteria(spec, flat_metrics)
    score = compute_score(spec, acceptance, flat_metrics)

    correctness = {
        "passed": "passed",
        "failed": "failed",
        "not_evaluated": "not_checked",
    }[acceptance["status"]]

    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "benchmark": {
            "benchmark_id": spec["benchmark"]["benchmark_id"],
            "version": spec["benchmark"]["version"],
        },
        "implementation": {
            "project": implementation_project
            or spec.get("implementation", {}).get("project", "unknown"),
            "revision": implementation_revision
            or spec.get("implementation", {}).get("revision", revision),
        },
        "workload": {
            "workload_id": workload["workload_id"],
            "version": workload["version"],
            "dataset_refs": workload.get("dataset_refs", []),
            "configuration": workload.get("configuration", {}),
            "repetitions": repeats,
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
            "status": overall_status,
            "started_at": repetitions_log[0]["started_at"],
            "ended_at": repetitions_log[-1]["ended_at"],
            "duration_seconds": sum(r["duration_seconds"] for r in repetitions_log),
            "exit_code": repetitions_log[-1]["exit_code"],
            "command": shlex.join(command),
            "timeout_seconds": timeout,
            "notes": "; ".join(notes),
        },
        "metrics": metrics,
        "acceptance": acceptance,
        "score": score,
        "artifacts": artifacts,
        "validation": {
            "schema": "not_checked",
            "execution": "passed" if overall_status == "success" else "failed",
            "correctness": correctness,
            "reproducibility": "not_checked",
            "comparability": "not_checked",
            "details": (
                "Execution status is not a scientific correctness or reproducibility verdict. "
                "Correctness reflects only the declared acceptance criteria of this benchmark."
            ),
        },
        "provenance": {
            "spec_sha256": hashlib.sha256(
                json.dumps(spec, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
                    "utf-8"
                )
            ).hexdigest(),
            "configuration_sha256": canonical_sha256(workload.get("configuration", {})),
            "criteria_sha256": canonical_sha256((spec.get("acceptance") or {}).get("criteria", [])),
            "repetitions": [
                {k: r[k] for k in ("repetition", "status", "exit_code", "duration_seconds")}
                for r in repetitions_log
            ],
        },
    }

    if dirty is not None:
        result["implementation"]["dirty"] = dirty

    result_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return result