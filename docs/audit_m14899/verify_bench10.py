#!/usr/bin/env python3
"""Independent replication of mission m14899 (KPI-BENCH-10) resistance benchmark cases.

Scope: this script does NOT import the audited implementation
(`benchmarks/workloads/resistance_ittc78.py` from m14899's worktree).  It
re-implements ITTC-1957 friction and ITTC-1978 total resistance from scratch and
then re-runs every acceptance claim of the three audited benchmark specs.

Case parameters are transcribed verbatim from the audited spec files
(`workload.command` of `<m14899>/benchmarks/cases/<case>/spec.json`), which are
*untracked* in that worktree (see audit report finding F1).  Because they are
not reachable from any git ref, they are duplicated here so that this check is
durable and runnable without that worktree; `--tree` additionally re-reads the
specs and result JSONs from the original worktree when it is available.

Usage:
    python3 docs/audit_m14899/verify_bench10.py                 # standalone
    python3 docs/audit_m14899/verify_bench10.py --tree <path>   # cross-check vs m14899 tree
    python3 docs/audit_m14899/verify_bench10.py --json out.json
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys

G = 9.80665
RHO = 998.2
NU = 1.139e-6

# ---------------------------------------------------------------------------
# Case parameters (verbatim from m14899 benchmarks/cases/*/spec.json commands)
# ---------------------------------------------------------------------------
CASES = {
    "suboff": {
        "L": 4.356, "B": 0.508, "T": 0.254, "Cb": 0.556, "S": 4.576,
        "V": 1.314, "form_factor": 1.050, "Cw": 0.00000, "Ca": 0.0004,
        "Ct_exp": 0.00315, "Fr_anchor": 0.20,
        "spec_tolerance_pct": 27.0, "spec_Ct_threshold": 0.004,
        "reported_Ct": 0.003963203186026273,
        "reported_Fn": 0.20104398862975406,
        "reported_run_id": "tb-ab3005bd5068491eaf47688c70d0cafb",
        "anchor": "Huang et al., DTRC-92/001, 1992",
    },
    "dtmb5415": {
        "L": 5.720, "B": 0.756, "T": 0.244, "Cb": 0.500, "S": 4.920,
        "V": 2.196, "form_factor": 1.200, "Cw": 0.00080, "Ca": 0.0004,
        "Ct_exp": 0.00380, "Fr_anchor": 0.28,
        "spec_tolerance_pct": 32.0, "spec_Ct_threshold": 0.005,
        "reported_Ct": 0.004739565034855285,
        "reported_Fn": 0.29320676315564886,
        "reported_run_id": "tb-a95adde3f7a34a02a8c34e33f33b3619",
        "anchor": "Olivieri et al., INSEAN 2001",
    },
    "kvlcc2": {
        "L": 7.2786, "B": 1.2131, "T": 0.3206, "Cb": 0.8098, "S": 9.438,
        "V": 1.179, "form_factor": 1.250, "Cw": 0.00020, "Ca": 0.0004,
        "Ct_exp": 0.00410, "Fr_anchor": 0.142,
        "spec_tolerance_pct": 15.0, "spec_Ct_threshold": 0.00472,
        "reported_Ct": 0.004541477114142221,
        "reported_Fn": 0.13954990357849692,
        "reported_run_id": "tb-7823fedb31a54e4cad2af9d54b010966",
        "anchor": "SIMMAN 2008, MOERI",
    },
}

PLATFORM_ERROR_LIMIT_PCT = 15.0  # platform precision standard: >15% unacceptable
KPI_CASE_TARGET = 10             # KPI-BENCH-10: >= 10 reference cases


def ittc1957_cf(re: float) -> float:
    if re <= 0:
        raise ValueError("Re must be positive")
    return 0.075 / (math.log10(re) - 2.0) ** 2


def replicate(case: dict) -> dict:
    """Full independent recomputation for one case."""
    re = case["V"] * case["L"] / NU
    cf = ittc1957_cf(re)
    fn = case["V"] / math.sqrt(G * case["L"])
    ct = case["form_factor"] * cf + case["Cw"] + case["Ca"]
    rt = ct * 0.5 * RHO * case["V"] ** 2 * case["S"]

    err_pct = (ct - case["Ct_exp"]) / case["Ct_exp"] * 100.0

    # Smallest Ct this method can produce with a physically admissible form
    # factor ((1+k) >= 1.0) and zero wave resistance.
    ct_floor = 1.0 * cf + case["Ca"]
    err_floor_pct = (ct_floor - case["Ct_exp"]) / case["Ct_exp"] * 100.0

    # Form factor that would match the anchor exactly, given the case Cw/Ca.
    k_exact = (case["Ct_exp"] - case["Cw"] - case["Ca"]) / cf

    return {
        "case": case,
        "Re": re,
        "Cf": cf,
        "Fn": fn,
        "Ct": ct,
        "Rt_N": rt,
        "err_vs_anchor_pct": err_pct,
        "abs_err_pct": abs(err_pct),
        "passes_platform_15pct": abs(err_pct) <= PLATFORM_ERROR_LIMIT_PCT,
        "passes_spec_tolerance": abs(err_pct) <= case["spec_tolerance_pct"],
        "passes_spec_threshold_rule": ct <= case["spec_Ct_threshold"],
        "ct_floor_at_form_factor_1": ct_floor,
        "err_floor_pct": err_floor_pct,
        "anchor_reachable_with_physical_form_factor": err_floor_pct <= PLATFORM_ERROR_LIMIT_PCT,
        "form_factor_needed_for_exact_match": k_exact,
        "form_factor_physical": k_exact >= 1.0,
        "Fn_vs_anchor_delta_pct": (fn - case["Fr_anchor"]) / case["Fr_anchor"] * 100.0,
        "reported_Ct": case["reported_Ct"],
        "reported_Fn": case["reported_Fn"],
        "replication_delta_Ct": ct - case["reported_Ct"],
        "replication_delta_Fn": fn - case["reported_Fn"],
    }


def load_tree(tree: str) -> dict:
    """Cross-check the transcribed parameters against the audited worktree."""
    out = {"specs_found": [], "results": {}, "problems": []}
    for name in CASES:
        spec_path = os.path.join(tree, "benchmarks", "cases", name, "spec.json")
        if not os.path.exists(spec_path):
            out["problems"].append(f"missing spec {spec_path}")
            continue
        spec = json.load(open(spec_path, encoding="utf-8"))
        out["specs_found"].append(name)
        argv = spec["workload"]["command"]
        parsed = {}
        for i, tok in enumerate(argv):
            if tok.startswith("--"):
                parsed[tok[2:]] = argv[i + 1]
        ref = spec["acceptance"]["reference"]
        mine = CASES[name]
        checks = {
            "L": (float(parsed["L"]), mine["L"]),
            "B": (float(parsed["B"]), mine["B"]),
            "T": (float(parsed["T"]), mine["T"]),
            "Cb": (float(parsed["Cb"]), mine["Cb"]),
            "S": (float(parsed["S"]), mine["S"]),
            "V": (float(parsed["V"]), mine["V"]),
            "form_factor": (float(parsed["form_factor"]), mine["form_factor"]),
            "Cw": (float(parsed["Cw"]), mine["Cw"]),
            "Ca": (float(parsed["Ca"]), mine["Ca"]),
            "Ct_exp": (float(ref["Ct_exp"]), mine["Ct_exp"]),
            "Fr_anchor": (float(ref["Fr"]), mine["Fr_anchor"]),
            "spec_tolerance_pct": (float(ref["tolerance_pct"]), mine["spec_tolerance_pct"]),
        }
        for key, (got, want) in checks.items():
            if abs(got - want) > 1e-12:
                out["problems"].append(f"{name}: transcribed {key}={want} but spec says {got}")

        run_dir = os.path.join(tree, "tensorbench-runs", name)
        if os.path.isdir(run_dir):
            for fn in sorted(os.listdir(run_dir)):
                if not fn.endswith(".result.json"):
                    continue
                res = json.load(open(os.path.join(run_dir, fn), encoding="utf-8"))
                metrics = {m["name"]: m["value"] for m in res.get("metrics", [])}
                out["results"].setdefault(name, []).append({
                    "file": f"tensorbench-runs/{name}/{fn}",
                    "run_id": res.get("run_id"),
                    "acceptance_status": res.get("acceptance", {}).get("status"),
                    "Ct": metrics.get("Ct"),
                    "Fn": metrics.get("Fn"),
                })
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", default=None, help="path to m14899 worktree (optional)")
    ap.add_argument("--json", default=None, help="write machine-readable result here")
    args = ap.parse_args()

    rows = [replicate(c) for c in CASES.values()]

    tree_info = load_tree(args.tree) if args.tree else None

    payload = {
        "audited_mission": 14899,
        "kpi": "KPI-BENCH-10",
        "kpi_case_target": KPI_CASE_TARGET,
        "cases_found": len(CASES),
        "kpi_coverage_fraction": len(CASES) / KPI_CASE_TARGET,
        "platform_error_limit_pct": PLATFORM_ERROR_LIMIT_PCT,
        "cases_passing_platform_15pct": sum(r["passes_platform_15pct"] for r in rows),
        "cases_marked_passed_by_own_specs": sum(r["passes_spec_threshold_rule"] for r in rows),
        "rows": [
            {k: v for k, v in r.items() if k != "case"}
            | {
                "Ct_exp": r["case"]["Ct_exp"],
                "Fr_anchor": r["case"]["Fr_anchor"],
                "spec_tolerance_pct": r["case"]["spec_tolerance_pct"],
                "spec_Ct_threshold": r["case"]["spec_Ct_threshold"],
                "anchor": r["case"]["anchor"],
                "reported_run_id": r["case"]["reported_run_id"],
            }
            for r in rows
        ],
        "tree_cross_check": tree_info,
    }

    print("=" * 100)
    print("INDEPENDENT REPLICATION OF m14899 / KPI-BENCH-10")
    print("=" * 100)
    hdr = (f"{'case':<10}{'Fn':>9}{'Fr_anc':>8}{'dFn%':>8}{'Cf':>11}{'Ct_calc':>11}"
           f"{'Ct_exp':>10}{'err%':>8}{'15%?':>6}{'spec_tol':>9}{'status':>8}")
    print(hdr)
    for r in rows:
        c = r["case"]
        print(f"{[k for k, v in CASES.items() if v is c][0]:<10}{r['Fn']:>9.5f}{c['Fr_anchor']:>8.3f}"
              f"{r['Fn_vs_anchor_delta_pct']:>8.2f}{r['Cf']:>11.6e}{r['Ct']:>11.6e}"
              f"{c['Ct_exp']:>10.5f}{r['err_vs_anchor_pct']:>8.2f}"
              f"{('PASS' if r['passes_platform_15pct'] else 'FAIL'):>6}"
              f"{c['spec_tolerance_pct']:>8.0f}%"
              f"{('passed' if r['passes_spec_threshold_rule'] else 'failed'):>8}")

    print("\nAnchor reachability under ITTC-78 with a physical form factor ((1+k) >= 1, Cw = 0):")
    for name, r in zip(CASES, rows):
        print(f"  {name:<10} min Ct = {r['ct_floor_at_form_factor_1']:.6e} "
              f"({r['err_floor_pct']:+.1f}% vs anchor); "
              f"form factor for exact match = {r['form_factor_needed_for_exact_match']:.3f} "
              f"({'physical' if r['form_factor_physical'] else 'UNPHYSICAL (<1.0)'})")

    print(f"\nCoverage: {len(CASES)}/{KPI_CASE_TARGET} cases = {100*len(CASES)/KPI_CASE_TARGET:.0f}% of KPI-BENCH-10")
    print(f"Pass rate at platform 15% standard: {payload['cases_passing_platform_15pct']}/{len(rows)}")
    print(f"Pass rate at the specs' own (widened) tolerances: "
          f"{payload['cases_marked_passed_by_own_specs']}/{len(rows)}")

    if tree_info is not None:
        print("\nCross-check against audited worktree:")
        print(f"  specs read: {tree_info['specs_found']}")
        print(f"  parameter transcription problems: {tree_info['problems'] or 'none'}")
        for name, runs in tree_info["results"].items():
            for run in runs:
                print(f"  {run['file']}: status={run['acceptance_status']} "
                      f"Ct={run['Ct']:.6e} Fn={run['Fn']:.6f}")
        if tree_info["problems"]:
            payload["transcription_ok"] = False
        else:
            payload["transcription_ok"] = True

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())