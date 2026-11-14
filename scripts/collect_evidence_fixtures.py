"""Record real AE-01 evidence fixtures from the live TensorPlatform + GitHub.

This is the only script allowed to write ``tests/fixtures/real_missions``. It
performs read-only collection, then stores two artifacts per mission:

* ``tests/fixtures/recorded/m<id>.json`` -- the raw upstream payloads, used by
  the offline interface-contract test (replayed through ``collect._request_json``);
* ``tests/fixtures/real_missions/<id>.json`` -- the sealed evidence bundle that
  ``tensorbench collect`` produced, with the recording's SHA-256 embedded under
  ``fixture`` so a reader can tell a mutated fixture from a live one.

Nothing is fabricated: if the platform or GitHub cannot answer, the run fails
loudly instead of writing a partial "fixture".
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tensorbench import evidence_bundle as bundle_model  # noqa: E402
from tensorbench.collect import CollectorError, collect_mission_evidence  # noqa: E402

DEFAULT_MISSIONS = [19812, 19694, 18757, 18685, 18524, 20111]
ROOT = Path(__file__).resolve().parents[1]
RECORDED_DIR = ROOT / "tests" / "fixtures" / "recorded"
BUNDLE_DIR = ROOT / "tests" / "fixtures" / "real_missions"


def record(mission_id: int, *, max_deliverables: int) -> dict:
    raw: dict = {}
    bundle = collect_mission_evidence(
        mission_id, max_deliverables=max_deliverables, raw_sink=raw
    )
    RECORDED_DIR.mkdir(parents=True, exist_ok=True)
    BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
    recorded_path = RECORDED_DIR / f"m{mission_id}.json"
    recorded_path.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    bundle["fixture"] = {
        "recorded_raw_path": f"tests/fixtures/recorded/m{mission_id}.json",
        "recorded_raw_sha256": bundle_model.sha256_payload(raw),
    }
    bundle_model.seal(bundle)
    bundle_path = BUNDLE_DIR / f"{mission_id}.json"
    bundle_path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    pr = bundle["pull_request"]
    return {
        "mission_id": mission_id,
        "repo": bundle["mission"]["repo"],
        "collected_at": bundle["collected_at"],
        "pull_request": None if pr == bundle_model.MISSING else pr["number"],
        "commit": None if bundle["commit"] == bundle_model.MISSING else bundle["commit"]["sha"],
        "ci": None if bundle["ci"] == bundle_model.MISSING else bundle["ci"]["conclusion"],
        "deliverables": len(bundle["deliverables"]),
        "missing": bundle["missing"],
        "bundle_sha256": bundle["integrity"]["bundle_sha256"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--missions", default=",".join(str(m) for m in DEFAULT_MISSIONS))
    parser.add_argument("--max-deliverables", type=int, default=10)
    parser.add_argument(
        "--allow-failure", action="store_true",
        help="Keep going when one mission cannot be collected (default: fail the recording)",
    )
    args = parser.parse_args(argv)

    entries: list[dict] = []
    errors: list[str] = []
    for token in args.missions.split(","):
        token = token.strip()
        if not token:
            continue
        mission_id = int(token.lstrip("mM"))
        try:
            entry = record(mission_id, max_deliverables=args.max_deliverables)
        except CollectorError as exc:
            errors.append(f"m{mission_id}: {exc}")
            if not args.allow_failure:
                print(f"tensorbench: fixture recording failed: m{mission_id}: {exc}", file=sys.stderr)
                return 2
            continue
        entries.append(entry)
        print(json.dumps(entry, ensure_ascii=False))

    manifest = {
        "description": "Real AE-01 evidence bundles collected read-only from TensorPlatform and GitHub.",
        "schema": "schemas/evidence_bundle.json",
        "generator": "scripts/collect_evidence_fixtures.py",
        "missions": entries,
        "errors": errors,
    }
    (BUNDLE_DIR / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"recorded {len(entries)} bundles -> {BUNDLE_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())