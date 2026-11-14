from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tensorbench import isolated_runner


SHA = "a" * 40
IMAGE = "registry.example/tensorbench-runner@sha256:" + "b" * 64


def _repo(tmp_path: Path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    monkeypatch.setattr(isolated_runner, "_git_value", lambda path, *args: SHA if args[0] == "rev-parse" else "")
    monkeypatch.setattr(isolated_runner.shutil, "which", lambda name: "/usr/bin/podman")
    return repo


def test_runs_pinned_revision_in_restricted_container(tmp_path, monkeypatch):
    repo = _repo(tmp_path, monkeypatch)
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        kwargs["stdout"].write(b"12 passed")
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(isolated_runner.subprocess, "run", fake_run)
    report = isolated_runner.run_isolated_tests(
        checkout_path=repo, expected_revision=SHA, image=IMAGE,
        command=["python", "-m", "pytest", "-q"],
    )
    assert report["status"] == "passed"
    assert report["candidate_revision"] == SHA
    assert "--network=none" in captured["argv"]
    assert "--read-only" in captured["argv"]
    assert "--cap-drop=ALL" in captured["argv"]
    assert any(str(repo) in arg and arg.endswith(":/workspace:ro") for arg in captured["argv"])
    assert report["stdout"]["sha256"]


def test_rejects_mutated_checkout(tmp_path, monkeypatch):
    repo = _repo(tmp_path, monkeypatch)
    monkeypatch.setattr(isolated_runner, "_git_value", lambda path, *args: SHA if args[0] == "rev-parse" else " M file.py")
    with pytest.raises(isolated_runner.IsolatedRunError, match="uncommitted"):
        isolated_runner.run_isolated_tests(
            checkout_path=repo, expected_revision=SHA, image=IMAGE,
            command=["pytest", "-q"],
        )


def test_rejects_unpinned_image(tmp_path, monkeypatch):
    repo = _repo(tmp_path, monkeypatch)
    with pytest.raises(isolated_runner.IsolatedRunError, match="pinned"):
        isolated_runner.run_isolated_tests(
            checkout_path=repo, expected_revision=SHA, image="python:3.11",
            command=["pytest", "-q"],
        )


def test_rejects_revision_mismatch(tmp_path, monkeypatch):
    repo = _repo(tmp_path, monkeypatch)
    monkeypatch.setattr(isolated_runner, "_git_value", lambda path, *args: "c" * 40)
    with pytest.raises(isolated_runner.IsolatedRunError, match="revision mismatch"):
        isolated_runner.run_isolated_tests(
            checkout_path=repo, expected_revision=SHA, image=IMAGE,
            command=["pytest", "-q"],
        )


def test_timeout_is_recorded(tmp_path, monkeypatch):
    repo = _repo(tmp_path, monkeypatch)

    def fake_run(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, 1)

    monkeypatch.setattr(isolated_runner.subprocess, "run", fake_run)
    report = isolated_runner.run_isolated_tests(
        checkout_path=repo, expected_revision=SHA, image=IMAGE,
        command=["pytest", "-q"], timeout_seconds=1,
    )
    assert report["status"] == "timed_out"
    assert report["timed_out"] is True
