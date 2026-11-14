"""Pure evidence-bundle model for agent-Mission evidence collection (AE-01).

The bundle is the single audit artifact produced by ``tensorbench collect``:
mission metadata, the PR/commit that claims to deliver the mission, the CI
conclusion for that exact commit, per-deliverable SHA-256 fingerprints, the
collection timestamp and an explicit list of everything that is *missing*.

Design rules:

* nothing is inferred -- absent evidence is the literal string ``"missing"``
  and is repeated in ``missing`` so a reader never mistakes silence for pass;
* every judgment is pinned: the commit SHA and the SHA-256 of each raw upstream
  payload are recorded, so the bundle can be re-derived and tamper-checked;
* the bundle carries its own digest over canonical JSON (excluding
  ``integrity``) so a single flipped byte is detectable without the network.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "1.0.0"
KIND = "tensorbench.evidence_bundle"
MISSING = "missing"
DIGEST_SCOPE = "canonical_json_of_bundle_excluding_integrity"

CI_PASSED_STATES = {"success", "successful", "passed", "neutral"}
CI_FAILED_STATES = {
    "failure", "failed", "error", "timed_out", "action_required",
    "startup_failure", "cancelled",
}
CI_PENDING_STATES = {"queued", "in_progress", "pending", "waiting", "requested", "expected"}


class EvidenceBundleError(ValueError):
    """Raised when evidence cannot be normalized without inventing facts."""


def canonical_bytes(value: Any) -> bytes:
    """Deterministic JSON encoding used for every fingerprint in the bundle."""
    try:
        return json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
        raise EvidenceBundleError(f"value is not canonical JSON: {exc}") from exc


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_payload(value: Any) -> str:
    """SHA-256 of a payload's canonical JSON (``missing`` for absent payloads)."""
    if value is None:
        return MISSING
    return sha256_bytes(canonical_bytes(value))


def bundle_digest(bundle: Mapping[str, Any]) -> str:
    """Digest over the bundle with ``integrity`` removed."""
    body = {key: value for key, value in bundle.items() if key != "integrity"}
    return sha256_bytes(canonical_bytes(body))


def seal(bundle: dict[str, Any]) -> dict[str, Any]:
    """(Re)compute and store the bundle's self-digest. Mutates and returns ``bundle``."""
    bundle["integrity"] = {
        "bundle_sha256": bundle_digest(bundle),
        "digest_scope": DIGEST_SCOPE,
    }
    return bundle


