import hashlib
import json

import pytest

from tensorbench.mission_evidence import (
    build_mission_evidence_bundle,
    evaluate_mission_snapshot,
)


def _snapshot():
    sha = "a" * 40
    criteria = [{
        "criterion_id": "feature", "statement": "Feature works",
        "required": True, "requires_code": True, "requires_test": True,
        "evidence_refs": ["github://TensorLBM/pull/9@" + sha],
        "test_ids": ["check-run-1"],
    }]
    criteria_sha = hashlib.sha256(json.dumps(
        criteria, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")).hexdigest()
    return {
        "mission": {
            "id": 73, "repo": "TensorLBM", "goal": "Add a tested feature",
            "status": "succeeded", "claimed_by": "agent-7",
            "acceptance_criteria": criteria,
            "acceptance_criteria_sha256": criteria_sha,
            "acceptance_criteria_freeze_source": "mission_created",
            "acceptance_criteria_status": "declared",
            "acceptance_criteria_frozen_at": "2026-11-14T05:00:00Z",
            "acceptance_criteria_version": 1,
        },
        "pull_request": {
            "number": 9, "html_url": "https://github.com/cxs503/TensorLBM/pull/9",
            "state": "closed", "merged": True, "head": {"sha": sha},
            "files": [{"filename": "src/feature.py", "status": "modified", "additions": 12}],
        },
        "checks": {"check_runs": [{
            "id": 1, "name": "pytest", "status": "completed",
            "conclusion": "success", "head_sha": sha,
        }], "statuses": []},
    }


def test_snapshot_produces_revision_pinned_bundle_and_pass_report():
    result = evaluate_mission_snapshot(_snapshot())
    assert result["report"]["overall_status"] == "passed"
    assert result["bundle"]["candidate_revision"] == "a" * 40
    assert result["report"]["summary"]["mission_id"] == 73
    assert result["bundle"]["artifacts"][1]["kind"] == "check_run"


def test_missing_predeclared_acceptance_criteria_is_inconclusive():
    snapshot = _snapshot()
    del snapshot["mission"]["acceptance_criteria"]
    result = evaluate_mission_snapshot(snapshot)
    assert result["report"]["overall_status"] == "inconclusive"
    assert result["report"]["summary"]["acceptance_criteria_source"] == "not_declared"


def test_check_for_different_commit_is_inconclusive():
    snapshot = _snapshot()
    snapshot["checks"]["check_runs"][0]["head_sha"] = "b" * 40
    result = evaluate_mission_snapshot(snapshot)
    assert result["report"]["overall_status"] == "inconclusive"


def test_pending_ci_is_not_a_pass():
    snapshot = _snapshot()
    snapshot["checks"]["check_runs"][0]["status"] = "in_progress"
    snapshot["checks"]["check_runs"][0]["conclusion"] = None
    result = evaluate_mission_snapshot(snapshot)
    assert result["report"]["overall_status"] == "inconclusive"


def test_failed_mission_cannot_pass_even_if_ci_passes():
    snapshot = _snapshot()
    snapshot["mission"]["status"] = "failed"
    result = evaluate_mission_snapshot(snapshot)
    assert result["report"]["overall_status"] == "inconclusive"


def test_invalid_commit_sha_is_rejected():
    snapshot = _snapshot()
    snapshot["pull_request"]["head"]["sha"] = "latest"
    with pytest.raises(ValueError, match="immutable Git SHA"):
        build_mission_evidence_bundle(snapshot)


def test_missing_check_snapshot_does_not_create_test_evidence():
    snapshot = _snapshot()
    snapshot["checks"] = {"check_runs": [], "statuses": []}
    result = evaluate_mission_snapshot(snapshot)
    assert result["report"]["overall_status"] == "inconclusive"


def test_successful_build_check_is_not_mistaken_for_test_evidence():
    snapshot = _snapshot()
    snapshot["checks"]["check_runs"][0]["name"] = "build-and-lint"
    result = evaluate_mission_snapshot(snapshot)
    assert result["report"]["overall_status"] == "inconclusive"
    assert result["bundle"]["tests"] == []



def test_successful_build_check_is_not_mistaken_for_test_evidence():
    snapshot = _snapshot()
    snapshot["checks"]["check_runs"][0]["name"] = "build-and-lint"
    result = evaluate_mission_snapshot(snapshot)
    assert result["report"]["overall_status"] == "inconclusive"
    assert result["bundle"]["tests"] == []


def test_criteria_digest_mismatch_cannot_be_evaluated_as_passed():
    snapshot = _snapshot()
    snapshot["mission"]["acceptance_criteria"][0]["statement"] = "Agent rewrote the criterion"
    result = evaluate_mission_snapshot(snapshot)
    assert result["report"]["overall_status"] == "failed"
    assert result["report"]["summary"]["acceptance_criteria_integrity"] == "mismatch"


def test_legacy_start_criteria_are_not_treated_as_predeclared():
    snapshot = _snapshot()
    snapshot["mission"]["acceptance_criteria_freeze_source"] = "legacy_start"
    result = evaluate_mission_snapshot(snapshot)
    assert result["report"]["overall_status"] == "inconclusive"
    assert result["report"]["summary"]["acceptance_criteria_source"] == "legacy_frozen_at_start"


def test_authoritative_empty_criteria_do_not_fall_back_to_agent_result():
    snapshot = _snapshot()
    snapshot["mission"]["acceptance_criteria"] = []
    snapshot["mission"]["acceptance_criteria_sha256"] = hashlib.sha256(b"[]").hexdigest()
    snapshot["mission"]["result"] = {"acceptance_criteria": [{
        "criterion_id": "agent-invented", "statement": "Self-asserted criterion",
        "required": True, "requires_code": True, "requires_test": True,
        "evidence_refs": [], "test_ids": ["check-run-1"],
    }]}
    result = evaluate_mission_snapshot(snapshot)
    assert result["report"]["overall_status"] == "inconclusive"
    assert result["report"]["summary"]["acceptance_criteria_source"] == "not_declared"
    assert result["bundle"]["acceptance_criteria"][0]["criterion_id"] == "mission-goal-not-formalized"
