"""Read-only TensorPlatform + GitHub evidence collection for AE-01.

Two upstreams, both read-only:

* TensorPlatform (``http://127.0.0.1:8010`` by default): mission metadata via
  ``GET {api}/tensor/missions/{id}``. Authentication follows the platform login
  convention documented by the backend (``POST {api}/auth/login`` with the
  credentials in ``/root/.eco_admin_creds.json``); the bearer token lives only
  in memory and is never written into an evidence bundle.
* GitHub (``api.github.com``): the PR whose head branch is ``agent/m<id>``
  (falling back to the PR that contains the mission-declared head commit), that
  PR's exact head commit, its changed files, and the CI check-runs/commit
  statuses for that commit. The token is read from ``/root/.git-credentials``
  (the same ``https://x-access-token:<token>@github.com`` convention used by
  the platform pusher) and is likewise never persisted.

Deliverable fingerprints are computed from the file bytes retrieved at the
pinned commit (``GET /repos/{repo}/contents/{path}?ref={sha}``). When a file is
too large or unavailable the fingerprint is recorded as ``missing``; the bytes
are never approximated.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from . import evidence_bundle as bundle_model

DEFAULT_PLATFORM_API_BASE = "http://127.0.0.1:8010"
DEFAULT_CREDS_FILE = "/root/.eco_admin_creds.json"
DEFAULT_GIT_CREDENTIALS = "/root/.git-credentials"
DEFAULT_GITHUB_OWNER = "cxs503"
GITHUB_API = "https://api.github.com"
MAX_CONTENT_BYTES = 1_000_000  # GitHub contents API returns inline content below 1 MB
CONTENT_RECORD_LIMIT = 128_000  # per-file cap when recording replay fixtures
CONTENT_RECORD_BUDGET = 512_000  # per-mission cap when recording replay fixtures


class CollectorError(RuntimeError):
    """Any failure that prevents a complete, honest evidence bundle."""


class MissionNotFoundError(CollectorError):
    """The requested mission id does not exist on the platform."""


class CollectorAuthError(CollectorError):
    """Platform or GitHub authentication could not be established."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def collector_version() -> str:
    try:
        from . import __version__ as version  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - namespace fallback
        version = "0.1.0"
    return str(version)


# --------------------------------------------------------------------------
# transport (module-level seam so contract tests can replay recorded payloads)
# --------------------------------------------------------------------------
def _request_json(
    url: str,
    token: str | None = None,
    *,
    accept: str = "application/vnd.github+json",
    method: str = "GET",
    body: Mapping[str, Any] | None = None,
) -> Any:
    headers = {"Accept": accept, "User-Agent": "TensorBench-AE01-Collector"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, headers=headers, method=method, data=data)
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read(2000).decode("utf-8", errors="replace")
        error = MissionNotFoundError if exc.code == 404 else CollectorError
        raise error(f"{method} {urlsplit(url).path} returned HTTP {exc.code}: {detail}") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise CollectorError(f"{method} {urlsplit(url).path} failed: {exc}") from exc


def _pages(url: str, token: str | None, *, page_limit: int = 10) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for page in range(1, page_limit + 1):
        separator = "&" if "?" in url else "?"
        batch = _request_json(f"{url}{separator}per_page=100&page={page}", token)
        if not isinstance(batch, list):
            raise CollectorError(f"expected an array from {urlsplit(url).path}")
        rows.extend(item for item in batch if isinstance(item, Mapping))
        if len(batch) < 100:
            return rows
    raise CollectorError(f"pagination limit exceeded for {urlsplit(url).path}")


# --------------------------------------------------------------------------
# credentials
# --------------------------------------------------------------------------
def platform_api_root(api_base: str) -> str:
    """Normalize a platform base URL to include the ``/api/v1`` API prefix."""
    base = api_base.rstrip("/")
    parsed = urlsplit(base)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise CollectorError("platform API base must be an absolute HTTP(S) URL")
    if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise CollectorError("platform API base must use HTTPS outside localhost")
    return base if parsed.path.rstrip("/").endswith("/api/v1") else f"{base}/api/v1"


