"""The reference stencil workload must reproduce its analytic solution.

This is the TensorBench self-check: if the reference workload is wrong, every
downstream "benchmark PASS" statement is worthless.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
WORKLOAD = ROOT / "benchmarks" / "reference" / "stencil2d5pt" / "stencil2d5pt.py"


def _run(impl: str, tmp_path: Path, n: int = 32, steps: int = 60) -> dict:
    out = tmp_path / f"metrics-{impl}.json"
    subprocess.run(
        [sys.executable, str(WORKLOAD), "--impl", impl, "--n", str(n), "--steps", str(steps),
         "--warmup-sweeps", "1", "--out", str(out)],
        check=True, capture_output=True, text=True, timeout=300,
    )
    return json.loads(out.read_text())["metrics"]


def test_reference_matches_analytic_solution(tmp_path):
    for impl in ("naive", "optimized"):
        metrics = _run(impl, tmp_path)
        # truncation error for this coarse grid is ~1e-3; the run must stay close
        assert metrics["max_rel_error"] < 5e-3, impl
        assert metrics["l2_rel_error"] < 5e-3, impl
        assert metrics["conservation_drift"] < 1e-9, impl
        assert metrics["diffusion_number"] == 0.1
        assert metrics["throughput_mlups"] > 0


def test_implementations_agree_bitwise(tmp_path):
    naive = _run("naive", tmp_path)
    optimized = _run("optimized", tmp_path)
    assert naive["field_sum"] == optimized["field_sum"]
    assert naive["max_rel_error"] == optimized["max_rel_error"]
