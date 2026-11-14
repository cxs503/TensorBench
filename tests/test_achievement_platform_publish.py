import json

import pytest

from tensorbench.publish import build_achievement_evaluation_payload


def _report():
    return {
        "product_id": "agent-achievement-evaluator",
        "product_version": "0.1.0",
        "run_id": "achievement-1234567890abcdef",
        "overall_status": "passed",
        "evidence_refs": ["artifact://diff", "artifact://ci-log"],
        "summary": {
            "work_package_id": "wp-42",
            "candidate_revision": "a" * 40,
            "changed_file_count": 2,
            "code_file_count": 1,
            "acceptance_criteria_count": 1,
            "test_count": 1,
        },
    }


def test_builds_s1_review_payload_without_auto_assigning_grade(tmp_path):
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(_report()), encoding="utf-8")
    payload = build_achievement_evaluation_payload(
        _report(), mission_id=42, contributor="agent-a", reviewer="human-reviewer",
        grade="S1", e_level="E1", report_path=report_path, repo="TensorPlatform",
    )
    assert payload["grade"] == "S1"
    assert payload["e_level"] == "E1"
    assert payload["reviewer_kind"] == "independent"
    assert payload["artifact_id"] == f"agent-work-package:wp-42@{'a' * 40}"
    assert any(item["kind"] == "commit" for item in payload["evidence_refs"])
    assert len(payload["grade_reason"]) >= 50


def test_s2_requires_explicit_five_element_chain(tmp_path):
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(_report()), encoding="utf-8")
    with pytest.raises(ValueError, match="five-element"):
        build_achievement_evaluation_payload(
            _report(), mission_id=42, contributor="agent-a", reviewer="human-reviewer",
            grade="S2", e_level="E2", report_path=report_path, baseline_or_scope="baseline-v1",
        )


def test_failed_achievement_report_cannot_be_published(tmp_path):
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(_report()), encoding="utf-8")
    report = _report()
    report["overall_status"] = "inconclusive"
    with pytest.raises(ValueError, match="only passed"):
        build_achievement_evaluation_payload(
            report, mission_id=42, contributor="agent-a", reviewer="human-reviewer",
            grade="S1", e_level="E1", report_path=report_path,
        )


def test_reviewer_must_be_independent(tmp_path):
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(_report()), encoding="utf-8")
    with pytest.raises(ValueError, match="differ"):
        build_achievement_evaluation_payload(
            _report(), mission_id=42, contributor="agent-a", reviewer="agent-a",
            grade="S1", e_level="E1", report_path=report_path,
        )
