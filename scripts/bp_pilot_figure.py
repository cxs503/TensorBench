#!/usr/bin/env python3
"""Figure for the BP-20261115 pilot (numbers injected from numbers.json only)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--numbers", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    numbers = json.loads(Path(args.numbers).read_text(encoding="utf-8"))

    fig, axes = plt.subplots(1, 3, figsize=(16.5, 5.2))

    # (A) per-field coverage, both declared spectra.
    coverage = numbers["coverage_per_field"]
    fields = list(coverage)
    counts = [coverage[field] for field in fields]
    colors = ["#2e6f95" if count else "#c44e52" for count in counts]
    axes[0].barh(range(len(fields)), counts, color=colors)
    axes[0].set_yticks(range(len(fields)))
    axes[0].set_yticklabels(fields, fontsize=8)
    axes[0].invert_yaxis()
    axes[0].axvline(0, color="black", linewidth=0.8)
    axes[0].set_xlabel("page-addressable proposals")
    axes[0].set_title(
        f"(A) field coverage: business_plan_v1 {numbers['bp_fields_extracted']}/"
        f"{numbers['bp_fields_declared']} fields, trade_documents_v1 "
        f"{numbers['legacy_fields_extracted']}/{numbers['legacy_fields_declared']}",
        fontsize=10,
    )
    for index, count in enumerate(counts):
        axes[0].text(count + 0.05, index, str(count), va="center", fontsize=8)

    # (B) table arithmetic: funding-use rows and revenue-mix row sums.
    axes[1].axhline(100, color="#c44e52", linestyle="--", linewidth=1.2, label="100 % reference")
    revenue_sums = [entry["sum"] for entry in numbers["revenue_row_sums"]]
    axes[1].scatter([f"revenue row {i + 1}" for i in range(len(revenue_sums))], revenue_sums,
                    marker="s", s=46, color="#2e6f95", label="revenue-mix row sum")
    axes[1].bar(["funding use\n(all rows)"], [numbers["fund_use_sum"]], width=0.45,
                color="#55a868", label=f"funding-use sum ({numbers['fund_use_rows']} rows)")
    axes[1].set_ylim(90, 110)
    axes[1].set_ylabel("sum of extracted percentages")
    axes[1].set_title("(B) arithmetic invariants of the extracted tables", fontsize=10)
    axes[1].legend(fontsize=8, loc="lower right")
    axes[1].grid(axis="y", alpha=0.3)

    # (C) roadmap coverage plus the pass counts of the independent checks.
    windows = numbers["roadmap_windows"]
    for index, (start, end) in enumerate(windows):
        axes[2].barh(index, end - start, left=start, height=0.5,
                     color=plt.cm.viridis(index / max(len(windows) - 1, 1)))
        axes[2].text(start + 0.4, index, f"{start}-{end} mo", va="center", fontsize=8)
    axes[2].set_yticks(range(len(windows)))
    axes[2].set_yticklabels([f"phase {i + 1}" for i in range(len(windows))], fontsize=8)
    axes[2].set_xlim(0, 42)
    axes[2].set_xlabel("months from plan start")
    axes[2].set_title(
        f"(C) roadmap span {numbers['roadmap_span']} months | spot-check "
        f"{numbers['spotcheck_agreed']}/{numbers['spotcheck_checks']} agree | negative path "
        f"{numbers['negative_passed']}/{numbers['negative_cases']} closed",
        fontsize=10,
    )

    fig.suptitle(
        "TensorBench stage-3 pilot: business-plan PDF -> page-addressable business evidence "
        f"(source sha256 {numbers['source_sha256'][:12]}…, {numbers['pages']} pages)",
        fontsize=11,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=150)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())