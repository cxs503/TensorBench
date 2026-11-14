"""Read-only TensorPlatform Mission + GitHub evidence collector.

Network access is explicit and read-only. Tokens are read from environment
variables and are never written into the evidence bundle.
"""
from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from .achievement import AchievementInputError


def _get_json(url: str, token: str | None, *, accept: str = "application/vnd.github+json") -> Any:
    headers = {"Accept": accept, "User-Agent": "TensorBench-Agent-Achievement-Evaluator"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read(2000).decode("utf-8", errors="replace")
        raise AchievementInputError(f"GET {urlsplit(url).path} returned HTTP {exc.code}: {detail}") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise AchievementInputError(f"GET {urlsplit(url).path} failed: {exc}") from exc


def _pages(url: str, token: str | None, *, page_limit: int = 10) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for page in range(1, page_limit + 1):
        separator = "&" if "?" in url else "?"
        batch = _get_json(f"{url}{separator}per_page=100&page={page}", token)
        if not isinstance(batch, list):
            raise AchievementInputError(f"Expected an array from {urlsplit(url).path}")
        rows.extend(item for item in batch if isinstance(item, dict))
        if len(batch) < 100:
            return rows
    raise AchievementInputError(f"Pagination limit exceeded for {urlsplit(url).path}")


def collect_mission_snapshot(
    *,
    platform_api_base: str,
    mission_id: int,
    github_owner: str = "cxs503",
    platform_token: str | None = None,
    github_token: str | None = None,
) -> dict[str, Any]:
    """Fetch one tenant-authorized Mission and its exact-commit GitHub evidence."""
    base = platform_api_base.rstrip("/")
    parsed = urlsplit(base)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        raise AchievementInputError("platform_api_base must be an absolute HTTP(S) URL")
    if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise AchievementInputError("platform_api_base must use HTTPS outside localhost")

    mission_url = f"{base}/tensor/missions/{int(mission_id)}"
    mission = _get_json(mission_url, platform_token)
    if not isinstance(mission, dict) or str(mission.get("id")) != str(mission_id):
        raise AchievementInputError("TensorPlatform returned an unexpected Mission payload")

    repo_value = str(mission.get("repo") or "").strip()
    if not repo_value:
        raise AchievementInputError("Mission has no repository name")
    repo = repo_value if "/" in repo_value else f"{github_owner}/{repo_value}"
    if len(repo.split("/")) != 2:
        raise AchievementInputError("Mission repo must resolve to owner/repository")

    result = mission.get("result") if isinstance(mission.get("result"), dict) else {}
    evidence = result.get("evidence") if isinstance(result.get("evidence"), dict) else {}
    summary = evidence.get("summary") if isinstance(evidence.get("summary"), dict) else {}
    head_sha = (
        evidence.get("head_commit")
        or result.get("head_commit")
        or summary.get("head_commit")
        or summary.get("commit_sha")
    )
    if not isinstance(head_sha, str) or len(head_sha) not in {40, 64}:
        raise AchievementInputError(
            "Mission result has no immutable head_commit; cannot safely associate a PR"
        )

    github_root = f"https://api.github.com/repos/{quote(repo, safe='/')}"
    associated = _pages(
        f"{github_root}/commits/{quote(head_sha, safe='')}/pulls",
        github_token,
    )
    exact_prs = [
        item for item in associated
        if isinstance(item.get("head"), dict)
        and item["head"].get("sha") == head_sha
    ]
    if len(exact_prs) != 1:
        raise AchievementInputError(
            f"Expected exactly one PR for Mission commit {head_sha}; found {len(exact_prs)}"
        )
    pr = exact_prs[0]
    number = pr.get("number")
    if not isinstance(number, int):
        raise AchievementInputError("GitHub associated PR has no numeric number")

    files = _pages(f"{github_root}/pulls/{number}/files", github_token)
    pr["files"] = files
    checks_payload = _get_json(
        f"{github_root}/commits/{quote(head_sha, safe='')}/check-runs?per_page=100",
        github_token,
    )
    if not isinstance(checks_payload, dict):
        raise AchievementInputError("GitHub check-runs response is not an object")
    statuses_payload = _get_json(
        f"{github_root}/commits/{quote(head_sha, safe='')}/status",
        github_token,
    )
    if not isinstance(statuses_payload, dict):
        raise AchievementInputError("GitHub commit-status response is not an object")
    checks = {
        "check_runs": checks_payload.get("check_runs") or [],
        "statuses": [
            {**item, "sha": statuses_payload.get("sha") or head_sha}
            for item in (statuses_payload.get("statuses") or [])
            if isinstance(item, dict)
        ],
    }

    result_evidence = result.get("evidence") if isinstance(result.get("evidence"), dict) else {}
    criteria = mission.get("acceptance_criteria")
    if criteria is None:
        criteria = result_evidence.get("acceptance_criteria")
    if criteria is None:
        criteria = result.get("acceptance_criteria")
    if criteria is None:
        criteria = summary.get("acceptance_criteria")

    def first_value(*values: Any) -> Any:
        return next((value for value in values if value is not None), None)

    criteria_sha256 = first_value(
        mission.get("acceptance_criteria_sha256"),
        result_evidence.get("acceptance_criteria_sha256"),
        result.get("acceptance_criteria_sha256"),
        summary.get("acceptance_criteria_sha256"),
    )
    frozen_at = first_value(
        mission.get("acceptance_criteria_frozen_at"),
        result_evidence.get("acceptance_criteria_frozen_at"),
        result.get("acceptance_criteria_frozen_at"),
    )
    freeze_source = first_value(
        mission.get("acceptance_criteria_freeze_source"),
        result_evidence.get("acceptance_criteria_freeze_source"),
        result.get("acceptance_criteria_freeze_source"),
    )
    criteria_version = first_value(
        mission.get("acceptance_criteria_version"),
        result_evidence.get("acceptance_criteria_version"),
        result.get("acceptance_criteria_version"),
    )
    integrity = "missing"
    if criteria is not None and criteria_sha256 is not None:
        try:
            normalized = []
            for index, item in enumerate(criteria, start=1):
                if not isinstance(item, dict):
                    raise ValueError("criterion must be an object")
                entry = dict(item)
                entry["criterion_id"] = entry.get("criterion_id", entry.get("id", f"C{index:03d}"))
                entry.pop("id", None)
                if isinstance(entry.get("metric"), str):
                    entry["metric"] = entry["metric"].strip()
                normalized.append(entry)
            payload = json.dumps(normalized, sort_keys=True, ensure_ascii=False,
                                 separators=(",", ":"), allow_nan=False).encode("utf-8")
            import hashlib
            actual_digest = hashlib.sha256(payload).hexdigest()
            integrity = "verified" if actual_digest == str(criteria_sha256).lower() else "mismatch"
        except (TypeError, ValueError):
            integrity = "invalid"

    contract = {
        "criteria": criteria if isinstance(criteria, list) else [],
        "sha256": criteria_sha256,
        "frozen_at": frozen_at,
        "version": criteria_version,
        "freeze_source": freeze_source,
        "integrity_status": integrity,
        "status": (
            "declared" if isinstance(criteria, list) and criteria
            and freeze_source == "mission_created" and integrity == "verified"
            else "not_declared" if not criteria
            else "legacy_or_unverified"
        ),
    }
    snapshot: dict[str, Any] = {
        "mission": mission,
        "pull_request": pr,
        "checks": checks,
        "acceptance_contract": contract,
        "collection_metadata": {
            "mode": "live_read_only",
            "mission_endpoint": f"/tensor/missions/{int(mission_id)}",
            "github_repository": repo,
            "associated_commit_sha": head_sha,
            "pull_request_number": number,
            "acceptance_criteria_source": (
                "mission_contract" if criteria is not None else "not_declared"
            ),
            "acceptance_criteria_integrity": integrity,
        },
    }
    if isinstance(criteria, list) and criteria:
        snapshot["acceptance_criteria"] = criteria
    return snapshot
