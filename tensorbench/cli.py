"""Command-line interface for TensorBench."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .runner import run_benchmark


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tensorbench")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="run one local benchmark spec")
    run_parser.add_argument("--spec", required=True, help="Path to benchmark specification JSON")
    run_parser.add_argument("--output", default="tensorbench-runs", help="Evidence output directory")
    run_parser.add_argument("--project", help="Implementation project name override")
    run_parser.add_argument("--revision", help="Implementation revision override")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "run":
        spec_path = Path(args.spec).resolve()
        try:
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
            result = run_benchmark(
                spec,
                args.output,
                implementation_project=args.project,
                implementation_revision=args.revision,
            )
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            print(f"tensorbench: error: {exc}", file=sys.stderr)
            return 2

        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result["execution"]["status"] == "success" else 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
