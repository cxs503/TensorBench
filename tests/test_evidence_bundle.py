"""AE-01 evidence-model tests: schema conformance, tamper detection, explicit missing.

The fixtures under ``tests/fixtures/real_missions`` are *live* bundles recorded
from TensorPlatform (127.0.0.1:8010) and api.github.com by
``scripts/collect_evidence_fixtures.py``. Nothing here is mocked data: the unit
tests below either read those real bundles or exercise the pure normalizer.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tensorbench import evidence_bundle as model

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "evidence_bundle.json"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "real_missions"


def _fixtures() -> list[tuple[Path, dict]]:
    paths = sorted(p for p in FIXTURE_DIR.glob("*.json") if p.name != "MANIFEST.json")
    return [(path, json.loads(path.read_text(encoding="utf-8"))) for path in paths]


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def test_at_least_five_real_mission_bundles_are_checked_in():
    fixtures = _fixtures()
    assert len(fixtures) >= 5, f"need >=5 real mission bundles, found {len(fixtures)}"
    for path, bundle in fixtures:
        assert bundle["collector"]["mode"] == "live_read_only", path.name
        assert bundle["platform"]["payload_sha256"] not in {"", model.MISSING}, path.name
        assert bundle["collected_at"].endswith("Z"), path.name


def test_every_real_bundle_validates_against_schema():
    jsonschema = pytest.importorskip("jsonschema")
    schema = _schema()
    jsonschema.Draft202012Validator.check_schema(schema)
    validator = jsonschema.Draft202012Validator(schema)
    for path, bundle in _fixtures():
        errors = sorted(validator.iter_errors(bundle), key=lambda error: list(error.path))
        assert not errors, f"{path.name}: {[error.message for error in errors][:3]}"


def test_every_real_bundle_self_digest_matches():
    for path, bundle in _fixtures():
        result = model.verify_bundle(bundle)
        assert result["digest"] == "match", f"{path.name} digest drifted"
        assert result["recomputed"] == bundle["integrity"]["bundle_sha256"]


def test_one_byte_fingerprint_tamper_changes_digest_and_is_detected():
    """Flipping a single hex character of a deliverable fingerprint must change the digest."""
    tampered_any = False
    for path, bundle in _fixtures():
        for index, deliverable in enumerate(bundle["deliverables"]):
            if deliverable["sha256"] == model.MISSING:
                continue
            mutated = json.loads(json.dumps(bundle))
            digest = mutated["deliverables"][index]["sha256"]
            mutated["deliverables"][index]["sha256"] = ("0" if digest[0] != "0" else "1") + digest[1:]
            before = model.canonical_bytes(bundle)
            after = model.canonical_bytes({**mutated, "integrity": None})
            assert before != after
            result = model.verify_bundle(mutated)
            assert result["digest"] == "mismatch", f"{path.name} accepted a tampered fingerprint"
            tampered_any = True
            break
        if tampered_any:
            break
    assert tampered_any, "no fixture carries a real deliverable fingerprint to tamper with"


def test_single_byte_tamper_anywhere_in_bundle_is_detected():
    _, bundle = _fixtures()[0]
    for field in ("mission_id", "collected_at"):
        mutated = json.loads(json.dumps(bundle))
        mutated[field] = mutated[field] if field == "mission_id" else "2026-11-14T00:00:00Z"
    mutated = json.loads(json.dumps(bundle))
    mutated["mission"]["status"] = mutated["mission"]["status"] + "x"
    assert model.verify_bundle(mutated)["digest"] == "mismatch"


def test_mission_without_pull_request_records_pr_as_missing():
    """Negative case: a real mission with no agent/m<id> PR yields pull_request == "missing"."""
    no_pr = [
        bundle for _, bundle in _fixtures()
        if bundle["pull_request"] == model.MISSING
    ]
    assert no_pr, "expected at least one recorded mission without a PR"
    for bundle in no_pr:
        assert "pull_request" in bundle["missing"]
        assert "commit.sha" in bundle["missing"]
        assert bundle["commit"] == model.MISSING
        assert bundle["ci"] == model.MISSING
        assert bundle["deliverables"] == []


def _minimal_mission(**overrides):
    mission = {
        "id": 7,
        "repo": "TensorBench",
        "status": "succeeded",
        "goal": "do the thing",
        "result": None,
        "claimed_by": "agent",
        "created_at": "2026-11-01T00:00:00Z",
        "finished_at": "2026-11-02T00:00:00Z",
    }
    mission.update(overrides)
    return mission


def test_build_marks_unavailable_deliverable_fingerprint_as_missing():
    files = [{"filename": "docs/report.md", "status": "added", "additions": 3, "deletions": 0, "sha": "b" * 40}]
    bundle = model.build_evidence_bundle(
        mission_id=7,
        mission=_minimal_mission(),
        platform_api_base="http://127.0.0.1:8010/api/v1",
        mission_endpoint="/tensor/missions/7",
        collected_at="2026-11-14T00:00:00Z",
        collector_version="0.1.0",
        pull_request={
            "number": 3,
            "state": "closed",
            "merged": True,
            "merged_at": "2026-11-02T00:00:00Z",
            "merge_commit_sha": "c" * 40,
            "head": {"sha": "d" * 40, "ref": "agent/m7"},
            "base": {"ref": "main"},
            "changed_files": 1,
            "additions": 3,
            "deletions": 0,
            "html_url": "https://github.com/cxs503/TensorBench/pull/3",
        },
        pull_request_files=files,
        check_runs={"check_runs": [], "total_count": 0},
        commit_statuses={"statuses": []},
        deliverable_sha256={"docs/report.md": (None, None)},
    )
    assert bundle["deliverables"][0]["sha256"] == model.MISSING
    assert bundle["deliverables"][0]["bytes"] is None
    assert any("docs/report.md" in item and item.endswith(".sha256") for item in bundle["missing"])
    assert bundle["ci"]["conclusion"] == "not_run"
    assert model.verify_bundle(bundle)["digest"] == "match"


def test_build_rejects_mission_payload_for_a_different_id():
    with pytest.raises(model.EvidenceBundleError):
        model.build_evidence_bundle(
            mission_id=8,
            mission=_minimal_mission(id=7),
            platform_api_base="http://127.0.0.1:8010/api/v1",
            mission_endpoint="/tensor/missions/8",
            collected_at="2026-11-14T00:00:00Z",
            collector_version="0.1.0",
        )


@pytest.mark.parametrize(
    "runs, statuses, expected",
    [
        ([], [], "not_run"),
        ([{"name": "pytest", "status": "completed", "conclusion": "success"}], [], "passed"),
        (
            [
                {"name": "pytest", "status": "completed", "conclusion": "success"},
                {"name": "lint", "status": "completed", "conclusion": "failure"},
            ],
            [],
            "failed",
        ),
        ([{"name": "pytest", "status": "in_progress", "conclusion": None}], [], "inconclusive"),
        ([], [{"context": "ci/test", "state": "failure"}], "failed"),
    ],
)
def test_ci_aggregation_never_turns_missing_or_pending_into_pass(runs, statuses, expected):
    assert model.summarize_ci(runs, statuses) == expected


def test_manifest_lists_the_recorded_missions():
    manifest = json.loads((FIXTURE_DIR / "MANIFEST.json").read_text(encoding="utf-8"))
    recorded = {entry["mission_id"] for entry in manifest["missions"]}
    checked_in = {int(path.stem) for path, _ in _fixtures()}
    assert recorded == checked_in
    assert len(recorded) >= 5
    for entry in manifest["missions"]:
        assert entry["bundle_sha256"] and len(entry["bundle_sha256"]) == 64
        assert entry["repo"]