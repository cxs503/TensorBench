"""Unavailable integration dependencies are distinct from passing evidence."""
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def pv():
    return load_module("pv_portability", ROOT / "tests/test_pv_scenario_publish.py")


def deny_git_entry(monkeypatch):
    original = Path.stat

    def stat(path, *args, **kwargs):
        if path.name == ".git":
            raise PermissionError("checkout inaccessible")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", stat)


def test_pv_module_can_be_collected_without_probing_checkout(monkeypatch):
    deny_git_entry(monkeypatch)
    module = load_module("pv_collection_regression", ROOT / "tests/test_pv_scenario_publish.py")
    assert callable(module.test_published_status_is_valid_via_module_entry_point)


@pytest.mark.parametrize("inaccessible", [False, True])
def test_absent_optional_checkout_is_explicitly_skipped(pv, tmp_path, monkeypatch, inaccessible):
    monkeypatch.delenv("TENSORDATA_REPO", raising=False)
    monkeypatch.setattr(pv, "ROOT", tmp_path / "TensorBench")
    if inaccessible:
        deny_git_entry(monkeypatch)
    with pytest.raises(pytest.skip.Exception, match="TensorData checkout unavailable"):
        pv._resolve_tensordata_repo()


@pytest.mark.parametrize("inaccessible", [False, True])
def test_invalid_explicit_checkout_fails_instead_of_skipping(pv, tmp_path, monkeypatch, inaccessible):
    monkeypatch.setenv("TENSORDATA_REPO", str(tmp_path / "TensorData"))
    if inaccessible:
        deny_git_entry(monkeypatch)
    with pytest.raises(pytest.fail.Exception, match="Invalid TENSORDATA_REPO"):
        pv._resolve_tensordata_repo()


@pytest.mark.parametrize("value", ["", " "])
def test_empty_explicit_checkout_is_invalid(pv, monkeypatch, value):
    monkeypatch.setenv("TENSORDATA_REPO", value)
    with pytest.raises(pytest.fail.Exception, match="empty path"):
        pv._resolve_tensordata_repo()


@pytest.mark.parametrize("worktree", [False, True])
def test_available_checkout_preserves_commit_pinning(pv, tmp_path, monkeypatch, worktree):
    repo = tmp_path / "TensorData"

    def git(*args):
        return subprocess.run(["git", "-C", str(repo), *args], check=True,
                              capture_output=True, text=True, timeout=10).stdout.strip()

    repo.mkdir()
    git("init", "-q")
    (repo / "receipt.json").write_bytes(b'{"original": true}\n')
    git("add", ".")
    git("-c", "user.name=Portability test", "-c", "user.email=test@invalid",
        "commit", "-qm", "Test fixture")
    commit = git("rev-parse", "HEAD")
    (repo / "receipt.json").write_bytes(b'{"original": false}\n')
    checkout = repo
    if worktree:
        checkout = tmp_path / "data-worktree"
        git("worktree", "add", "--detach", str(checkout), commit)
        assert (checkout / ".git").is_file()
    monkeypatch.setenv("TENSORDATA_REPO", str(checkout))
    resolved = pv._resolve_tensordata_repo()
    assert resolved == checkout.resolve()
    assert pv._git_show(resolved, f"{commit}:receipt.json") == b'{"original": true}\n'
    # Present but incomplete history is a verification failure, never a skip.
    with pytest.raises(subprocess.CalledProcessError):
        pv._git_show(resolved, f"{commit}:absent.json")


@pytest.fixture
def checker():
    return load_module("be_portability", ROOT / "docs/m22925/check_verdict_row.py")


@pytest.mark.parametrize("error", [FileNotFoundError(), PermissionError(),
    subprocess.TimeoutExpired("psql", 15)])
def test_missing_or_stalled_database_client_is_unknown(checker, monkeypatch, error):
    def unavailable(*args, **kwargs):
        assert kwargs["timeout"] == 15
        raise error

    monkeypatch.setattr(checker.subprocess, "run", unavailable)
    result = checker.check_ledger(checker.be_product())
    assert result["state"] == "unknown"
    assert type(error).__name__ in result["note"]


def test_unknown_database_keeps_cli_verdict_partial(checker, monkeypatch, capsys):
    for name in ("check_criteria", "check_receipt"):
        monkeypatch.setattr(checker, name, lambda p: {"check": "local", "state": "passed"})
    monkeypatch.setattr(checker, "check_refs", lambda p: [])

    def unavailable(*args, **kwargs):
        raise FileNotFoundError("psql")

    monkeypatch.setattr(checker.subprocess, "run", unavailable)
    assert checker.main(["check_verdict_row.py", "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["verdict"] == "partial"


@pytest.mark.parametrize("row_kind,expected", [
    ("valid", "passed"), ("missing", "failed"), ("mismatch", "failed"),
    ("unreachable", "unknown"),
])
def test_database_results_are_not_downgraded_to_unavailability(checker, monkeypatch, row_kind, expected):
    product = checker.be_product()
    evidence = product["acceptance_evidence"]
    path = checker.REF_PATTERN.match(evidence["review_receipt_ref"]).group("path")
    columns = ["911", "TensorBench", "22060", "3", "passed", path, "pass",
               evidence["reviewed_commit"], "independent_party", "0", "[]"]
    if row_kind == "mismatch":
        columns[1] = "unrelated-repository"
    stdout = "" if row_kind == "missing" else "\t".join(columns) + "\n"
    response = subprocess.CompletedProcess([], 1 if row_kind == "unreachable" else 0,
                                           stdout, "connection refused")
    monkeypatch.setattr(checker.subprocess, "run", lambda *a, **k: response)
    result = checker.check_ledger(product)
    assert result["state"] == expected
    if row_kind == "mismatch":
        assert any("repo=" in problem for problem in result["problems"])
