"""Command-line interface for TensorBench."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .compare import compare_results, load_result
from .contracts import ContractValidationError, validate_file
from .business_evidence import BusinessEvidenceError, reconcile_file
from .achievement import AchievementInputError, evaluate_file
from .publish import (
    PlatformClient,
    build_capability_delta,
    build_evaluation_payload,
    default_artifact_refs,
)
from .runner import run_benchmark


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tensorbench")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser(
        "validate", help="validate an evidence, report or asset contract JSON file"
    )
    validate_parser.add_argument("--kind", choices=("evidence", "report", "asset"), required=True)
    validate_parser.add_argument("--input", required=True, help="Contract JSON file")
    validate_parser.add_argument("--output", help="Optional validation-result JSON path")

    achievement_parser = subparsers.add_parser(
        "evaluate-work-package", help="evaluate revision-pinned agent work-package evidence"
    )
    achievement_parser.add_argument("--input", required=True, help="Work-package evidence JSON")
    achievement_parser.add_argument("--output", help="Optional evaluation-report JSON path")

    business_parser = subparsers.add_parser(
        "reconcile-business", help="reconcile normalized contract/PO/delivery/invoice records"
    )
    business_parser.add_argument("--input", required=True, help="Normalized document bundle JSON")
    business_parser.add_argument("--output", help="Optional validation-report JSON path")
    business_parser.add_argument("--tolerance", default="0.01", help="Decimal currency tolerance")

    run_parser = subparsers.add_parser("run", help="run one local benchmark spec")
    run_parser.add_argument("--spec", required=True, help="Path to benchmark specification JSON")
    run_parser.add_argument("--output", default="tensorbench-runs", help="Evidence output directory")
    run_parser.add_argument("--project", help="Implementation project name override")
    run_parser.add_argument("--revision", help="Implementation revision override")
    run_parser.add_argument(
        "--repetitions", type=int, help="Override spec.protocol.repetitions"
    )

    compare_parser = subparsers.add_parser(
        "compare", help="compare a candidate result against a baseline result"
    )
    compare_parser.add_argument("--baseline", required=True, help="Baseline *.result.json")
    compare_parser.add_argument("--candidate", required=True, help="Candidate *.result.json")
    compare_parser.add_argument(
        "--min-improvement",
        type=float,
        default=None,
        help="Relative improvement required for verdict=improved (default 0.10)",
    )
    compare_parser.add_argument("--hypothesis", help="Optional hypothesis under test")
    compare_parser.add_argument("--output", help="Write the comparison JSON here")

    publish_parser = subparsers.add_parser(
        "publish", help="turn run results into platform evaluation + capability delta records"
    )
    publish_parser.add_argument("--result", required=True, help="Candidate *.result.json")
    publish_parser.add_argument("--baseline", help="Baseline *.result.json for the comparison")
    publish_parser.add_argument("--mission-id", type=int, required=True)
    publish_parser.add_argument("--contributor", required=True)
    publish_parser.add_argument("--reviewer", required=True)
    publish_parser.add_argument("--repo", default="TensorBench")
    publish_parser.add_argument("--grade", help="Override the derived S grade")
    publish_parser.add_argument("--e-level", help="Override the derived evidence level")
    publish_parser.add_argument("--category", help="Override the derived capability delta category")
    publish_parser.add_argument("--min-improvement", type=float, default=None)
    publish_parser.add_argument("--hypothesis", help="Optional hypothesis under test")
    publish_parser.add_argument("--output", default=None, help="Bundle output directory")
    publish_parser.add_argument(
        "--post", action="store_true", help="POST the evaluation to the platform (default: dry run)"
    )
    publish_parser.add_argument("--api-base", default=None)
    return parser


def _cmd_compare(args: argparse.Namespace) -> int:
    baseline = load_result(args.baseline)
    candidate = load_result(args.candidate)
    comparison = compare_results(
        baseline,
        candidate,
        min_relative_improvement=args.min_improvement,
        hypothesis=args.hypothesis,
    )
    text = json.dumps(comparison, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


def _cmd_publish(args: argparse.Namespace) -> int:
    result = load_result(args.result)
    result_path = Path(args.result).resolve()
    baseline = load_result(args.baseline) if args.baseline else None
    comparison = None
    if baseline is not None:
        comparison = compare_results(
            baseline,
            result,
            min_relative_improvement=args.min_improvement,
            hypothesis=args.hypothesis,
        )

    output = Path(args.output).resolve() if args.output else result_path.parent
    output.mkdir(parents=True, exist_ok=True)

    comparison_path = None
    if comparison is not None:
        comparison_path = output / f"{result['run_id']}.comparison.json"
        comparison_path.write_text(
            json.dumps(comparison, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    refs = default_artifact_refs(result_path, comparison_path)
    evaluation = build_evaluation_payload(
        result,
        comparison,
        mission_id=args.mission_id,
        contributor=args.contributor,
        reviewer=args.reviewer,
        repo=args.repo,
        grade=args.grade,
        e_level=args.e_level,
        artifact_refs=refs,
    )
    bundle: dict[str, object] = {
        "evaluation": evaluation,
        "comparison": comparison,
        "artifact_refs": refs,
    }
    if comparison is not None:
        bundle["capability_delta"] = build_capability_delta(
            comparison,
            category=args.category,
            artifacts=[f"{r['path']}#sha256={r['sha256']}" for r in refs],
            result=result,
        )

    bundle_path = output / f"{result['run_id']}.publish.json"
    bundle_path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"tensorbench: wrote {bundle_path}", file=sys.stderr)

    if not args.post:
        print(json.dumps(bundle["evaluation"], indent=2, ensure_ascii=False))
        return 0

    client = PlatformClient(args.api_base)
    client.login()
    posted = client.post_evaluation(bundle["evaluation"])
    print(json.dumps({"post": posted}, indent=2, ensure_ascii=False))
    if posted["status"] != 200:
        return 1
    evaluation_id = (posted.get("data") or {}).get("evaluation_id")
    if evaluation_id:
        fetched = client.get_evaluation(str(evaluation_id))
        print(json.dumps({"verified": fetched}, indent=2, ensure_ascii=False))
    return 0


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "evaluate-work-package":
        try:
            result = evaluate_file(args.input)
            rendered = json.dumps(result, indent=2, ensure_ascii=False)
            if args.output:
                Path(args.output).write_text(rendered + "\n", encoding="utf-8")
            print(rendered)
            return 0 if result["overall_status"] == "passed" else 1
        except (OSError, json.JSONDecodeError, AchievementInputError) as exc:
            print(f"tensorbench: error: {exc}", file=sys.stderr)
            return 2

    if args.command == "reconcile-business":
        try:
            result = reconcile_file(args.input, tolerance=args.tolerance)
            rendered = json.dumps(result, indent=2, ensure_ascii=False)
            if args.output:
                Path(args.output).write_text(rendered + "\n", encoding="utf-8")
            print(rendered)
            return 0 if result["overall_status"] == "passed" else 1
        except (OSError, json.JSONDecodeError, BusinessEvidenceError) as exc:
            print(f"tensorbench: error: {exc}", file=sys.stderr)
            return 2

    if args.command == "validate":
        try:
            result = validate_file(args.kind, args.input)
            rendered = json.dumps(result, indent=2, ensure_ascii=False)
            if args.output:
                Path(args.output).write_text(rendered + "\n", encoding="utf-8")
            print(rendered)
            return 0 if result["status"] == "valid" else 1
        except (OSError, json.JSONDecodeError, ContractValidationError) as exc:
            print(f"tensorbench: error: {exc}", file=sys.stderr)
            return 2

    if args.command == "run":
        spec_path = Path(args.spec).resolve()
        try:
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
            result = run_benchmark(
                spec,
                args.output,
                implementation_project=args.project,
                implementation_revision=args.revision,
                repetitions=args.repetitions,
            )
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            print(f"tensorbench: error: {exc}", file=sys.stderr)
            return 2

        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result["execution"]["status"] == "success" else 1

    if args.command == "compare":
        try:
            return _cmd_compare(args)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            print(f"tensorbench: error: {exc}", file=sys.stderr)
            return 2

    if args.command == "publish":
        try:
            return _cmd_publish(args)
        except (OSError, json.JSONDecodeError, ValueError, RuntimeError) as exc:
            print(f"tensorbench: error: {exc}", file=sys.stderr)
            return 2

    return 2


if __name__ == "__main__":
    raise SystemExit(main())