def load_platform_credentials(path: str | os.PathLike[str] | None = None) -> tuple[str, str]:
    creds_path = Path(path or DEFAULT_CREDS_FILE)
    if not creds_path.is_file():
        raise CollectorAuthError(f"platform credentials file not found: {creds_path}")
    try:
        payload = json.loads(creds_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CollectorAuthError(f"cannot read platform credentials: {exc}") from exc
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")
    if not username or not password:
        raise CollectorAuthError("platform credentials must contain username and password")
    return username, password


def platform_login(api_base: str, *, creds_file: str | os.PathLike[str] | None = None) -> str:
    username, password = load_platform_credentials(creds_file)
    url = f"{platform_api_root(api_base)}/auth/login"
    payload = _request_json(
        url,
        accept="application/json",
        method="POST",
        body={"username": username, "password": password},
    )
    token = payload.get("access_token") if isinstance(payload, Mapping) else None
    if not isinstance(token, str) or not token:
        raise CollectorAuthError("platform login did not return an access_token")
    return token


def load_github_token(path: str | os.PathLike[str] | None = None) -> str:
    """Extract the token half of the ``https://user:token@github.com`` credential line."""
    creds_path = Path(path or DEFAULT_GIT_CREDENTIALS)
    if not creds_path.is_file():
        raise CollectorAuthError(f"git credentials file not found: {creds_path}")
    text = creds_path.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"https://([^:\s/]+):([^@\s]+)@github\.com", text)
    if not match:
        raise CollectorAuthError("git credentials contain no https://user:token@github.com entry")
    return match.group(2)


