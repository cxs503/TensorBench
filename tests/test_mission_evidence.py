import pytest

from tensorbench.mission_evidence import (
    build_mission_evidence_bundle,
    evaluate_mission_snapshot,
)


def _snapshot():
    sha = "a" * 40
    return {
        "mission": {
            "id": 73, "repo": "TensorLBM", "goal": "Add a tested feature",
            "status": "succeeded", "claimed_by": "agent-7",
            "acceptance_criteria": [{
                "criterion_id": "feature", "statement": "Feature works",
                "required": True, "requires_code": True, "requires_test": True,
                "evidence_refs": ["github://TensorLBM/pull/9@" + sha],
                "test_ids": ["check-run-1"],
            }],
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


def test_platform_metric_criteria_are_normalized_but_not_assumed_satisfied():
    import hashlib
    import json

    snapshot = _snapshot()
    criteria = [{"criterion_id": "C001", "metric": "relative_error",
                 "target": "<0.03", "tolerance": "0.001"}]
    digest = hashlib.sha256(json.dumps(
        criteria, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")).hexdigest()
    snapshot["acceptance_contract"] = {
        "criteria": criteria, "sha256": digest,
        "frozen_at": "2026-11-14T06:00:00Z", "version": 1,
        "freeze_source": "mission_created", "integrity_status": "verified",
        "status": "declared",
    }
    result = evaluate_mission_snapshot(snapshot)
    assert result["bundle"]["acceptance_criteria"][0]["criterion_id"] == "C001"
    assert result["bundle"]["acceptance_criteria"][0]["statement"] == (
        "relative_error: target=<0.03; tolerance=0.001"
    )
    # No criterion-to-test mapping was provided: a green unrelated CI check
    # must not be promoted into proof that this metric target was achieved.
    assert result["report"]["overall_status"] == "inconclusive"
    assert any(check["check_id"] == "mission.acceptance_contract"
               and check["state"] == "passed" for check in result["report"]["checks"])


def test_frozen_criteria_digest_mismatch_fails_closed():
    snapshot = _snapshot()
    snapshot["acceptance_contract"] = {
        "criteria": [{"criterion_id": "C001", "metric": "error",
                      "target": "<0.01", "tolerance": "0.001"}],
        "sha256": "0" * 64, "freeze_source": "mission_created",
        "integrity_status": "mismatch",
    }
    result = evaluate_mission_snapshot(snapshot)
    assert result["report"]["overall_status"] == "failed"


def test_legacy_start_contract_remains_inconclusive_even_when_digest_is_valid():
    import hashlib
    import json

    snapshot = _snapshot()
    criteria = [{"criterion_id": "C001", "metric": "error",
                 "target": "<0.01", "tolerance": "0.001"}]
    digest = hashlib.sha256(json.dumps(
        criteria, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")).hexdigest()
    snapshot["acceptance_contract"] = {
        "criteria": criteria, "sha256": digest,
        "freeze_source": "legacy_start", "integrity_status": "verified",
    }
    result = evaluate_mission_snapshot(snapshot)
    assert result["report"]["overall_status"] == "inconclusive"
