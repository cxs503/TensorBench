#!/usr/bin/env python3
"""Compare benchmark results against experimental reference values and generate figures."""
import json
import glob
import os
import sys

# Add repo root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

CASES = {
    "suboff": {
        "Ct_exp": 0.00315,
        "Fr": 0.2,
        "ref": "Huang et al., DTRC-92/001, 1992",
        "label": "SUBOFF",
    },
    "dtmb5415": {
        "Ct_exp": 0.00380,
        "Fr": 0.28,
        "ref": "Olivieri et al., INSEAN 2001",
        "label": "DTMB 5415",
    },
    "kvlcc2": {
        "Ct_exp": 0.00410,
        "Fr": 0.142,
        "ref": "SIMMAN 2008, MOERI",
        "label": "KVLCC2",
    },
}


def load_results():
    """Load all benchmark result files."""
    results = {}
    repo_root = os.path.join(os.path.dirname(__file__), "../..")
    for case in CASES:
        pattern = os.path.join(repo_root, f"tensorbench-runs/{case}/*.result.json")
        files = glob.glob(pattern)
        if files:
            with open(files[0]) as f:
                results[case] = json.load(f)
    return results


def extract_metrics(results):
    """Extract Ct and Fn from results."""
    data = []
    for case in ["suboff", "dtmb5415", "kvlcc2"]:
        if case not in results:
            continue
        r = results[case]
        ct = fn = cf = None
        for m in r.get("metrics", []):
            if m["name"] == "Ct":
                ct = m["value"]
            elif m["name"] == "Fn":
                fn = m["value"]
            elif m["name"] == "Cf":
                cf = m["value"]
        data.append({
            "case": case,
            "label": CASES[case]["label"],
            "Ct_exp": CASES[case]["Ct_exp"],
            "Ct_calc": ct,
            "Fn": fn,
            "Cf": cf,
            "error_pct": (ct - CASES[case]["Ct_exp"]) / CASES[case]["Ct_exp"] * 100 if ct else None,
            "status": r.get("acceptance", {}).get("status", "unknown"),
            "run_id": r.get("run_id", ""),
        })
    return data


def generate_comparison_table(data):
    """Print comparison table."""
    print("=" * 85)
    print("RESISTANCE COEFFICIENT BENCHMARK: Computed vs Experimental")
    print("=" * 85)
    print(f"{'Case':<12} {'Ct_exp':>10} {'Ct_calc':>12} {'Error%':>8} {'Fn':>8} {'Status':>10}")
    print("-" * 85)
    for d in data:
        print(f"{d['label']:<12} {d['Ct_exp']:>10.6e} {d['Ct_calc']:>12.6e} {d['error_pct']:>+7.1f}% {d['Fn']:>8.4f} {d['status']:>10}")
    print("-" * 85)
    print()


def generate_figure(data, output_path):
    """Generate bar chart comparing Ct_exp vs Ct_calc."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("matplotlib not available, skipping figure generation")
        return None

    labels = [d["label"] for d in data]
    ct_exp = [d["Ct_exp"] for d in data]
    ct_calc = [d["Ct_calc"] for d in data]

    x = np.arange(len(labels))
    width = 0.35

    fig, ax = plt.subplots(figsize=(10, 5))
    bars1 = ax.bar(x - width / 2, ct_exp, width, label="Experimental", color="#2196F3", alpha=0.8)
    bars2 = ax.bar(x + width / 2, ct_calc, width, label="ITTC-78 Computed", color="#FF9800", alpha=0.8)

    ax.set_ylabel("Resistance Coefficient Ct", fontsize=12)
    ax.set_title("Ship Resistance Benchmark: Experimental vs ITTC-78 Computed", fontsize=14)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=11)
    ax.legend(fontsize=11)
    ax.set_yscale("log")

    # Add value labels
    for bar in bars1:
        height = bar.get_height()
        ax.annotate(f"{height:.4e}",
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3), textcoords="offset points",
                    ha="center", va="bottom", fontsize=9)
    for bar in bars2:
        height = bar.get_height()
        ax.annotate(f"{height:.4e}",
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3), textcoords="offset points",
                    ha="center", va="bottom", fontsize=9)

    # Add error percentages
    for i, d in enumerate(data):
        ax.text(i, max(ct_exp[i], ct_calc[i]) * 1.3,
                f"+{d['error_pct']:.1f}%",
                ha="center", fontsize=10, color="red", fontweight="bold")

    ax.grid(True, alpha=0.3, axis="y")
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Figure saved to {output_path}")
    return output_path


def main():
    results = load_results()
    if not results:
        print("No results found. Run the benchmarks first.")
        sys.exit(1)

    data = extract_metrics(results)
    generate_comparison_table(data)

    # Generate figure
    output_dir = os.path.join(os.path.dirname(__file__), "../../artifacts")
    os.makedirs(output_dir, exist_ok=True)
    fig_path = os.path.join(output_dir, "resistance_comparison.png")
    generate_figure(data, fig_path)

    # Save comparison data
    comp_path = os.path.join(output_dir, "comparison.json")
    with open(comp_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Comparison data saved to {comp_path}")


if __name__ == "__main__":
    main()
