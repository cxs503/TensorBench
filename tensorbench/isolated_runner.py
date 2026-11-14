"""Constrained OCI execution for independent test re-verification.

Defense-in-depth only. Prefer rootless Podman on a dedicated runner host.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Sequence


class IsolatedRunError(ValueError):
    """Invalid isolated execution request."""


_IMAGE_RE = re.compile(r"^(?:[^\s@]+@sha256:[a-f0-9]{64}|sha256:[a-f0-9]{64})$")
_CONTAINER_ID_RE = re.compile(r"^[a-f0-9]{64}$")
_SHA_RE = re.compile(r"^(?:[a-fA-F0-9]{40}|[a-fA-F0-9]{64})$")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_value(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], check=False, capture_output=True,
        text=True, timeout=15,
        env={
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
        },
    )
    if result.returncode:
        raise IsolatedRunError(f"git {' '.join(args)} failed: {result.stderr[-1000:]}")
    return result.stdout.strip()


def run_isolated_tests(
    *,
    checkout_path: str | Path,
    expected_revision: str,
    image: str,
    command: Sequence[str],
    log_dir: str | Path,
    engine: str = "podman",
    timeout_seconds: int = 900,
    memory_limit: str = "2g",
    cpu_limit: str = "2",
    pids_limit: int = 128,
) -> dict:
    """Run an explicit argv against an exact clean checkout and retain full logs."""
    if not _SHA_RE.fullmatch(expected_revision):
        raise IsolatedRunError("expected_revision must be a full Git SHA")
    if not _IMAGE_RE.fullmatch(image):
        raise IsolatedRunError("image must be pinned by registry @sha256 digest or local sha256 image ID")
    if engine not in {"podman", "docker"}:
        raise IsolatedRunError("engine must be podman or docker")
    if not command or any(not isinstance(part, str) or not part or "\x00" in part for part in command):
        raise IsolatedRunError("command must be a non-empty argv array of non-empty strings")
    if not 1 <= timeout_seconds <= 7200 or not 1 <= pids_limit <= 4096:
        raise IsolatedRunError("timeout_seconds or pids_limit is outside the permitted range")
    if not re.fullmatch(r"[1-9][0-9]*(?:m|g)", memory_limit):
        raise IsolatedRunError("memory_limit must be a positive integer followed by m or g")
    if not re.fullmatch(r"[1-9][0-9]*(?:\.[0-9]+)?", cpu_limit):
        raise IsolatedRunError("cpu_limit must be a positive CPU quantity")

    repo_arg = Path(checkout_path)
    if repo_arg.is_symlink():
        raise IsolatedRunError("checkout_path must not be a symlink")
    repo = repo_arg.resolve(strict=True)
    if not repo.is_dir() or not (repo / ".git").is_dir():
        raise IsolatedRunError("checkout_path must be an existing Git working tree")
    actual_revision = _git_value(repo, "rev-parse", "HEAD")
    if actual_revision.lower() != expected_revision.lower():
        raise IsolatedRunError(
            f"checkout revision mismatch: expected {expected_revision}, got {actual_revision}"
        )
    if _git_value(repo, "status", "--porcelain"):
        raise IsolatedRunError("checkout has uncommitted or untracked changes")
    tree_sha = _git_value(repo, "rev-parse", "HEAD^{tree}")

    executable = shutil.which(engine)
    if not executable:
        raise IsolatedRunError(f"{engine} executable was not found")
    logs = Path(log_dir)
    if logs.exists() and (not logs.is_dir() or any(logs.iterdir())):
        raise IsolatedRunError("log_dir must be a new or empty directory")
    logs.mkdir(parents=True, exist_ok=True)
    logs = logs.resolve()
    stdout_path, stderr_path = logs / "stdout.log", logs / "stderr.log"
    cidfile_path = logs / "container.cid"

    argv = [
        executable, "run", "--rm", "--pull=never", "--network=none",
        "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
        f"--pids-limit={pids_limit}", f"--memory={memory_limit}",
        f"--cpus={cpu_limit}", "--user=65532:65532",
        f"--cidfile={cidfile_path}",
        "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=512m",
        "--env=HOME=/tmp", "--env=TMPDIR=/tmp",
        "--env=PYTHONDONTWRITEBYTECODE=1", "--env=PYTEST_ADDOPTS=-p no:cacheprovider",
        f"--volume={repo}:/workspace:ro", "--workdir=/workspace",
        image, *command,
    ]
    started = datetime.now(UTC)
    timed_out = False
    cleanup_status = "not_needed"
    runner_env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    try:
        with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
            completed = subprocess.run(
                argv, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                check=False, timeout=timeout_seconds, env=runner_env,
            )
        exit_code = completed.returncode
        if cidfile_path.exists():
            try:
                cidfile_path.unlink()
            except OSError:
                cleanup_status = "cidfile_cleanup_failed"
    except subprocess.TimeoutExpired:
        timed_out, exit_code = True, None
        container_id = cidfile_path.read_text(encoding="ascii", errors="ignore").strip() if cidfile_path.exists() else ""
        if _CONTAINER_ID_RE.fullmatch(container_id):
            try:
                kill_result = subprocess.run(
                    [executable, "kill", container_id], stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    check=False, timeout=10, env=runner_env,
                )
                kill_code = kill_result.returncode
            except (OSError, subprocess.TimeoutExpired):
                kill_code = None
            try:
                remove_result = subprocess.run(
                    [executable, "rm", "-f", container_id], stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    check=False, timeout=10, env=runner_env,
                )
                remove_code = remove_result.returncode
            except (OSError, subprocess.TimeoutExpired):
                remove_code = None
            cleanup_status = (
                "removed" if kill_code == 0 or remove_code == 0 else "cleanup_failed"
            )
        else:
            cleanup_status = "container_id_unavailable"
        if cidfile_path.exists():
            try:
                cidfile_path.unlink()
            except OSError:
                cleanup_status = "cleanup_failed"

    stdout_hash, stderr_hash = _sha256_file(stdout_path), _sha256_file(stderr_path)
    stdout_text = stdout_path.read_text(encoding="utf-8", errors="replace")
    stderr_text = stderr_path.read_text(encoding="utf-8", errors="replace")
    status = "timed_out" if timed_out else ("passed" if exit_code == 0 else "failed")
    return {
        "schema_version": "tensorbench.isolated-run.v1",
        "status": status,
        "method": "oci_container_no_network_read_only_checkout",
        "started_at": started.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "candidate_revision": actual_revision,
        "git_tree_sha": tree_sha,
        "image": image,
        "engine": engine,
        "command": list(command),
        "exit_code": exit_code,
        "timed_out": timed_out,
        "container_cleanup_status": cleanup_status,
        "timeout_seconds": timeout_seconds,
        "limits": {
            "network": "none", "rootfs": "read_only", "checkout": "read_only",
            "memory": memory_limit, "cpus": cpu_limit, "pids": pids_limit,
            "capabilities": "all_dropped", "user": "65532:65532",
        },
        "stdout": {"path": str(stdout_path), "sha256": stdout_hash,
                   "bytes": stdout_path.stat().st_size, "excerpt": stdout_text[-12000:]},
        "stderr": {"path": str(stderr_path), "sha256": stderr_hash,
                   "bytes": stderr_path.stat().st_size, "excerpt": stderr_text[-12000:]},
        "limitations": [
            "Container isolation is defense-in-depth, not a formally verified sandbox.",
            "Docker requires a trusted isolated host; rootless Podman is preferred.",
            "Timed-out containers are explicitly killed and removed when the engine provides a valid cidfile.",
            "A passing test command does not prove scientific or functional correctness.",
        ],
    }
