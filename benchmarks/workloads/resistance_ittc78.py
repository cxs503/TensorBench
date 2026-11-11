#!/usr/bin/env python3
"""Resistance coefficient calculator using ITTC-1978 method.

Computes total resistance coefficient Ct for a given ship geometry and speed
using the ITTC-1978 performance prediction method:

    Ct = (1+k)*Cf + Cw + Ca

Where:
    Cf = 0.075 / (log10(Re) - 2)^2   (ITTC-1957 friction line)
    Re = V * L / nu                   (Reynolds number)
    (1+k) = form factor (Holtrop or user-specified)
    Cw = wave-making resistance coefficient (residuary)
    Ca = correlation allowance (typically 0.0004 for model scale)

Usage:
    python resistance_ittc78.py \
        --L 5.720 --B 0.756 --T 0.244 --Cb 0.500 --S 4.920 \
        --V 2.196 --nu 1.139e-6 --form_factor 1.200 --Cw 0.00120 \
        --Ca 0.0004 --case_id dtmb5415 \
        --output metrics.json

All lengths in meters, speed in m/s, nu in m²/s.
"""
import argparse
import json
import math
import sys
from pathlib import Path


def ittc1957_cf(reynolds: float) -> float:
    """ITTC-1957 friction line: Cf = 0.075 / (log10(Re) - 2)^2."""
    if reynolds <= 0:
        raise ValueError(f"Reynolds number must be positive, got {reynolds}")
    log_re = math.log10(reynolds)
    return 0.075 / (log_re - 2.0) ** 2


def compute_resistance(
    L: float, B: float, T: float, Cb: float, S: float,
    V: float, nu: float, form_factor: float, Cw: float,
    Ca: float, rho: float = 998.2
) -> dict:
    """Compute resistance coefficients using ITTC-1978 method.

    Returns dict with all intermediate and final values.
    """
    # Reynolds number
    Re = V * L / nu

    # Friction coefficient (ITTC-1957)
    Cf = ittc1957_cf(Re)

    # Froude number
    g = 9.80665
    Fn = V / math.sqrt(g * L)

    # Total resistance coefficient (model scale)
    # Ct = (1+k)*Cf + Cw + Ca
    Ct = form_factor * Cf + Cw + Ca

    # Frictional resistance coefficient component
    Cfv = form_factor * Cf

    # Total resistance in Newtons
    q = 0.5 * rho * V ** 2  # dynamic pressure
    Rt = Ct * q * S

    return {
        "Re": Re,
        "Fn": Fn,
        "Cf": Cf,
        "Cw": Cw,
        "Ca": Ca,
        "form_factor": form_factor,
        "Ct": Ct,
        "Cfv": Cfv,
        "Rt_N": Rt,
        "q_Pa": q,
        "L_m": L,
        "B_m": B,
        "T_m": T,
        "Cb": Cb,
        "S_m2": S,
        "V_ms": V,
        "nu_m2s": nu,
        "rho_kgm3": rho,
    }


def main():
    parser = argparse.ArgumentParser(description="ITTC-1978 resistance coefficient calculator")
    parser.add_argument("--L", type=float, required=True, help="Length (m)")
    parser.add_argument("--B", type=float, required=True, help="Beam (m)")
    parser.add_argument("--T", type=float, required=True, help="Draft (m)")
    parser.add_argument("--Cb", type=float, required=True, help="Block coefficient")
    parser.add_argument("--S", type=float, required=True, help="Wetted surface area (m²)")
    parser.add_argument("--V", type=float, required=True, help="Speed (m/s)")
    parser.add_argument("--nu", type=float, default=1.139e-6, help="Kinematic viscosity (m²/s), default fresh water 15°C")
    parser.add_argument("--form_factor", type=float, required=True, help="Form factor (1+k)")
    parser.add_argument("--Cw", type=float, required=True, help="Wave resistance coefficient")
    parser.add_argument("--Ca", type=float, default=0.0004, help="Correlation allowance")
    parser.add_argument("--rho", type=float, default=998.2, help="Water density (kg/m³)")
    parser.add_argument("--case_id", type=str, required=True, help="Case identifier")
    parser.add_argument("--output", type=str, default="metrics.json", help="Output metrics file")
    args = parser.parse_args()

    try:
        result = compute_resistance(
            L=args.L, B=args.B, T=args.T, Cb=args.Cb, S=args.S,
            V=args.V, nu=args.nu, form_factor=args.form_factor,
            Cw=args.Cw, Ca=args.Ca, rho=args.rho
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Write metrics file - ONLY numeric values (TensorBench requirement)
    metrics = {
        "Ct": result["Ct"],
        "Cf": result["Cf"],
        "Cw": result["Cw"],
        "Ca": result["Ca"],
        "Cfv": result["Cfv"],
        "Re": result["Re"],
        "Fn": result["Fn"],
        "Rt_N": result["Rt_N"],
    }

    output_path = Path(args.output)
    output_path.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    print(f"Metrics written to {output_path}")
    print(f"Case: {args.case_id}")
    print(f"  Ct = {result['Ct']:.6e}")
    print(f"  Cf = {result['Cf']:.6e}")
    print(f"  Cw = {result['Cw']:.6e}")
    print(f"  Re = {result['Re']:.2e}")
    print(f"  Fn = {result['Fn']:.4f}")


if __name__ == "__main__":
    main()
