#!/usr/bin/env python3
"""Verify the BE publication: STATUS.json claim <-> review receipt <-> maturity-ledger row.

Mission m22925 publishes ``products/STATUS.json`` BE ``scenario_validated=true``. A published
claim is only worth the evidence it can be re-bound to, so this script re-derives every binding
from primary sources instead of trusting the numbers written in the record:

1. ``maturity_verdict_ref`` in the status file resolves to a real ledger row, and that row's own
   evidence (receipt path, verdict, independence, checks_not_run, reviewed_commit, rerun exit)
   agrees with the status file and with the receipt bytes on ``origin/main``.
2. Every ``<repo>@<commit>:<path>#sha256:<sha>`` ref in ``acceptance_evidence`` resolves: the
   commit exists on ``origin/main``, the path exists at that commit, and the blob's bytes hash to
   the declared sha256.
3. ``criteria_sha256`` equals the raw byte sha256 of the frozen criteria file at the reviewed
   commit (``criteria_freeze.json#criteria_sha256`` agrees as well).
4. The six-check receipt has no unresolved preconditions: ``verdict=pass``, ``checks_not_run=[]``,
   ``blocking_conditions=[]``, all six checks ``passed``, ``rerun.exit_code=0``, independence
   declared and not a self review.

Reads only. ``--json`` prints a machine-readable report; ``--skip-db`` drops the ledger step
(useful where the platform database is not reachable).

    python3 docs/m22925/check_verdict_row.py [--json] [--skip-db]
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATUS = ROOT / "products" / "STATUS.json"
DB = ["psql", "-d", "tensorplatform", "-U", "ship", "-At", "-F", "\t"]
REF_PATTERN = re.compile(r"^(?P<repo>[^@]+)@(?P<commit>[0-9a-f]{40}):(?P<path>.+?)#sha256:(?P<sha>[0-9a-f]{64})$")
VERDICT_REF_PATTERN = re.compile(r"#id=(?P<id>\d+)")
SIX_CHECKS = (
    "artifact_identity",
    "criteria_frozen_before_run",
    "evidence_traceability",
    "independent_rerun",
    "failure_record",
    "regression_scope",
)
NON_INDEPENDENT = {"self_review", "same_owner"}


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)


def blob(commit: str, path: str) -> bytes:
    proc = subprocess.run(["git", "-C", str(ROOT), "show", f"{commit}:{path}"], capture_output=True)
    if proc.returncode != 0:
        raise SystemExit(f"cannot read {commit}:{path}: {proc.stderr.decode()[:200]}")
    return proc.stdout


def be_product() -> dict:
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    return next(p for p in status["products"] if p["id"] == "BE")


def check_refs(product: dict) -> list[dict]:
    results = []
    for field in ("validation_report_ref", "review_receipt_ref"):
        ref = product["acceptance_evidence"][field]
        match = REF_PATTERN.match(ref or "")
        if not match:
            results.append({"check": f"ref.{field}", "state": "failed", "note": f"not a pinned ref: {ref!r}"})
            continue
        parts = match.groupdict()
        ancestor = git("merge-base", "--is-ancestor", parts["commit"], "origin/main")
        exists = git("cat-file", "-e", f"{parts['commit']}:{parts['path']}")
        import hashlib
        digest = hashlib.sha256(blob(parts["commit"], parts["path"])).hexdigest() if exists.returncode == 0 else None
        ok = ancestor.returncode == 0 and digest == parts["sha"]
        results.append({
            "check": f"ref.{field}",
            "state": "passed" if ok else "failed",
            "commit_on_main": ancestor.returncode == 0,
            "path_at_commit": exists.returncode == 0,
            "declared_sha256": parts["sha"],
            "recomputed_sha256": digest,
            "note": f"{parts['repo']}@{parts['commit'][:8]}:{parts['path']}",
        })
    return results


def check_criteria(product: dict) -> dict:
    import hashlib
    commit = product["acceptance_evidence"]["reviewed_commit"]
    criteria_path = "docs/pilots/BP-20261115-tensorai-bp-field-extraction/criteria_v1.md"
    freeze_path = "docs/pilots/BP-20261115-tensorai-bp-field-extraction/criteria_freeze.json"
    digest = hashlib.sha256(blob(commit, criteria_path)).hexdigest()
    freeze = json.loads(blob(commit, freeze_path))
    ok = digest == product["acceptance_evidence"]["criteria_sha256"] == freeze["criteria_sha256"]
    return {
        "check": "criteria_sha256",
        "state": "passed" if ok else "failed",
        "recomputed": digest,
        "status_declared": product["acceptance_evidence"]["criteria_sha256"],
        "freeze_declared": freeze["criteria_sha256"],
    }


def check_receipt(product: dict) -> dict:
    import hashlib
    ref = REF_PATTERN.match(product["acceptance_evidence"]["review_receipt_ref"]).groupdict()
    receipt = json.loads(blob(ref["commit"], ref["path"]))
    states = {c["check_id"]: c["state"] for c in receipt.get("six_checks", [])}
    rerun_exit = (receipt.get("rerun") or {}).get("exit_code")
    problems = []
    if receipt.get("verdict") != "pass":
        problems.append(f"verdict={receipt.get('verdict')!r}")
    if receipt.get("checks_not_run") != []:
        problems.append(f"checks_not_run={receipt.get('checks_not_run')!r}")
    if receipt.get("blocking_conditions") != []:
        problems.append(f"blocking_conditions={receipt.get('blocking_conditions')!r}")
    missing = [name for name in SIX_CHECKS if states.get(name) != "passed"]
    if missing:
        problems.append("six_checks not all passed: " + ", ".join(missing))
    if rerun_exit != 0:
        problems.append(f"rerun.exit_code={rerun_exit!r}")
    independence = str(receipt.get("independence") or "").strip()
    if not independence or independence in NON_INDEPENDENT or independence.startswith("self"):
        problems.append(f"independence={independence!r}")
    if receipt.get("reviewed_commit") != product["acceptance_evidence"]["reviewed_commit"]:
        problems.append("receipt.reviewed_commit != status.acceptance_evidence.reviewed_commit")
    return {
        "check": "review_receipt_preconditions",
        "state": "passed" if not problems else "failed",
        "problems": problems,
        "six_checks": states,
        "rerun_exit_code": rerun_exit,
        "independence": independence,
        "receipt_sha256": hashlib.sha256(blob(ref["commit"], ref["path"])).hexdigest(),
        "amendments": len(receipt.get("amendments") or []),
    }


def check_ledger(product: dict) -> dict:
    ref = product["acceptance_evidence"].get("maturity_verdict_ref") or ""
    match = VERDICT_REF_PATTERN.search(ref)
    if not match:
        return {"check": "maturity_verdict_row", "state": "failed", "note": f"no row id in {ref!r}"}
    row_id = int(match.group("id"))
    query = (
        "select id, repo, mission_id, level, gate_state, "
        "coalesce(evidence->>'receipt',''), coalesce(evidence->>'verdict',''), "
        "coalesce(evidence->>'reviewed_commit',''), coalesce(evidence->>'independence',''), "
        "coalesce(evidence->>'rerun_exit',''), evidence->'checks_not_run' "
        f"from tensor_maturity_verdicts where id = {row_id}"
    )
    proc = subprocess.run(DB + ["-c", query], capture_output=True, text=True)
    if proc.returncode != 0:
        return {"check": "maturity_verdict_row", "state": "unknown",
                "note": f"database unreachable: {proc.stderr.strip()[:200]}"}
    line = proc.stdout.strip()
    if not line:
        return {"check": "maturity_verdict_row", "state": "failed",
                "note": f"ledger row id={row_id} does not exist"}
    (rid, repo, mission, level, gate, receipt, verdict, commit, independence,
     rerun_exit, checks_not_run) = line.split("\t")
    receipt_path = REF_PATTERN.match(product["acceptance_evidence"]["review_receipt_ref"]).group("path")
    problems = []
    if repo != "TensorBench":
        problems.append(f"repo={repo!r}")
    if mission != "22060":
        problems.append(f"mission_id={mission!r} (pilot mission is 22060)")
    if level != "3":
        problems.append(f"level={level!r} (published record states level 3)")
    if verdict != "pass":
        problems.append(f"verdict={verdict!r}")
    if receipt != receipt_path:
        problems.append(f"row receipt={receipt!r} != status receipt path")
    if commit != product["acceptance_evidence"]["reviewed_commit"]:
        problems.append("row reviewed_commit != status reviewed_commit")
    if independence and independence not in {"independent", "independent_party"}:
        problems.append(f"independence={independence!r}")
    if checks_not_run not in {"[]", ""}:
        problems.append(f"checks_not_run={checks_not_run!r}")
    if rerun_exit not in {"0", ""}:
        problems.append(f"rerun_exit={rerun_exit!r}")
    return {
        "check": "maturity_verdict_row",
        "state": "passed" if not problems else "failed",
        "problems": problems,
        "row": {"id": int(rid), "repo": repo, "mission_id": int(mission), "level": int(level),
                "gate_state": gate, "verdict": verdict, "reviewed_commit": commit},
    }


def main(argv: list[str]) -> int:
    product = be_product()
    report = {
        "product": "BE",
        "scenario_validated": product["scenario_validated"],
        "code_implemented": product["code_implemented"],
        "checks": [*check_refs(product), check_criteria(product), check_receipt(product)],
    }
    if "--skip-db" not in argv[1:]:
        report["checks"].append(check_ledger(product))
    else:
        report["checks"].append({"check": "maturity_verdict_row", "state": "not_run",
                                 "note": "--skip-db"})
    blocking = [c for c in report["checks"] if c["state"] == "failed"]
    report["verdict"] = "failed" if blocking else ("passed" if all(
        c["state"] == "passed" for c in report["checks"]) else "partial")
    if "--json" in argv[1:]:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for check in report["checks"]:
            print(f"[{check['state']:>7}] {check['check']}"
                  + (f"  problems={check.get('problems')}" if check.get("problems") else ""))
        print(f"verdict: {report['verdict']}")
    return 0 if report["verdict"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))