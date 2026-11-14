from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tensorbench import isolated_runner
from tensorbench.cli import build_parser


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
        command=["python", "-m", "pytest", "-q"], log_dir=tmp_path / "logs",
    )
    assert report["status"] == "passed"
    assert report["candidate_revision"] == SHA
    assert "--network=none" in captured["argv"]
    assert "--read-only" in captured["argv"]
    assert "--cap-drop=ALL" in captured["argv"]
    assert any(arg.startswith("--cidfile=") for arg in captured["argv"])
    assert report["container_cleanup_status"] == "not_needed"
    assert any(str(repo) in arg and arg.endswith(":/workspace:ro") for arg in captured["argv"])
    assert report["stdout"]["sha256"]
    assert Path(report["stdout"]["path"]).is_file()
    assert Path(report["stderr"]["path"]).is_file()


def test_rejects_mutated_checkout(tmp_path, monkeypatch):
    repo = _repo(tmp_path, monkeypatch)
    monkeypatch.setattr(isolated_runner, "_git_value", lambda path, *args: SHA if args[0] == "rev-parse" else " M file.py")
    with pytest.raises(isolated_runner.IsolatedRunError, match="uncommitted"):
        isolated_runner.run_isolated_tests(
            checkout_path=repo, expected_revision=SHA, image=IMAGE,
            command=["pytest", "-q"], log_dir=tmp_path / "logs",
        )


def test_rejects_unpinned_image(tmp_path, monkeypatch):
    repo = _repo(tmp_path, monkeypatch)
    with pytest.raises(isolated_runner.IsolatedRunError, match="pinned"):
        isolated_runner.run_isolated_tests(
            checkout_path=repo, expected_revision=SHA, image="python:3.11",
            command=["pytest", "-q"], log_dir=tmp_path / "logs",
        )


def test_rejects_revision_mismatch(tmp_path, monkeypatch):
    repo = _repo(tmp_path, monkeypatch)
    monkeypatch.setattr(isolated_runner, "_git_value", lambda path, *args: "c" * 40)
    with pytest.raises(isolated_runner.IsolatedRunError, match="revision mismatch"):
        isolated_runner.run_isolated_tests(
            checkout_path=repo, expected_revision=SHA, image=IMAGE,
            command=["pytest", "-q"], log_dir=tmp_path / "logs",
        )


def test_timeout_is_recorded(tmp_path, monkeypatch):
    repo = _repo(tmp_path, monkeypatch)

    def fake_run(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, 1)

    monkeypatch.setattr(isolated_runner.subprocess, "run", fake_run)
    report = isolated_runner.run_isolated_tests(
        checkout_path=repo, expected_revision=SHA, image=IMAGE,
        command=["pytest", "-q"], timeout_seconds=1, log_dir=tmp_path / "logs",
    )
    assert report["status"] == "timed_out"
    assert report["timed_out"] is True
    assert report["container_cleanup_status"] == "container_id_unavailable"


def test_reverify_cli_keeps_subcommand_and_command_argv_separate():
    args = build_parser().parse_args([
        "reverify-tests", "--checkout", "/tmp/repo", "--revision", SHA,
        "--image", IMAGE, "--log-dir", "/tmp/logs", "--", "python", "-m", "pytest", "-q",
    ])
    assert args.command == "reverify-tests"
    assert args.test_argv == ["--", "python", "-m", "pytest", "-q"]


def test_accepts_local_immutable_image_id(tmp_path, monkeypatch):
    repo = _repo(tmp_path, monkeypatch)
    image_id = "sha256:" + "c" * 64

    def fake_run(argv, **kwargs):
        kwargs["stdout"].write(b"2 passed")
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(isolated_runner.subprocess, "run", fake_run)
    report = isolated_runner.run_isolated_tests(
        checkout_path=repo, expected_revision=SHA, image=image_id,
        command=["python", "-m", "pytest", "-q"], log_dir=tmp_path / "logs",
    )
    assert report["status"] == "passed"
    assert report["image"] == image_id


def test_timeout_kills_and_removes_container_when_cidfile_exists(tmp_path, monkeypatch):
    repo = _repo(tmp_path, monkeypatch)
    calls = []
    container_id = "d" * 64

    def fake_run(argv, **kwargs):
        calls.append(argv)
        if argv[1] == "run":
            cid_arg = next(arg for arg in argv if arg.startswith("--cidfile="))
            Path(cid_arg.split("=", 1)[1]).write_text(container_id, encoding="ascii")
            raise subprocess.TimeoutExpired(argv, 1)
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(isolated_runner.subprocess, "run", fake_run)
    report = isolated_runner.run_isolated_tests(
        checkout_path=repo, expected_revision=SHA, image=IMAGE,
        command=["pytest", "-q"], timeout_seconds=1, log_dir=tmp_path / "logs",
    )
    assert report["status"] == "timed_out"
    assert report["container_cleanup_status"] == "removed"
    assert calls[1][1:3] == ["kill", container_id]
    assert calls[2][1:4] == ["rm", "-f", container_id]
