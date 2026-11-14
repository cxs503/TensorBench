"""AE-01 collector contract tests.

These run offline: the recorded raw upstream payloads in
``tests/fixtures/recorded`` are replayed through the module-level transport seam
``tensorbench.collect._request_json``. The point is to prove that the shipping
client code, fed the *real* recorded payloads, reproduces the *real* recorded
bundle -- not to substitute a mock for the platform.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

from tensorbench import cli
from tensorbench import collect as collector
from tensorbench import evidence_bundle as model

ROOT = Path(__file__).resolve().parents[1]
RECORDED = ROOT / "tests" / "fixtures" / "recorded"
BUNDLES = ROOT / "tests" / "fixtures" / "real_missions"
MISSION_ID = 19812
NO_PR_MISSION_ID = 20111


def _recording(mission_id: int) -> dict:
    return json.loads((RECORDED / f"m{mission_id}.json").read_text(encoding="utf-8"))


def _fixture_bundle(mission_id: int) -> dict:
    return json.loads((BUNDLES / f"{mission_id}.json").read_text(encoding="utf-8"))


def make_router(mission_id: int):
    raw = _recording(mission_id)
    pr = raw["pull_request"]
    contents = raw.get("deliverable_contents") or {}

    def router(url, token=None, *, accept="", method="GET", body=None):
        if "/auth/login" in url:
            return {"access_token": "replayed"}
        if re.search(r"/tensor/missions/\d+$", url):
            requested = int(url.rsplit("/", 1)[1])
            if requested != mission_id:
                raise collector.MissionNotFoundError(f"GET /tensor/missions/{requested} returned HTTP 404")
            return raw["mission"]
        if "/pulls?state=all" in url:
            return [pr] if pr is not None else []
        if re.search(r"/pulls/\d+/files", url):
            return raw["pull_request_files"]
        if re.search(r"/pulls/\d+$", url):
            return pr
        if "/check-runs" in url:
            return raw["check_runs"] or {"check_runs": [], "total_count": 0}
        if url.endswith("/status"):
            return raw["commit_statuses"] or {"statuses": []}
        if "/contents/" in url:
            path = url.split("/contents/", 1)[1].split("?", 1)[0]
            recorded = contents.get(path)
            if recorded is None:
                raise collector.CollectorError(f"GET /contents/{path} unavailable in recording")
            return {
                "size": recorded["size"],
                "content": recorded["content_b64"],
                "encoding": "base64",
            }
        raise AssertionError(f"unexpected URL in contract test: {url}")

    return router


def test_replayed_real_payloads_reproduce_the_recorded_bundle(monkeypatch):
    monkeypatch.setattr(collector, "_request_json", make_router(MISSION_ID))
    rebuilt = collector.collect_mission_evidence(
        MISSION_ID, github_token="replayed", platform_token="replayed", max_deliverables=25
    )
    recorded = _fixture_bundle(MISSION_ID)
    for field in ("mission", "commit", "pull_request", "ci"):
        assert rebuilt[field] == recorded[field], field
    assert model.verify_bundle(rebuilt)["digest"] == "match"
    # every deliverable whose content was recorded must fingerprint identically
    recorded_by_path = {item["path"]: item for item in recorded["deliverables"]}
    assert [item["path"] for item in rebuilt["deliverables"]] == list(recorded_by_path)
    for item in rebuilt["deliverables"]:
        if item["sha256"] != model.MISSING:
            assert item["sha256"] == recorded_by_path[item["path"]]["sha256"]
            assert item["origin"].startswith("github_contents@")


def test_unknown_mission_id_is_an_explicit_error(monkeypatch):
    monkeypatch.setattr(collector, "_request_json", make_router(MISSION_ID))
    with pytest.raises(collector.MissionNotFoundError) as excinfo:
        collector.collect_mission_evidence(999999, github_token="replayed", platform_token="replayed")
    assert "999999" in str(excinfo.value)


def test_cli_collect_writes_one_bundle_per_mission_and_keeps_going_after_failure(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(collector, "_request_json", make_router(MISSION_ID))
    monkeypatch.setattr(collector, "platform_login", lambda *a, **k: "replayed")
    monkeypatch.setattr(collector, "load_github_token", lambda *a, **k: "replayed")
    monkeypatch.setattr(sys, "argv", [
        "tensorbench", "collect", "--missions", f"m{MISSION_ID},m999999",
        "--out-dir", str(tmp_path),
    ])
    code = cli.main()
    assert code == 2  # one mission genuinely does not exist
    written = tmp_path / f"{MISSION_ID}.json"
    assert written.is_file()
    bundle = json.loads(written.read_text(encoding="utf-8"))
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((ROOT / "schemas" / "evidence_bundle.json").read_text(encoding="utf-8"))
    jsonschema.validate(bundle, schema)
    captured = capsys.readouterr()
    assert "m999999" in captured.err
    assert bundle["deliverables"]


def test_cli_collect_returns_zero_when_all_missions_exist(monkeypatch, tmp_path):
    monkeypatch.setattr(collector, "_request_json", make_router(MISSION_ID))
    monkeypatch.setattr(collector, "load_github_token", lambda *a, **k: "replayed")
    monkeypatch.setattr(collector, "platform_login", lambda *a, **k: "replayed")
    monkeypatch.setattr(sys, "argv", [
        "tensorbench", "collect", "--missions", f"m{MISSION_ID}", "--out-dir", str(tmp_path),
    ])
    code = cli.main()
    assert code == 0
    assert json.loads((tmp_path / f"{MISSION_ID}.json").read_text())["mission_id"] == MISSION_ID


def test_parse_mission_ids_accepts_m_prefix_and_dedupes():
    assert collector.parse_mission_ids("m12,13 m12") == [12, 13]
    with pytest.raises(collector.CollectorError):
        collector.parse_mission_ids("m,abc")


def test_platform_login_uses_creds_file_convention(monkeypatch, tmp_path):
    creds = tmp_path / "creds.json"
    creds.write_text(json.dumps({"username": "u", "password": "p"}), encoding="utf-8")
    seen = {}

    def router(url, token=None, *, accept="", method="GET", body=None):
        seen["url"] = url
        seen["method"] = method
        seen["body"] = body
        return {"access_token": "tok"}

    monkeypatch.setattr(collector, "_request_json", router)
    assert collector.platform_login("http://127.0.0.1:8010", creds_file=creds) == "tok"
    assert seen["url"] == "http://127.0.0.1:8010/api/v1/auth/login"
    assert seen["method"] == "POST"
    assert seen["body"] == {"username": "u", "password": "p"}


def test_github_token_parsed_from_git_credentials(monkeypatch, tmp_path):
    creds = tmp_path / ".git-credentials"
    creds.write_text("https://x-access-token:secret-token@github.com\n", encoding="utf-8")
    assert collector.load_github_token(creds) == "secret-token"
    with pytest.raises(collector.CollectorAuthError):
        collector.load_github_token(tmp_path / "missing")