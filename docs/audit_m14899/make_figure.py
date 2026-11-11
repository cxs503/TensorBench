#!/usr/bin/env python3
"""Figure for the m14899 / KPI-BENCH-10 audit (reads docs/audit_m14899/numbers.json)."""
from __future__ import annotations

import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = json.load(open(os.path.join(HERE, "numbers.json"), encoding="utf-8"))
ROWS = DATA["rows"]


def case_names():
    return ["SUBOFF", "DTMB 5415", "KVLCC2"]


def main() -> None:
    labels = case_names()
    ct_exp = [r["Ct_exp"] for r in ROWS]
    ct_calc = [r["Ct"] for r in ROWS]
    err = [r["err_vs_anchor_pct"] for r in ROWS]
    tol = [r["spec_tolerance_pct"] for r in ROWS]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.2))

    # --- panel 1: Ct_calc vs Ct_exp with +-15% band -----------------------
    x = range(len(labels))
    ax1.errorbar(list(x), ct_exp, yerr=[[0.15 * e for e in ct_exp], [0.15 * e for e in ct_exp]],
                 fmt="o", color="black", capsize=6, label="experimental anchor $\\pm$15%")
    ax1.axhline(0, color="none")
    ax1.plot(list(x), ct_calc, "s", color="crimson", markersize=9, label="replicated $C_t$ (ITTC-78)")
    for i, (e, c) in enumerate(zip(ct_exp, ct_calc)):
        ax1.annotate(f"{100*(c-e)/e:+.1f}%", (i, c), textcoords="offset points",
                     xytext=(10, 6), color="crimson", fontsize=10)
    ax1.set_xticks(list(x))
    ax1.set_xticklabels(labels)
    ax1.set_ylabel("$C_t$ [-]")
    ax1.set_title("Total resistance coefficient: anchor vs replication\n(black bars = platform $\\pm$15% acceptance band)")
    ax1.grid(alpha=0.3)
    ax1.legend(fontsize=9)

    # --- panel 2: error vs the two acceptance thresholds ------------------
    bars = ax2.bar(labels, err, color=["crimson" if abs(e) > 15 else "seagreen" for e in err], width=0.55)
    ax2.axhline(15, color="black", linestyle="--", linewidth=1.2, label="platform standard 15%")
    ax2.plot(labels, tol, "v", color="darkorange", markersize=9, label="spec tolerance (post-hoc)")
    for b, e, t in zip(bars, err, tol):
        ax2.annotate(f"{e:+.1f}%", (b.get_x() + b.get_width() / 2, e), ha="center",
                     va="bottom", fontsize=10)
        ax2.annotate(f"tol {t:.0f}%", (b.get_x() + b.get_width() / 2, -3.5), ha="center",
                     va="top", fontsize=8, color="darkorange")
    ax2.set_ylabel("relative error vs anchor [%]")
    ax2.set_ylim(-6, max(err + tol) * 1.25)
    ax2.set_title("Error vs the 15% platform standard:\n1/3 cases acceptable (KPI case count 3/10)")
    ax2.grid(alpha=0.3, axis="y")
    ax2.legend(fontsize=9)

    fig.suptitle("m14899 / KPI-BENCH-10 audit: independent replication of the TensorBench resistance suite", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    out = os.path.join(HERE, "bench10_audit.png")
    fig.savefig(out, dpi=140)
    print("wrote", out)


if __name__ == "__main__":
    main()