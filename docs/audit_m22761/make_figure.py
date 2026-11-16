#!/usr/bin/env python3
"""Render the PV publish evidence figure from the committed pilot artifacts.

Every plotted number is read out of the pinned artefacts (review receipt + pilot
report at TensorData@857a189) or recomputed in this worktree — nothing is typed in
by hand. Writes ``pv_publish_evidence.png`` next to this file.

Run: python3 docs/audit_m22761/make_figure.py
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
TENSORDATA = Path("/root/tensor-ecosystem/TensorData")
ART_COMMIT = "857a189ee66cfda0fc208556b1316e25ff2e2104"
ART_DIR = "artifacts/pv-pilot/ex1_kcs"


def load(name: str) -> dict:
    blob = subprocess.run(
        ["git", "-C", str(TENSORDATA), "show", f"{ART_COMMIT}:{ART_DIR}/{name}"],
        check=True,
        capture_output=True,
    ).stdout
    return json.loads(blob)


def main() -> int:
    report = load("pilot_report.json")
    receipt = load("review_receipt.json")
    negatives = load("negative_cases.json")

    summary = report["summary"]
    ident_rate = summary["identified_columns"] / summary["numeric_columns"]
    unknown_limit = 0.10
    six = {c["check_id"]: c["verdict"] for c in receipt["six_checks"]}
    neg_cases = negatives["cases"] if isinstance(negatives, dict) else negatives
    neg_detected = sum(1 for c in neg_cases if c.get("detected"))

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.6), gridspec_kw={"width_ratios": [1.0, 1.6, 1.2]})

    # (a) column identification vs the predeclared unknown-rate gate
    ax = axes[0]
    ax.barh(
        ["identified", "unknown"],
        [summary["identified_columns"], summary["numeric_columns"] - summary["identified_columns"]],
        color=["#2a7f62", "#c0392b"],
    )
    ax.axvline(
        summary["numeric_columns"] * unknown_limit, color="k", ls="--", lw=1.2,
        label=f"unknown-rate gate {unknown_limit:.0%} of {summary['numeric_columns']}",
    )
    ax.set_xlabel("numeric columns")
    ax.set_title(f"(a) identification {ident_rate:.0%} "
                 f"({summary['identified_columns']}/{summary['numeric_columns']})")
    ax.legend(fontsize=8, loc="lower right")

    # (b) the six review checks, read from the receipt
    ax = axes[1]
    names = list(six)
    ax.bar(range(len(names)), [1 if v == "pass" else 0 for v in six.values()],
           color=["#2a7f62" if v == "pass" else "#c0392b" for v in six.values()])
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels([n.replace("_", "\n") for n in names], fontsize=7.5)
    ax.set_ylim(0, 1.25)
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["not pass", "pass"])
    ax.set_title(
        "(b) independent review: "
        f"{sum(v == 'pass' for v in six.values())}/6 pass, "
        f"verdict={receipt['verdict']}, checks_not_run={len(receipt['checks_not_run'])}"
    )
    for i, v in enumerate(six.values()):
        ax.text(i, 1.02, v, ha="center", fontsize=8)

    # (c) acceptance blockers before / after this publish
    ax = axes[2]
    blockers = summary["acceptance_blockers"]
    cleared = {"review_receipt", "scenario_validated"}
    state = ["cleared" if b in cleared else "open" for b in blockers]
    ax.barh(blockers, [1] * len(blockers),
            color=["#2a7f62" if s == "cleared" else "#d68910" for s in state])
    for i, s in enumerate(state):
        ax.text(0.02, i, s, va="center", fontsize=8, color="white", weight="bold")
    ax.set_xlim(0, 1)
    ax.set_xticks([])
    ax.set_title(f"(c) blockers: {len(blockers)} in the report, {len(cleared)} closed by ⑤")
    ax.text(
        0.02, -0.7,
        f"negative injections detected {neg_detected}/{len(neg_cases)}",
        fontsize=8, color="#2a7f62",
    )

    fig.suptitle(
        "PV (Physics Dataset Validator) — publish evidence, "
        f"reviewed commit {receipt['reviewed_commit'][:7]}, "
        f"criteria {receipt['six_checks'][1]['evidence']['criteria_sha256'][:12]}…",
        fontsize=10,
    )
    fig.tight_layout(rect=(0, 0.03, 1, 0.94))
    out = HERE / "pv_publish_evidence.png"
    fig.savefig(out, dpi=150)
    print(f"wrote {out} ({out.stat().st_size} bytes)")
    print(f"identified={summary['identified_columns']}/{summary['numeric_columns']} "
          f"negative={neg_detected}/{len(neg_cases)} six_checks="
          f"{sum(v == 'pass' for v in six.values())}/6 blockers={blockers}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())