def verify_bundle(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute the self-digest and report whether it still matches.

    Returns ``{"digest": "match"|"mismatch"|"absent", "recomputed": <hex>,
    "recorded": <hex or None>}``. A single flipped byte anywhere outside
    ``integrity`` changes the recomputed value.
    """
    integrity = bundle.get("integrity")
    recorded = integrity.get("bundle_sha256") if isinstance(integrity, Mapping) else None
    recomputed = bundle_digest(bundle)
    if not isinstance(recorded, str):
        return {"digest": "absent", "recomputed": recomputed, "recorded": None}
    return {
        "digest": "match" if recorded == recomputed else "mismatch",
        "recomputed": recomputed,
        "recorded": recorded,
    }


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise EvidenceBundleError(f"{name} must be an object")
    return dict(value)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_or_none(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_commit_sha(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return len(value) in {40, 64} and all(char in "0123456789abcdef" for char in value.lower())


def _normalize_state(value: Any) -> str:
    return str(value or "").strip().lower()


def is_commit_sha(value: Any) -> bool:
    """True for a 40/64 hex git object id."""
    return _is_commit_sha(value)


def summarize_ci(check_runs: Sequence[Mapping[str, Any]], statuses: Sequence[Mapping[str, Any]]) -> str:
    """Aggregate CI evidence into passed/failed/not_run/inconclusive.

    ``not_run`` means the commit simply has no CI evidence attached; it is not a
    pass. Any failure dominates; a single pending entry makes the aggregate
    inconclusive rather than letting an older green run speak for a new commit.
    """
    states: list[str] = []
    for run in check_runs:
        state = _normalize_state(run.get("conclusion") or run.get("status"))
        if state:
            states.append(state)
    for status in statuses:
        state = _normalize_state(status.get("state"))
        if state:
            states.append(state)
    if not states:
        return "not_run"
    if any(state in CI_FAILED_STATES for state in states):
        return "failed"
    if any(state in CI_PENDING_STATES for state in states):
        return "inconclusive"
    if any(state in CI_PASSED_STATES for state in states):
        return "passed"
    return "inconclusive"


def _mission_section(mission: Mapping[str, Any], mission_id: int) -> dict[str, Any]:
    if _int_or_none(mission.get("id")) != int(mission_id):
        raise EvidenceBundleError(
            f"TensorPlatform returned mission {mission.get('id')!r} for requested id {mission_id}"
        )
    repo = _text(mission.get("repo"))
    status = _text(mission.get("status"))
    if not repo:
        raise EvidenceBundleError("mission payload has no repository name")
    if not status:
        raise EvidenceBundleError("mission payload has no status")
    goal = mission.get("goal")
    result = mission.get("result")
    return {
        "id": int(mission_id),
        "repo": repo,
        "status": status,
        "claimed_by": _text(mission.get("claimed_by")),
        "created_at": _text(mission.get("created_at")),
        "finished_at": _text(mission.get("finished_at")),
        "goal": goal if isinstance(goal, str) else None,
        "goal_sha256": sha256_bytes(goal.encode("utf-8")) if isinstance(goal, str) else MISSING,
        "result_sha256": sha256_payload(result if isinstance(result, Mapping) else None),
    }


def _declared_head_commit(mission: Mapping[str, Any]) -> str | None:
    result = mission.get("result") if isinstance(mission.get("result"), Mapping) else {}
    evidence = result.get("evidence") if isinstance(result.get("evidence"), Mapping) else {}
    summary = evidence.get("summary") if isinstance(evidence.get("summary"), Mapping) else {}
    for candidate in (
        evidence.get("head_commit"),
        result.get("head_commit"),
        summary.get("head_commit"),
        summary.get("commit_sha"),
    ):
        if _is_commit_sha(candidate):
            return str(candidate)
    return None


def build_evidence_bundle(
    *,
    mission_id: int,
    mission: Mapping[str, Any],
    platform_api_base: str,
    mission_endpoint: str,
    collected_at: str,
    collector_version: str,
    github_repository: str | None = None,
    pull_request: Mapping[str, Any] | None = None,
    pull_request_files: Sequence[Mapping[str, Any]] | None = None,
    check_runs: Mapping[str, Any] | None = None,
    commit_statuses: Mapping[str, Any] | None = None,
    deliverable_sha256: Mapping[str, tuple[str | None, int | None]] | None = None,
    pr_resolution: str = "branch_head",
) -> dict[str, Any]:
    """Normalize one mission + its GitHub evidence into a sealed bundle.

    ``deliverable_sha256`` maps a deliverable path to ``(sha256, bytes)`` or
    ``(None, None)`` when the content could not be retrieved. Nothing is
    invented: every gap ends up in ``missing``.
    """
    mission_section = _mission_section(mission, mission_id)
    repository = _text(github_repository) or mission_section["repo"]
    missing: list[str] = []

    bundle: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "mission_id": int(mission_id),
        "collected_at": collected_at,
        "collector": {"name": "tensorbench", "version": collector_version, "mode": "live_read_only"},
        "platform": {
            "api_base": platform_api_base,
            "mission_endpoint": mission_endpoint,
            "payload_sha256": sha256_payload(mission),
        },
        "mission": mission_section,
    }

    if mission_section["result_sha256"] == MISSING:
        missing.append("mission.result_sha256")

    # ---- PR + commit -----------------------------------------------------
    if pull_request is None:
        bundle["pull_request"] = MISSING
        bundle["commit"] = MISSING
        missing.extend(["pull_request", "commit.sha"])
    else:
        pr = _mapping(pull_request, "pull_request")
        head = pr.get("head") if isinstance(pr.get("head"), Mapping) else {}
        base = pr.get("base") if isinstance(pr.get("base"), Mapping) else {}
        head_sha = head.get("sha") if _is_commit_sha(head.get("sha")) else None
        number = _int_or_none(pr.get("number"))
        if number is None:
            raise EvidenceBundleError("pull_request payload has no numeric number")
        pr_section: dict[str, Any] = {
            "number": number,
            "state": _text(pr.get("state")) or MISSING,
            "merged": pr.get("merged") if isinstance(pr.get("merged"), bool) else None,
            "merged_at": _text(pr.get("merged_at")),
            "merge_commit_sha": pr.get("merge_commit_sha")
            if _is_commit_sha(pr.get("merge_commit_sha"))
            else None,
            "head_ref": _text(head.get("ref")) or MISSING,
            "head_sha": head_sha or MISSING,
            "base_ref": _text(base.get("ref")) or MISSING,
            "changed_files": _int_or_none(pr.get("changed_files")),
            "additions": _int_or_none(pr.get("additions")),
            "deletions": _int_or_none(pr.get("deletions")),
            "html_url": _text(pr.get("html_url")),
            "resolution": pr_resolution,
        }
        if pr_section["merged_at"] is None and pr_section["merged"] is not False:
            missing.append("pull_request.merged_at")
        for field in ("head_sha", "head_ref", "base_ref"):
            if pr_section[field] == MISSING:
                missing.append(f"pull_request.{field}")
        if pr_section["changed_files"] is None:
            missing.append("pull_request.changed_files")
        bundle["pull_request"] = pr_section

        declared_head = _declared_head_commit(mission)
        if head_sha is None:
            bundle["commit"] = MISSING
            missing.append("commit.sha")
        else:
            bundle["commit"] = {
                "sha": head_sha,
                "source": "pull_request.head",
                "matches_mission_head": (head_sha == declared_head) if declared_head else "inconclusive",
            }
            if declared_head is None:
                missing.append("mission.result.evidence.head_commit")

    # ---- deliverables ----------------------------------------------------
    files = list(pull_request_files or [])
    digests = deliverable_sha256 or {}
    commit_ref = (
        bundle["commit"]["sha"] if isinstance(bundle["commit"], Mapping) else None
    )
    deliverables: list[dict[str, Any]] = []
    for index, raw in enumerate(files):
        if not isinstance(raw, Mapping):
            raise EvidenceBundleError(f"pull_request file #{index} is not an object")
        path = _text(raw.get("filename"))
        if not path:
            raise EvidenceBundleError(f"pull_request file #{index} has no filename")
        digest, size = digests.get(path, (None, None))
        entry = {
            "path": path,
            "status": _text(raw.get("status")) or MISSING,
            "additions": _int_or_none(raw.get("additions")),
            "deletions": _int_or_none(raw.get("deletions")),
            "blob_sha": _text(raw.get("sha")),
            "sha256": digest if isinstance(digest, str) and len(digest) == 64 else MISSING,
            "bytes": _int_or_none(size),
            "origin": (
                f"github_contents@{commit_ref}"
                if isinstance(digest, str) and isinstance(commit_ref, str)
                else "unavailable"
            ),
        }
        if entry["sha256"] == MISSING:
            missing.append(f"deliverables[{index}]({path}).sha256")
        if entry["bytes"] is None:
            missing.append(f"deliverables[{index}]({path}).bytes")
        deliverables.append(entry)
    bundle["deliverables"] = deliverables
    if not deliverables:
        missing.append("deliverables")

    # ---- CI --------------------------------------------------------------
    runs_payload = check_runs if isinstance(check_runs, Mapping) else None
    statuses_payload = commit_statuses if isinstance(commit_statuses, Mapping) else None
    if runs_payload is None and statuses_payload is None:
        bundle["ci"] = MISSING
        missing.append("ci.conclusion")
    else:
        runs = [
            {
                "name": _text(run.get("name")) or "unnamed",
                "status": _text(run.get("status")),
                "conclusion": _text(run.get("conclusion")),
            }
            for run in (runs_payload or {}).get("check_runs", [])
            if isinstance(run, Mapping)
        ]
        statuses = [
            {"context": _text(item.get("context")) or "unnamed", "state": _text(item.get("state"))}
            for item in (statuses_payload or {}).get("statuses", [])
            if isinstance(item, Mapping)
        ]
        bundle["ci"] = {
            "conclusion": summarize_ci(runs, statuses),
            "check_runs": runs,
            "statuses": statuses,
            "total_count": _int_or_none((runs_payload or {}).get("total_count")) or len(runs),
        }
        if bundle["ci"]["conclusion"] == "not_run":
            missing.append("ci.check_runs")

    bundle["source_fingerprints"] = {
        "platform_mission": sha256_payload(mission),
        "pull_request": sha256_payload(pull_request if pull_request is not None else None),
        "pull_request_files": sha256_payload(list(pull_request_files) if pull_request_files is not None else None),
        "check_runs": sha256_payload(check_runs if check_runs is not None else None),
        "commit_statuses": sha256_payload(commit_statuses if commit_statuses is not None else None),
    }
    bundle["missing"] = sorted(set(missing))
    return seal(bundle)