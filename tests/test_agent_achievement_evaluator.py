from tensorbench.achievement import evaluate_work_package


def _bundle():
    revision = "a" * 40
    return {
        "work_package_id": "wp-001",
        "candidate_revision": revision,
        "acceptance_criteria": [{
            "criterion_id": "feature-works",
            "statement": "Implement the declared feature.",
            "required": True,
            "requires_code": True,
            "requires_test": True,
            "evidence_refs": ["artifact://diff"],
            "test_ids": ["test-feature"],
        }],
        "changed_files": [{"path": "src/feature.py", "status": "added", "additions": 42}],
        "tests": [{
            "test_id": "test-feature",
            "status": "passed",
            "commit_sha": revision,
            "artifact_refs": ["artifact://test-log"],
        }],
        "artifacts": [
            {"artifact_ref": "artifact://diff", "kind": "diff", "sha256": "a" * 64},
            {"artifact_ref": "artifact://test-log", "kind": "test_log", "sha256": "b" * 64},
        ],
    }


def test_agent_evaluator_accepts_complete_revision_pinned_evidence():
    report = evaluate_work_package(_bundle())
    assert report["overall_status"] == "passed"
    assert report["summary"]["candidate_revision"] == "a" * 40
    assert report["summary"]["code_file_count"] == 1


def test_agent_evaluator_rejects_failed_required_test():
    bundle = _bundle()
    bundle["tests"][0]["status"] = "failed"
    report = evaluate_work_package(bundle)
    assert report["overall_status"] == "failed"
    assert any(f["check_id"] == "criterion.feature-works.test.test-feature"
               for f in report["findings"])


def test_agent_evaluator_rejects_docs_only_change_for_code_criterion():
    bundle = _bundle()
    bundle["changed_files"] = [{"path": "docs/feature.md", "status": "modified"}]
    report = evaluate_work_package(bundle)
    assert report["overall_status"] == "failed"
    assert any(f["check_id"] == "candidate.code_delta" for f in report["findings"])


def test_agent_evaluator_marks_stale_test_revision_inconclusive():
    bundle = _bundle()
    bundle["tests"][0]["commit_sha"] = "c" * 40
    report = evaluate_work_package(bundle)
    assert report["overall_status"] == "inconclusive"


def test_agent_evaluator_does_not_pass_unresolved_evidence_refs():
    bundle = _bundle()
    bundle["acceptance_criteria"][0]["evidence_refs"] = ["artifact://missing"]
    report = evaluate_work_package(bundle)
    assert report["overall_status"] == "inconclusive"


def test_agent_evaluator_allows_non_code_work_package_when_declared():
    bundle = _bundle()
    bundle["acceptance_criteria"][0]["requires_code"] = False
    bundle["acceptance_criteria"][0]["requires_test"] = False
    bundle["changed_files"] = [{"path": "docs/guide.md", "status": "added"}]
    bundle["tests"] = []
    report = evaluate_work_package(bundle)
    assert report["overall_status"] == "passed"
    code_check = next(c for c in report["checks"] if c["check_id"] == "candidate.code_delta")
    assert code_check["state"] == "not_applicable"
