from tensorbench import live_mission


SHA = "a" * 40


def test_collects_only_pr_pinned_to_mission_completion_commit(monkeypatch):
    calls = []

    def fake_get(url, token, **kwargs):
        calls.append(url)
        if url.endswith("/tensor/missions/42"):
            return {
                "id": 42, "repo": "TensorLBM", "goal": "Implement feature",
                "status": "succeeded", "claimed_by": "agent-1",
                "result": {
                    "evidence": {"head_commit": SHA, "summary": {"acceptance_criteria": []}}
                },
            }
        if "/commits/" in url and url.endswith("/pulls?per_page=100&page=1"):
            return [{
                "number": 17, "html_url": "https://github.com/cxs503/TensorLBM/pull/17",
                "head": {"sha": SHA}, "base": {"sha": "b" * 40},
                "state": "closed", "merged": True,
            }]
        if url.endswith("/pulls/17/files?per_page=100&page=1"):
            return [{"filename": "src/solver.py", "status": "modified", "additions": 8}]
        if "/check-runs?" in url:
            return {"check_runs": [{
                "id": 99, "name": "pytest", "status": "completed",
                "conclusion": "success", "head_sha": SHA,
            }]}
        if url.endswith("/status"):
            return {"sha": SHA, "statuses": []}
        raise AssertionError(url)

    monkeypatch.setattr(live_mission, "_get_json", fake_get)
    snapshot = live_mission.collect_mission_snapshot(
        platform_api_base="https://platform.example/api",
        mission_id=42,
        platform_token="platform-secret",
        github_token="github-secret",
    )
    assert snapshot["mission"]["id"] == 42
    assert snapshot["pull_request"]["number"] == 17
    assert snapshot["pull_request"]["head"]["sha"] == SHA
    assert snapshot["pull_request"]["files"][0]["filename"] == "src/solver.py"
    assert snapshot["checks"]["check_runs"][0]["head_sha"] == SHA
    assert all("secret" not in url for url in calls)


def test_refuses_to_guess_when_mission_has_no_commit_sha(monkeypatch):
    monkeypatch.setattr(
        live_mission, "_get_json",
        lambda url, token, **kwargs: {
            "id": 42, "repo": "TensorLBM", "result": {}
        },
    )
    try:
        live_mission.collect_mission_snapshot(
            platform_api_base="https://platform.example/api", mission_id=42
        )
    except ValueError as exc:
        assert "immutable head_commit" in str(exc)
    else:
        raise AssertionError("missing immutable commit must be rejected")


def test_refuses_ambiguous_pr_association(monkeypatch):
    def fake_get(url, token, **kwargs):
        if url.endswith("/tensor/missions/42"):
            return {
                "id": 42, "repo": "TensorLBM",
                "result": {"evidence": {"head_commit": SHA}},
            }
        if "/commits/" in url:
            return [
                {"number": 17, "head": {"sha": SHA}},
                {"number": 18, "head": {"sha": SHA}},
            ]
        raise AssertionError(url)

    monkeypatch.setattr(live_mission, "_get_json", fake_get)
    try:
        live_mission.collect_mission_snapshot(
            platform_api_base="https://platform.example/api", mission_id=42
        )
    except ValueError as exc:
        assert "found 2" in str(exc)
    else:
        raise AssertionError("ambiguous PR association must be rejected")