# --------------------------------------------------------------------------
# upstream readers
# --------------------------------------------------------------------------
def fetch_mission(api_base: str, mission_id: int, token: str) -> tuple[dict[str, Any], str]:
    endpoint = f"/tensor/missions/{int(mission_id)}"
    url = f"{platform_api_root(api_base)}{endpoint}"
    try:
        payload = _request_json(url, token, accept="application/json")
    except MissionNotFoundError as exc:
        raise MissionNotFoundError(f"TensorPlatform mission {mission_id} does not exist: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise CollectorError("TensorPlatform mission payload is not an object")
    return dict(payload), endpoint


def resolve_repository(mission: Mapping[str, Any], owner: str) -> str:
    repo_value = str(mission.get("repo") or "").strip()
    if not repo_value:
        raise CollectorError("mission payload has no repository name")
    repo = repo_value if "/" in repo_value else f"{owner}/{repo_value}"
    if len(repo.split("/")) != 2:
        raise CollectorError("mission repository must resolve to owner/repository")
    return repo


def find_pull_request(
    repo: str,
    mission_id: int,
    github_token: str,
    *,
    declared_head_commit: str | None = None,
) -> tuple[dict[str, Any] | None, str]:
    """Return ``(pull_request, resolution)`` for ``head=agent/m<id>``.

    Falls back to the PR that contains the mission-declared head commit when the
    branch has been deleted, so the association stays commit-exact.
    """
    branch = f"agent/m{int(mission_id)}"
    owner = repo.split("/")[0]
    url = f"{GITHUB_API}/repos/{quote(repo, safe='/')}/pulls?state=all&head={quote(f'{owner}:{branch}', safe='')}"
    try:
        candidates = _pages(url, github_token, page_limit=1)
    except MissionNotFoundError as exc:
        raise CollectorError(f"GitHub repository {repo} is not readable: {exc}") from exc
    exact = [item for item in candidates if str((item.get("head") or {}).get("ref")) == branch]
    if exact:
        pr = max(exact, key=lambda item: int(item.get("number") or 0))
        return dict(pr), "branch_head"
    if declared_head_commit:
        associated = _pages(
            f"{GITHUB_API}/repos/{quote(repo, safe='/')}/commits/{quote(declared_head_commit, safe='')}/pulls",
            github_token,
        )
        matching = [
            item for item in associated
            if str((item.get("head") or {}).get("sha")) == declared_head_commit
        ]
        if len(matching) == 1:
            return dict(matching[0]), "commit_association"
        if len(matching) > 1:
            raise CollectorError(
                f"{len(matching)} PRs claim mission commit {declared_head_commit}; refusing to guess"
            )
    return None, "not_found"


def fetch_pull_request_detail(repo: str, number: int, github_token: str) -> dict[str, Any]:
    payload = _request_json(
        f"{GITHUB_API}/repos/{quote(repo, safe='/')}/pulls/{int(number)}", github_token
    )
    if not isinstance(payload, Mapping):
        raise CollectorError("GitHub pull request payload is not an object")
    return dict(payload)


def fetch_pull_request_files(repo: str, number: int, github_token: str) -> list[dict[str, Any]]:
    return _pages(f"{GITHUB_API}/repos/{quote(repo, safe='/')}/pulls/{int(number)}/files", github_token)


def fetch_ci(repo: str, sha: str, github_token: str) -> tuple[dict[str, Any], dict[str, Any]]:
    root = f"{GITHUB_API}/repos/{quote(repo, safe='/')}/commits/{quote(sha, safe='')}"
    runs = _request_json(f"{root}/check-runs?per_page=100", github_token)
    statuses = _request_json(f"{root}/status", github_token)
    if not isinstance(runs, Mapping) or not isinstance(statuses, Mapping):
        raise CollectorError("GitHub CI payloads are not objects")
    return dict(runs), dict(statuses)


def fetch_file_stats(
    repo: str, path: str, ref: str, github_token: str
) -> tuple[str | None, int | None, bytes | None]:
    """``(sha256, size, raw_bytes)`` of the file at ``ref``.

    ``(None, None, None)`` means the path is not a fingerprintable file (a
    directory or an unreadable entry); ``(None, size, None)`` means the content
    exists but is too large to inline, so the fingerprint is genuinely unknown.
    """
    url = f"{GITHUB_API}/repos/{quote(repo, safe='/')}/contents/{quote(path, safe='/')}?ref={quote(ref, safe='')}"
    try:
        payload = _request_json(url, github_token)
    except CollectorError:
        return None, None, None
    if not isinstance(payload, Mapping):
        return None, None, None  # directory or unexpected shape
    size = payload.get("size")
    content = payload.get("content")
    encoding = payload.get("encoding")
    if not isinstance(size, int) or size > MAX_CONTENT_BYTES:
        return None, size if isinstance(size, int) else None, None
    if encoding != "base64" or not isinstance(content, str) or not content:
        return None, size, None
    try:
        raw = base64.b64decode(content)
    except (ValueError, TypeError):
        return None, size, None
    if len(raw) != size:
        return None, size, None
    return hashlib.sha256(raw).hexdigest(), size, raw


def fetch_file_sha256(
    repo: str, path: str, ref: str, github_token: str
) -> tuple[str | None, int | None]:
    """SHA-256 of the file bytes at ``ref``; ``(None, None)`` when not retrievable."""
    digest, size, _ = fetch_file_stats(repo, path, ref, github_token)
    return digest, size


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
        if isinstance(candidate, str) and bundle_model._is_commit_sha(candidate):
            return candidate
    return None


def collect_mission_evidence(
    mission_id: int,
    *,
    platform_api_base: str | None = None,
    github_owner: str = DEFAULT_GITHUB_OWNER,
    creds_file: str | os.PathLike[str] | None = None,
    github_credentials: str | os.PathLike[str] | None = None,
    platform_token: str | None = None,
    github_token: str | None = None,
    max_deliverables: int = 25,
    fetch_contents: bool = True,
    collected_at: str | None = None,
    raw_sink: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Collect one mission's evidence bundle. Read-only; never mutates upstream state."""
    api_base = platform_api_base or os.environ.get("TENSORPLATFORM_API_BASE") or DEFAULT_PLATFORM_API_BASE
    timestamp = collected_at or utc_now()
    token = platform_token or platform_login(api_base, creds_file=creds_file)
    mission, endpoint = fetch_mission(api_base, mission_id, token)
    repo = resolve_repository(mission, github_owner)
    gh_token = github_token or load_github_token(github_credentials)

    pr, resolution = find_pull_request(
        repo, mission_id, gh_token, declared_head_commit=_declared_head_commit(mission)
    )
    files: list[dict[str, Any]] = []
    checks: dict[str, Any] | None = None
    statuses: dict[str, Any] | None = None
    deliverable_digests: dict[str, tuple[str | None, int | None]] = {}
    recorded_contents: dict[str, Any] = {}
    if pr is not None:
        number = int(pr.get("number"))
        pr = fetch_pull_request_detail(repo, number, gh_token)
        files = fetch_pull_request_files(repo, number, gh_token)
        head_sha = str((pr.get("head") or {}).get("sha") or "")
        if bundle_model._is_commit_sha(head_sha):
            checks, statuses = fetch_ci(repo, head_sha, gh_token)
            if fetch_contents:
                recorded_budget = 0
                for item in files[:max_deliverables]:
                    path = str(item.get("filename") or "")
                    if not path:
                        continue
                    digest, size, raw = fetch_file_stats(repo, path, head_sha, gh_token)
                    deliverable_digests[path] = (digest, size)
                    if (
                        raw_sink is not None
                        and raw is not None
                        and len(raw) <= CONTENT_RECORD_LIMIT
                        and recorded_budget + len(raw) <= CONTENT_RECORD_BUDGET
                    ):
                        recorded_budget += len(raw)
                        recorded_contents[path] = {
                            "sha256": digest,
                            "size": size,
                            "content_b64": base64.b64encode(raw).decode("ascii"),
                        }

    if raw_sink is not None:
        raw_sink.update({
            "platform_api_base": platform_api_root(api_base),
            "mission_endpoint": endpoint,
            "github_repository": repo,
            "pr_resolution": resolution,
            "mission": mission,
            "pull_request": pr,
            "pull_request_files": files,
            "check_runs": checks,
            "commit_statuses": statuses,
            "collected_at": timestamp,
            "deliverable_contents": recorded_contents,
        })

    return bundle_model.build_evidence_bundle(
        mission_id=mission_id,
        mission=mission,
        platform_api_base=platform_api_root(api_base),
        mission_endpoint=endpoint,
        collected_at=timestamp,
        collector_version=collector_version(),
        github_repository=repo,
        pull_request=pr,
        pull_request_files=files,
        check_runs=checks,
        commit_statuses=statuses,
        deliverable_sha256=deliverable_digests,
        pr_resolution=resolution,
    )


def parse_mission_ids(raw: str) -> list[int]:
    """Parse ``m1,m2`` / ``1,2`` / ``m1 m2`` into unique positive ints, order preserved."""
    ids: list[int] = []
    for chunk in re.split(r"[,\s]+", str(raw or "").strip()):
        if not chunk:
            continue
        token = chunk[1:] if chunk[0] in "mM" else chunk
        if not token.isdigit():
            raise CollectorError(f"invalid mission id: {chunk!r} (expected m<digits>)")
        value = int(token)
        if value <= 0:
            raise CollectorError(f"invalid mission id: {chunk!r}")
        if value not in ids:
            ids.append(value)
    if not ids:
        raise CollectorError("no mission ids given")
    return ids


def collect_missions(
    mission_ids: list[int],
    *,
    out_dir: str | os.PathLike[str] = "evidence",
    **kwargs: Any,
) -> dict[str, Any]:
    """Collect each mission and write ``<out_dir>/<mission_id>.json``.

    Failures are isolated per mission: successful bundles are still written so a
    single dead mission id cannot destroy the run's genuine evidence.
    """
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    for mission_id in mission_ids:
        target = out_path / f"{mission_id}.json"
        try:
            bundle = collect_mission_evidence(mission_id, **kwargs)
        except CollectorError as exc:
            results.append({"mission_id": mission_id, "status": "error", "error": str(exc)})
            continue
        target.write_text(json.dumps(bundle, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        results.append({
            "mission_id": mission_id,
            "status": "collected",
            "path": str(target),
            "bundle_sha256": bundle["integrity"]["bundle_sha256"],
            "pr": None if bundle["pull_request"] == bundle_model.MISSING else bundle["pull_request"]["number"],
            "ci": None if bundle["ci"] == bundle_model.MISSING else bundle["ci"]["conclusion"],
            "deliverables": len(bundle["deliverables"]),
            "missing": bundle["missing"],
        })
    return {
        "out_dir": str(out_path),
        "collected_at": utc_now(),
        "missions": results,
        "failed": [item["mission_id"] for item in results if item["status"] == "error"],
    }