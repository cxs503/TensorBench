"""Reference workload: 2-D five-point heat-diffusion stencil with an analytic solution.

Why this workload exists: TensorBench needs at least one benchmark whose
correctness verdict is derived from a closed-form reference instead of from a
solver's own self-report, so that "benchmark PASS as S-grade evidence" has a
concrete, re-derivable meaning.

Equation and reference
----------------------
    u_t = alpha * (u_xx + u_yy),  periodic [0, L]^2
    u(x, y, 0) = A * sin(k x) * sin(k y),  k = 2*pi/L
    u_exact(x, y, t) = A * exp(-2 * alpha * k^2 * t) * sin(k x) * sin(k y)

The discrete operator is the standard five-point FTCS scheme with the diffusion
number r = alpha*dt/h^2 held at 0.1 (well inside the 2-D stability limit 0.25).
Truncation error is O(dt) + O(h^2); with dt = 0.1*h^2/alpha the time term is
negligible and the expected relative error is ~1e-3 for n=96 (see the benchmark
specification for the predeclared tolerance and its derivation).

Implementations
---------------
``naive``      index arithmetic inside the loop over a padded (halo) grid.
``optimized``  row-slice buffers with ``zip`` over shifted rows; identical
               arithmetic and identical operand order, so the two
               implementations must agree to the last bit -- a real
               cross-implementation correctness check, not a style comparison.

Both write the same metric set; the metric definitions are declared in the
benchmark specification and are never adjusted after a run.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

IMPLS = ("naive", "optimized")


def _initial_field(n: int, length: float, amplitude: float) -> list[float]:
    """Padded flat field with periodic halos already filled."""
    ns = n + 2
    k = 2.0 * math.pi / length
    h = length / n
    grid = [0.0] * (ns * ns)
    for i in range(n):
        base = (i + 1) * ns
        for j in range(n):
            grid[base + j + 1] = amplitude * math.sin(k * i * h) * math.sin(k * j * h)
    return grid


def _fill_halos(grid: list[float], n: int) -> None:
    ns = n + 2
    for i in range(n):
        base = (i + 1) * ns
        grid[base] = grid[base + n]
        grid[base + ns - 1] = grid[base + 1]
    top = 1 * ns
    bottom = n * ns
    for j in range(ns):
        grid[j] = grid[bottom + j]
        grid[(ns - 1) * ns + j] = grid[top + j]


def _step_naive(grid: list[float], out: list[float], n: int, r: float) -> None:
    ns = n + 2
    four_r = 4.0 * r
    for i in range(1, n + 1):
        base = i * ns
        up = base - ns
        down = base + ns
        for j in range(1, n + 1):
            center = grid[base + j]
            out[base + j] = center + r * (
                grid[up + j] + grid[base + j - 1] + grid[down + j] + grid[base + j + 1]
            ) - four_r * center


def _step_optimized(grid: list[float], out: list[float], n: int, r: float) -> None:
    ns = n + 2
    four_r = 4.0 * r
    for i in range(1, n + 1):
        base = i * ns
        center_row = grid[base : base + ns]
        up_row = grid[base - ns : base]
        down_row = grid[base + ns : base + 2 * ns]
        out_row = out[base : base + ns]
        # Identical operand order to _step_naive so results are bit-comparable.
        out_row = [
            center + r * (up + left + down + right) - four_r * center
            for center, up, left, down, right in zip(
                center_row[1:-1], up_row[1:-1], center_row[0:-2], down_row[1:-1], center_row[2:]
            )
        ]
        out[base + 1 : base + ns - 1] = out_row


def _timed_sweeps(impl: str, n: int, steps: int, alpha: float, length: float,
                  amplitude: float, warmup_sweeps: int = 0) -> float:
    """Run ``steps`` sweeps and return the wall time of the measured sweeps.

    ``warmup_sweeps`` are executed but excluded from the measurement; the timer
    brackets the whole measured loop, so the reported throughput is
    ``n*n*steps_measured / seconds`` and not a single-sweep extrapolation.
    """
    h = length / n
    dt = 0.1 * h * h / alpha
    r = alpha * dt / (h * h)
    grid = _initial_field(n, length, amplitude)
    _fill_halos(grid, n)
    out = list(grid)
    step = _step_naive if impl == "naive" else _step_optimized
    for _ in range(warmup_sweeps):
        _fill_halos(grid, n)
        step(grid, out, n, r)
        grid, out = out, grid
    started = time.perf_counter()
    for _ in range(steps):
        _fill_halos(grid, n)
        step(grid, out, n, r)
        grid, out = out, grid
    return time.perf_counter() - started


def _field_after(impl: str, n: int, steps: int, alpha: float, length: float,
                 amplitude: float) -> list[float]:
    """Advance ``steps`` sweeps without timing and return the padded field."""
    h = length / n
    dt = 0.1 * h * h / alpha
    r = alpha * dt / (h * h)
    grid = _initial_field(n, length, amplitude)
    _fill_halos(grid, n)
    out = list(grid)
    step = _step_naive if impl == "naive" else _step_optimized
    for _ in range(steps):
        _fill_halos(grid, n)
        step(grid, out, n, r)
        grid, out = out, grid
    return grid


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--impl", choices=IMPLS, default="naive")
    parser.add_argument("--n", type=int, default=96, help="cells per direction")
    parser.add_argument("--steps", type=int, default=400)
    parser.add_argument("--alpha", type=float, default=1.0, help="diffusivity")
    parser.add_argument("--length", type=float, default=1.0, help="periodic domain length")
    parser.add_argument("--amplitude", type=float, default=1.0)
    parser.add_argument("--warmup-sweeps", type=int, default=5,
                        help="sweeps executed but excluded from the timed measurement")
    parser.add_argument("--out", required=True, help="metrics JSON path")
    args = parser.parse_args(argv)

    if args.n < 4 or args.steps < 1:
        parser.error("--n must be >= 4 and --steps >= 1")

    h = args.length / args.n
    dt = 0.1 * h * h / args.alpha
    total_time = dt * args.steps
    k = 2.0 * math.pi / args.length
    decay = math.exp(-2.0 * args.alpha * k * k * total_time)

    sweep_seconds = _timed_sweeps(args.impl, args.n, args.steps, args.alpha, args.length,
                                  args.amplitude, warmup_sweeps=args.warmup_sweeps)
    field = _field_after(args.impl, args.n, args.steps, args.alpha, args.length, args.amplitude)

    ns = args.n + 2
    max_err = 0.0
    sq_err = 0.0
    ref_sq = 0.0
    total = 0.0
    for i in range(args.n):
        for j in range(args.n):
            x = i * h
            y = j * h
            exact = args.amplitude * decay * math.sin(k * x) * math.sin(k * y)
            numeric = field[(i + 1) * ns + (j + 1)]
            err = abs(numeric - exact)
            max_err = max(max_err, err)
            sq_err += err * err
            ref_sq += exact * exact
            total += numeric

    mean_final = total / (args.n * args.n)
    initial = _initial_field(args.n, args.length, args.amplitude)
    mean_initial = sum(initial) / ((args.n + 2) ** 2)
    conservation_drift = abs(mean_final - mean_initial)

    updated_cells = float(args.n) * args.n * args.steps
    metrics = {
        "max_rel_error": max_err / args.amplitude,
        "l2_rel_error": math.sqrt(sq_err / ref_sq) if ref_sq else 0.0,
        "conservation_drift": conservation_drift,
        "throughput_mlups": updated_cells / sweep_seconds / 1e6 if sweep_seconds > 0 else 0.0,
        "step_seconds": sweep_seconds / args.steps,
        "field_sum": sum(field),
        "diffusion_number": args.alpha * dt / (h * h),
        "total_time": total_time,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"metrics": metrics}, indent=2) + "\n", encoding="utf-8")
    print(
        f"impl={args.impl} n={args.n} steps={args.steps} dt={dt:.6e} "
        f"max_rel_error={metrics['max_rel_error']:.6e} "
        f"throughput_mlups={metrics['throughput_mlups']:.2f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())