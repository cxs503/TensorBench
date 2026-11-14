from __future__ import annotations

import hashlib
import json

import pytest

from tensorbench.achievement import AchievementInputError
from tensorbench.isolated_evidence import attach_isolated_run


SHA = "a" * 40


def _fixture(tmp_path):
    stdout = tmp_path / "stdout.log"
    stderr = tmp_path / "stderr.log"
    stdout.write_text("all tests passed", encoding="utf-8")
    stderr.write_text("", encoding="utf-8")
    report_path = tmp_path / "run.json"
    report = {
        "candidate_revision": SHA, "status": "passed",
        "command": ["pytest", "-q"], "image": "runner@sha256:" + "b" * 64,
        "method": "oci_container_no_network_read_only_checkout", "exit_code": 0,
        "stdout": {"path": str(stdout), "sha256": hashlib.sha256(stdout.read_bytes()).hexdigest()},
        "stderr": {"path": str(stderr), "sha256": hashlib.sha256(stderr.read_bytes()).hexdigest()},
    }
    report_path.write_text(json.dumps(report), encoding="utf-8")
    bundle = {
        "candidate_revision": SHA,
        "acceptance_criteria": [{"criterion_id": "C1", "test_ids": []}],
        "tests": [], "artifacts": [], "collection": {},
    }
    return bundle, report, report_path, stdout


def test_attaches_verified_run_logs_to_selected_criterion(tmp_path):
    bundle, report, report_path, _ = _fixture(tmp_path)
    result = attach_isolated_run(
        bundle, report, report_path=report_path, test_id="rerun-1", criterion_ids=["C1"]
    )
    assert result["acceptance_criteria"][0]["test_ids"] == ["rerun-1"]
    assert result["tests"][0]["status"] == "passed"
    assert len(result["artifacts"]) == 3
    assert result["collection"]["isolated_runs"][0]["candidate_revision"] == SHA


def test_rejects_revision_mismatch(tmp_path):
    bundle, report, report_path, _ = _fixture(tmp_path)
    report["candidate_revision"] = "c" * 40
    with pytest.raises(AchievementInputError, match="revision"):
        attach_isolated_run(bundle, report, report_path=report_path, test_id="r", criterion_ids=["C1"])


def test_rejects_tampered_log(tmp_path):
    bundle, report, report_path, stdout = _fixture(tmp_path)
    stdout.write_text("tampered", encoding="utf-8")
    with pytest.raises(AchievementInputError, match="SHA-256"):
        attach_isolated_run(bundle, report, report_path=report_path, test_id="r", criterion_ids=["C1"])


def test_requires_explicit_criterion_mapping(tmp_path):
    bundle, report, report_path, _ = _fixture(tmp_path)
    with pytest.raises(AchievementInputError, match="unknown criterion"):
        attach_isolated_run(bundle, report, report_path=report_path, test_id="r", criterion_ids=["unknown"])
