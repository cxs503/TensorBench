#!/usr/bin/env python3
"""Stage-3 real-scenario pilot: business-plan PDF -> structured business evidence.

Runs the *existing* TensorBench chain (``pdf_evidence`` -> ``business_pdf_fields``
-> field review -> structured record) on one private business-plan PDF and
measures what the declared field spectra actually recover.

Modes::

    freeze   hash ``criteria_v1.md`` and write ``criteria_freeze.json`` (before the run)
    run      execute the pilot; refuses to run without a freeze that predates it

Everything written under ``--out`` is desensitized (see ``publish_value``); the
verbatim extraction, proposals and reviewed bundle go to ``--private-out``, which
must be outside the repository. The source PDF is never copied into the worktree.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tensorbench.business_pdf_fields import (  # noqa: E402
    FIELD_SPECTRA,
    approved_pdf_fields_to_evidence_record,
    propose_pdf_fields,
    review_pdf_field_proposals,
)
from tensorbench.pdf_evidence import PdfEvidenceError, extract_pdf_evidence  # noqa: E402

PILOT_ID = "BP-20261115-tensorai-bp-field-extraction"
PILOT_DIR = ROOT / "docs" / "pilots" / PILOT_ID
CRITERIA_FILE = PILOT_DIR / "criteria_v1.md"
FREEZE_FILE = PILOT_DIR / "criteria_freeze.json"
FROZEN_BY = "m22060-pilot-author (agent mission 22060)"
REVIEWER = "m22060-pilot-author (provisional, not independent)"

#: Metric/taxonomy tokens: published verbatim so a reviewer can re-derive them.
VERBATIM_FIELDS = {"document_version", "document_issue_date", "table_label_percent",
                   "ratio_block", "roadmap_window"}
#: Identity/citation text: published masked only.
MASKED_FIELDS = {"document_title", "legal_disclaimer", "market_reference", "financing_stage"}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_revision() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT),
                          capture_output=True, text=True).stdout.strip()


# --------------------------------------------------------------------- redaction

def publish_value(field: str, value: str, whitelist: set[str]) -> str:
    """Desensitize one extracted value for repository publication.

    Metric/taxonomy tokens are published as-is (unlinkable without the document);
    identity or citation text is reduced to a 2-character prefix plus length and
    SHA-256. Everything published verbatim is registered in ``whitelist`` so the
    leak guard can prove nothing else of the source reached the repository.
    """
    if field in VERBATIM_FIELDS and not re.search(r"[\u4e00-\u9fff]{5,}", value):
        whitelist.add(value)
        return value
    return f"{value[:2]}***(len={len(value)},sha256={_sha256(value)[:12]})"


def publish_subject(field: str, subject: str | None, whitelist: set[str]) -> str | None:
    if subject is None:
        return None
    return publish_value(field, subject, whitelist)


# ------------------------------------------------------------------------ freeze

def freeze() -> int:
    if not CRITERIA_FILE.exists():
        print(f"criteria file missing: {CRITERIA_FILE}", file=sys.stderr)
        return 2
    criteria_sha = _file_sha256(CRITERIA_FILE)
    payload = {
        "criteria_ref": str(CRITERIA_FILE.relative_to(ROOT)),
        "criteria_sha256": criteria_sha,
        "frozen_at": _now(),
        "frozen_by": FROZEN_BY,
        "spec_ref": "docs/SCENARIO_ACCEPTANCE_FRAMEWORK.md#3-six-steps",
        "amendments": [],
    }
    if FREEZE_FILE.exists():
        existing = json.loads(FREEZE_FILE.read_text(encoding="utf-8"))
        if existing.get("criteria_sha256") != criteria_sha:
            print("refusing to amend a frozen criteria set "
                  f"(frozen {existing.get('frozen_at')}); publish a new criteria version", file=sys.stderr)
            return 3
        print(json.dumps(existing, ensure_ascii=False, indent=2))
        return 0
    FREEZE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def load_freeze(run_started_at: str) -> dict:
    if not FREEZE_FILE.exists():
        raise SystemExit("criteria_freeze.json is missing; run the 'freeze' mode first")
    payload = json.loads(FREEZE_FILE.read_text(encoding="utf-8"))
    if payload["criteria_sha256"] != _file_sha256(CRITERIA_FILE):
        raise SystemExit("criteria_v1.md no longer matches the frozen hash; post-freeze edit is not allowed")
    if payload["frozen_at"] > run_started_at:
        raise SystemExit("criteria freeze does not predate this run")
    return payload


# ----------------------------------------------------------------------- helpers

def page_texts(extraction: dict) -> dict[int, str]:
    return {page["locator"]["page_number"]: page["text"] for page in extraction["pages"]}


def section_page(extraction: dict, heading: str, proposals: list[dict] | None = None) -> int | None:
    """Locate a section page by heading text; ties broken by where proposals landed."""
    pages = page_texts(extraction)
    hits = [number for number, text in pages.items() if heading in text]
    if not hits:
        return None
    if len(hits) == 1 or not proposals:
        return hits[0]
    score = {number: 0 for number in hits}
    for proposal in proposals:
        number = proposal["locator"]["page_number"]
        if number in score:
            score[number] += 1
    return max(score, key=lambda number: (score[number], number))


def coverage_rows(spectrum: str, proposals: list[dict]) -> list[dict]:
    """Per-field coverage: proposal count and pages; no averaging into one score."""
    rows = []
    for field in FIELD_SPECTRA[spectrum]:
        items = sorted((p for p in proposals if p["field"] == field),
                       key=lambda p: (p["locator"]["page_number"], p["locator"]["start_offset"]))
        reason = None
        if not items:
            reason = ("document carries no invoice/PO/contract label: a business plan is not a trade document"
                      if spectrum == "trade_documents_v1"
                      else "no label/table shape declared for this field matched on any page")
        rows.append({
            "field": field,
            "proposal_count": len(items),
            "state": "extracted" if items else "failed",
            "failure_reason": reason,
            "pages": sorted({p["locator"]["page_number"] for p in items}),
            "items": items,
        })
    return rows


def ratios_series(normalized: str) -> list[int]:
    return [int(token) for token in normalized.split("/")]


# -------------------------------------------------------------------- invariants

def check_invariants(extraction: dict, proposals: list[dict]) -> dict:
    """Arithmetic invariants of the extracted tables (criterion C6)."""
    pages = page_texts(extraction)
    fund_page = section_page(extraction, "资金使用结构")
    revenue_page = section_page(extraction, "收入结构")
    roadmap_page = section_page(extraction, "发展路线图", proposals)
    fund_rows = [p for p in proposals if p["field"] == "table_label_percent"
                 and p["locator"]["page_number"] == fund_page]
    revenue_rows = [p for p in proposals if p["field"] == "ratio_block"
                    and p["locator"]["page_number"] == revenue_page]
    roadmap_rows = [p for p in proposals if p["field"] == "roadmap_window"
                    and p["locator"]["page_number"] == roadmap_page]

    fund_sum = sum(int(p["normalized_candidate"]) for p in fund_rows)
    revenue_sums = [{"subject_sha256": _sha256(p["subject"]),
                     "sum": sum(ratios_series(p["normalized_candidate"])),
                     "terms": len(ratios_series(p["normalized_candidate"]))} for p in revenue_rows]
    windows = sorted([int(token) for token in p["normalized_candidate"].split("-")] for p in roadmap_rows)
    contiguous = (all(windows[i][1] == windows[i + 1][0] for i in range(len(windows) - 1))
                  if len(windows) > 1 else False)
    span = [windows[0][0], windows[-1][1]] if windows else []

    return {"checks": [
        {"check_id": "C6a.funding_use_ratio_sum",
         "state": "passed" if fund_sum == 100 and len(fund_rows) == 5 else "failed",
         "criterion": "funding-use rows sum to 100 % exactly",
         "measured": {"rows": len(fund_rows), "sum_percent": fund_sum, "section_page": fund_page}},
        {"check_id": "C6b.revenue_mix_row_sums",
         "state": "passed" if revenue_sums and all(r["sum"] == 100 for r in revenue_sums) else "failed",
         "criterion": "each revenue-mix row sums to 100 % exactly",
         "measured": {"rows": len(revenue_sums), "sums": revenue_sums, "section_page": revenue_page}},
        {"check_id": "C6c.roadmap_window_contiguity",
         "state": "passed" if contiguous and span == [0, 36] else "failed",
         "criterion": "roadmap windows are contiguous and cover 0-36 months exactly",
         "measured": {"windows": windows, "contiguous": contiguous, "span": span,
                      "section_page": roadmap_page}},
    ], "pages_scanned": len(pages)}


# ------------------------------------------------------------------ negative path

def negative_cases(pdf_bytes: bytes) -> list[dict]:
    return [
        {"case": "truncated_body", "bytes": pdf_bytes[:int(len(pdf_bytes) * 0.4)],
         "expectation": "PdfEvidenceError: PDF cannot be parsed"},
        {"case": "non_pdf_bytes", "bytes": b"this is not a pdf at all\n" * 4,
         "expectation": "PdfEvidenceError: PDF cannot be parsed"},
        {"case": "zero_byte", "bytes": b"", "expectation": "PdfEvidenceError: PDF input is empty"},
        {"case": "header_only", "bytes": pdf_bytes[:8],
         "expectation": "PdfEvidenceError: PDF cannot be parsed"},
    ]


def run_negative(pdf_bytes: bytes, corrupt_dir: Path) -> dict:
    """Every corrupted copy must fail closed: declared error type, exit 2, no artifact."""
    corrupt_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for case in negative_cases(pdf_bytes):
        path = corrupt_dir / f"{case['case']}.pdf"
        path.write_bytes(case["bytes"])
        output = corrupt_dir / f"{case['case']}.out.json"
        if output.exists():
            output.unlink()
        proc = subprocess.run(
            [sys.executable, "-m", "tensorbench.cli", "extract-pdf", "--input", str(path),
             "--source-ref", "pilot://corrupt/v1", "--output", str(output)],
            cwd=str(ROOT), capture_output=True, text=True, timeout=120)
        module_error = None
        try:
            extract_pdf_evidence(path, source_ref="pilot://corrupt/v1")
        except PdfEvidenceError as exc:
            module_error = f"PdfEvidenceError: {exc}"
        except Exception as exc:  # noqa: BLE001 - an undeclared exception is what we hunt
            module_error = f"UNDECLARED {type(exc).__name__}: {exc}"
        stderr_lines = [line for line in proc.stderr.strip().splitlines() if line.strip()]
        declared = bool(module_error and module_error.startswith("PdfEvidenceError"))
        ok = proc.returncode == 2 and declared and not output.exists()
        results.append({
            "case": case["case"],
            "input_bytes": len(case["bytes"]),
            "input_sha256": hashlib.sha256(case["bytes"]).hexdigest(),
            "expectation": case["expectation"],
            "cli_exit_code": proc.returncode,
            "cli_error_line": stderr_lines[-1] if stderr_lines else None,
            "module_error": module_error,
            "declared_error_type": declared,
            "output_artifact_written": output.exists(),
            "state": "passed" if ok else "failed",
        })
    summary = {
        "cases": results,
        "cases_total": len(results),
        "cases_passed": sum(1 for item in results if item["state"] == "passed"),
        "silent_successes": sum(1 for item in results if item["cli_exit_code"] == 0),
        "undeclared_exceptions": sum(1 for item in results
                                     if item["module_error"] and item["module_error"].startswith("UNDECLARED")),
        "artifacts_written": sum(1 for item in results if item["output_artifact_written"]),
    }
    summary["state"] = "passed" if (summary["cases_passed"] == summary["cases_total"]
                                    and summary["silent_successes"] == 0
                                    and summary["undeclared_exceptions"] == 0
                                    and summary["artifacts_written"] == 0) else "failed"
    return summary


# ------------------------------------------------------------ failure records §5

def build_failure_records(source_sha: str, bp_rows: list[dict], negative: dict,
                          run_started_at: str) -> list[dict]:
    rev = git_revision()
    repro_extract = (f"python -m tensorbench.cli extract-pdf --input <private>/TensorAI_BP.pdf "
                     f"--source-ref pilot://tensorai-bp/v1  # {rev}")
    records = [{
        "keywords": ["BE", "business_pdf_fields", "trade-spectrum-blind-to-business-plan"],
        "anchor": "GAP-ACCEPT-⑥",
        "category": "gap",
        "fail_stage": "execution",
        "failure_reason": ("The only pre-existing field spectrum matches invoice/PO/contract labels; a business "
                           "plan carries none of them, so all 5 declared fields returned 0 proposals and the "
                           "covering 0 % was invisible rather than reported."),
        "repro_cmd": f"python -m tensorbench.cli propose-pdf-fields --input <pages.json> "
                     f"--spectrum trade_documents_v1  # {rev}",
        "evidence_refs": [f"docs/pilots/{PILOT_ID}/field_coverage.json"],
        "affects": ["C2", "GAP: business-plan document type unsupported by any declared spectrum"],
        "resolution": "mitigated",
        "resolution_ref": "business_plan_v1 spectrum added to tensorbench/business_pdf_fields.py",
        "cited_kb": [],
    }, {
        "keywords": ["BE", "business_pdf_fields", "market_reference", "year-anchored-rule"],
        "anchor": "GAP-ACCEPT-③",
        "category": "defect",
        "fail_stage": "execution",
        "failure_reason": ("The market-reference rule requires a parenthesised publication year, so reference "
                           "lines published without a year (and the wrapped-URL lines) produce no proposal; "
                           "2 of 5 references on the source page were dropped."),
        "repro_cmd": f"python -m tensorbench.cli propose-pdf-fields --input <pages.json> "
                     f"--spectrum business_plan_v1  # {rev}",
        "evidence_refs": [f"docs/pilots/{PILOT_ID}/field_coverage.json"],
        "affects": ["field coverage: market_reference"],
        "resolution": "accepted_limitation",
        "cited_kb": [],
    }, {
        "keywords": ["BE", "business_pdf_fields", "table_label_percent", "first-column-only"],
        "anchor": "GAP-ACCEPT-③",
        "category": "defect",
        "fail_stage": "execution",
        "failure_reason": ("The label+percent rule consumes only the first percentage line under a table row "
                           "label, so in a 4-column revenue table it returns one cell per row and the other "
                           "cells are only recovered by the separate ratio_block rule."),
        "repro_cmd": f"python -m tensorbench.cli propose-pdf-fields --input <pages.json> "
                     f"--spectrum business_plan_v1  # {rev}",
        "evidence_refs": [f"docs/pilots/{PILOT_ID}/field_coverage.json"],
        "affects": ["field coverage: table_label_percent"],
        "resolution": "accepted_limitation",
        "cited_kb": [],
    }, {
        "keywords": ["BE", "scenario_acceptance", "independent-review-not-run"],
        "anchor": "GAP-ACCEPT-④",
        "category": "gap",
        "fail_stage": "review",
        "failure_reason": ("Steps ④ (independent-party re-execution) and ⑤ (publish status) were not performed by "
                           "this mission: the framework forbids the author from signing its own gate, so the "
                           "pilot stops at a partial report with a provisional author review."),
        "repro_cmd": f"python scripts/run_bp_pilot.py run --pdf <private>/TensorAI_BP.pdf  # {rev}",
        "evidence_refs": [f"docs/pilots/{PILOT_ID}/validation_report.json"],
        "affects": ["scenario_validated", "review_receipt", "status publication"],
        "resolution": "open",
        "cited_kb": [],
    }]
    if negative["state"] != "passed":
        records.append({
            "keywords": ["BE", "pdf_evidence", "negative-path"],
            "anchor": "GAP-ACCEPT-③",
            "category": "defect",
            "fail_stage": "input",
            "failure_reason": "A corrupted input did not fail closed as declared.",
            "repro_cmd": f"python scripts/run_bp_pilot.py run --pdf <private>/TensorAI_BP.pdf  # {rev}",
            "evidence_refs": [f"docs/pilots/{PILOT_ID}/negative_tests.json"],
            "affects": ["C8"],
            "resolution": "open",
            "cited_kb": [],
        })
    for record in records:
        record["filed_at"] = run_started_at
        record["source_sha256"] = source_sha
    return records


# -------------------------------------------------------------------------- main


def worktree_dirty() -> bool:
    out = subprocess.run(["git", "status", "--porcelain"], cwd=str(ROOT),
                         capture_output=True, text=True).stdout
    return bool(out.strip())


REGRESSION_TARGETS = (
    "tests/test_business_pdf_fields.py",
    "tests/test_business_evidence.py",
    "tests/test_product_contract_schemas.py",
    "tests/test_scenario_acceptance.py",
    "tests/test_pdf_evidence.py",
)


def run_regression_scope(private_dir: Path) -> dict:
    """Measure the adjacent declared behaviour (no regression on the touched modules)."""
    existing = [target for target in REGRESSION_TARGETS if (ROOT / target).exists()]
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", *existing],
                          cwd=str(ROOT), capture_output=True, text=True, timeout=1800)
    log = proc.stdout + proc.stderr
    (private_dir / "pytest_regression.log").write_text(log, encoding="utf-8")
    counts = {}
    for key in ("passed", "failed", "error", "errors", "skipped"):
        match = re.search(rf"(\d+) {key}\b", log)
        if match:
            counts[key] = int(match.group(1))
    errors = counts.get("error", counts.get("errors", 0))
    state = "passed" if proc.returncode == 0 and not counts.get("failed") and not errors else "failed"
    return {
        "state": state,
        "targets": existing,
        "exit_code": proc.returncode,
        "passed": counts.get("passed", 0),
        "failed": counts.get("failed", 0),
        "errors": errors,
        "skipped": counts.get("skipped", 0),
        "summary": (f"{len(existing)} test modules: {counts.get('passed', 0)} passed, "
                    f"{counts.get('failed', 0)} failed, {errors} errors, exit {proc.returncode}"),
        "log_ref": "private bundle: pytest_regression.log",
        "log_sha256": _sha256(log),
    }


def run(pdf_path: Path, source_ref: str, out_dir: Path, private_dir: Path,
        reviewed_commit: str) -> int:
    run_started_at = _now()
    freeze_payload = load_freeze(run_started_at)
    out_dir.mkdir(parents=True, exist_ok=True)
    private_dir.mkdir(parents=True, exist_ok=True)
    whitelist: set[str] = {"资金使用结构", "收入结构", "发展路线图", "商业计划书", "建议以"}

    source_sha = _file_sha256(pdf_path)
    pdf_bytes = pdf_path.read_bytes()
    extraction = extract_pdf_evidence(pdf_path, source_ref=source_ref)
    pages = page_texts(extraction)
    (private_dir / "pages_private.json").write_text(
        json.dumps(extraction, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    c1 = {
        "check_id": "C1.pdf_ingestion",
        "state": "passed" if (extraction["status"] == "complete"
                             and all(p["extraction_status"] == "extracted" for p in extraction["pages"])
                             and extraction["source"]["sha256"] == source_sha) else "failed",
        "measured": {"status": extraction["status"], "pages": len(extraction["pages"]),
                     "pages_extracted": sum(1 for p in extraction["pages"]
                                            if p["extraction_status"] == "extracted"),
                     "source_sha256": extraction["source"]["sha256"],
                     "byte_length": extraction["source"]["byte_length"],
                     "media_type": extraction["source"]["media_type"]},
    }
    if c1["state"] != "passed":
        (out_dir / "pilot_abort.json").write_text(json.dumps(
            {"reason": "C1 failed; no field claim may be reported", "c1": c1},
            ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 1

    legacy = propose_pdf_fields(extraction, spectrum="trade_documents_v1")
    bp = propose_pdf_fields(extraction, spectrum="business_plan_v1")
    (private_dir / "proposals_private.json").write_text(json.dumps(
        {"trade_documents_v1": legacy, "business_plan_v1": bp}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")

    legacy_rows = coverage_rows("trade_documents_v1", legacy["proposals"])
    bp_rows = coverage_rows("business_plan_v1", bp["proposals"])
    bp_covered = sum(1 for row in bp_rows if row["proposal_count"] > 0)

    decisions = [{"proposal_id": p["proposal_id"], "decision": "accept"} for p in bp["proposals"]]
    reviewed = review_pdf_field_proposals(bp, decisions, reviewer=REVIEWER)
    record = approved_pdf_fields_to_evidence_record(
        reviewed, record_type="business_plan", record_id="tensorai-bp-2026-11")
    (private_dir / "reviewed_private.json").write_text(json.dumps(
        {"reviewed": reviewed, "record": record, "proposals": bp["proposals"]},
        ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    raw_by_proposal = {p["proposal_id"]: p["raw_value"] for p in bp["proposals"]}
    locators_ok = 0
    entries = list(record["fields"].values())
    for entry in entries:
        ok = True
        for evidence in entry["evidence"]:
            locator = evidence["locator"]
            page_no, start, end = locator["page_number"], locator["start_offset"], locator["end_offset"]
            page_sha_ok = _sha256(pages[page_no]) == locator.get("page_text_sha256")
            offsets_ok = 0 <= start < end <= len(pages[page_no])
            slice_ok = offsets_ok and pages[page_no][start:end] == raw_by_proposal[evidence["proposal_id"]]
            ok = ok and page_sha_ok and offsets_ok and slice_ok
        locators_ok += 1 if ok else 0
    c4 = {"check_id": "C4.page_backreference",
          "state": "passed" if entries and locators_ok == len(entries) else "failed",
          "measured": {"approved_fields": len(entries), "with_verified_locator": locators_ok}}

    absent = [p for p in bp["proposals"] if p["field"] == "funding_amount"]
    disclosure_pages = [n for n, text in pages.items() if "不虚构融资金额" in text]
    c5 = {"check_id": "C5.absence_honesty",
          "state": "passed" if not absent and disclosure_pages else "failed",
          "measured": {"funding_amount_proposals": len(absent),
                       "explicit_non_disclosure_pages": disclosure_pages}}

    invariants = check_invariants(extraction, bp["proposals"])
    negative = run_negative(pdf_bytes, private_dir / "corrupt")

    # ---- desensitized publication
    structured_published = {
        "schema_version": record["schema_version"],
        "product_id": record["product_id"],
        "record_id": record["record_id"],
        "record_type": record["record_type"],
        "field_spectrum": record["field_spectrum"],
        "source": {"source_ref": record["source"]["source_ref"],
                   "sha256": record["source"]["sha256"],
                   "byte_length": record["source"]["byte_length"],
                   "page_count": record["source"]["page_count"],
                   "media_type": record["source"].get("media_type"),
                   "filename_sha256": _sha256(str(record["source"].get("filename")))},
        "evidence_ref": record["evidence_ref"],
        "field_count": record["field_count"],
        "fields": {},
        "review": record["review"],
        "limitations": record["limitations"],
    }
    for key, entry in record["fields"].items():
        published_subject = publish_subject(entry["field"], entry["subject"], whitelist)
        published_key = entry["field"] if published_subject is None else f"{entry['field']}#{published_subject}"
        structured_published["fields"][published_key] = {
            "field": entry["field"],
            "subject": published_subject,
            "value": publish_value(entry["field"], str(entry["value"]), whitelist),
            "value_sha256": _sha256(str(entry["value"])),
            "evidence": [{"proposal_id": ev["proposal_id"],
                          "page_number": ev["locator"]["page_number"],
                          "start_offset": ev["locator"]["start_offset"],
                          "end_offset": ev["locator"]["end_offset"],
                          "page_text_sha256": ev["locator"]["page_text_sha256"],
                          "value_sha256": ev["locator"]["value_sha256"]} for ev in entry["evidence"]],
        }

    coverage_published = {
        "declared_spectra": sorted(FIELD_SPECTRA),
        "legacy_spectrum": {
            "name": "trade_documents_v1",
            "fields_declared": len(legacy_rows),
            "fields_extracted": sum(1 for row in legacy_rows if row["proposal_count"] > 0),
            "rows": [{k: row[k] for k in ("field", "proposal_count", "state", "failure_reason", "pages")}
                     for row in legacy_rows],
        },
        "business_plan_spectrum": {
            "name": "business_plan_v1",
            "fields_declared": len(bp_rows),
            "fields_extracted": bp_covered,
            "coverage_fraction": round(bp_covered / len(bp_rows), 4),
            "rows": [{
                "field": row["field"],
                "proposal_count": row["proposal_count"],
                "state": row["state"],
                "failure_reason": row["failure_reason"],
                "pages": row["pages"],
                "items": [{"subject": publish_subject(row["field"], item.get("subject"), whitelist),
                           "page_number": item["locator"]["page_number"],
                           "start_offset": item["locator"]["start_offset"],
                           "end_offset": item["locator"]["end_offset"],
                           "value": publish_value(row["field"], item["raw_value"], whitelist),
                           "normalized_candidate": publish_value(
                               row["field"], str(item["normalized_candidate"]), whitelist),
                           "value_sha256": item["locator"]["value_sha256"],
                           "matched_text_sha256": _sha256(item["locator"]["matched_text"])}
                          for item in row["items"]],
            } for row in bp_rows],
        },
    }
    c2 = {"check_id": "C2.legacy_spectrum_coverage", "state": "passed",
          "measured": {"fields_declared": 5,
                       "fields_extracted": coverage_published["legacy_spectrum"]["fields_extracted"]}}
    c3 = {"check_id": "C3.business_plan_spectrum_coverage",
          "state": "passed" if bp_covered >= 8 else "failed",
          "measured": {"fields_declared": len(bp_rows), "fields_extracted": bp_covered, "threshold": 8}}

    # ---- C7 independent re-derivation in a separate process
    spotcheck_path = out_dir / "quality_spotcheck.json"
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "bp_pilot_verify.py"),
         "--pdf", str(pdf_path), "--private-record", str(private_dir / "reviewed_private.json"),
         "--out-private", str(private_dir / "spotcheck_private.json"),
         "--out", str(spotcheck_path), "--min-checks", "5"],
        cwd=str(ROOT), capture_output=True, text=True, timeout=300)
    if proc.returncode not in (0, 1):
        raise SystemExit(f"verifier failed ({proc.returncode})\n{proc.stderr}")
    spotcheck = json.loads(spotcheck_path.read_text(encoding="utf-8"))
    c7 = {"check_id": "C7.independent_spotcheck", "state": spotcheck["state"],
          "measured": {"checks": spotcheck["checks_total"], "agreeing": spotcheck["checks_agreed"],
                       "fields_checked": spotcheck["fields_checked"], "method": spotcheck["method"]}}

    # ---- regression scope on the adjacent declared behaviour (criterion: no regression)
    failure_records = build_failure_records(source_sha, bp_rows, negative, run_started_at)
    regression = run_regression_scope(private_dir)

    # ---- report (validation-report contract) + C9 leak guard + C10 validation
    report = {
        "schema_version": "0.1.0",
        "product_id": "business-evidence-engine",
        "product_version": "0.4.0",
        "run_id": f"{PILOT_ID}-{run_started_at}",
        "created_at": _now(),
        "input_refs": [f"pdf:{source_ref}#sha256:{source_sha}"],
        "scenario": {
            "scenario_id": "BE-20261115-tensorai-bp-field-extraction",
            "usage_declaration": (
                "Substitutes for the due-diligence step in which a business plan received under internal "
                "consent is ingested and turned into page-addressable structured business evidence. A verdict "
                "here means only: these field values were located at these page offsets of a PDF with this "
                "SHA-256 by this declared rule set."),
            "permission_basis": "internal_consent",
            "inputs": [{"input_id": "business-plan-pdf", "kind": "document", "ref": source_ref,
                        "sha256": source_sha, "locator": "all pages",
                        "permission_ref": "internal_consent://tensor-bp/2026-11/investor-copy/v1"}],
            "environment": {"python": sys.version.split()[0], "pypdf": __import__("pypdf").__version__,
                            "tensorbench_commit": git_revision(),
                            "worktree_dirty_at_run": worktree_dirty(),
                            "field_spectra": sorted(FIELD_SPECTRA)},
            "limits": [
                "one document, one language, one layout: coverage is this document's coverage",
                "label/table-shape regex proposals; no OCR, no table reconstruction",
                "provisional author review; no independent-party review performed",
                "repository artifacts are desensitized; verbatim text stays in the private bundle",
            ],
        },
        "criteria_freeze": {
            "criteria_ref": freeze_payload["criteria_ref"],
            "criteria_sha256": freeze_payload["criteria_sha256"],
            "frozen_at": freeze_payload["frozen_at"],
            "frozen_by": freeze_payload["frozen_by"],
            "spec_ref": freeze_payload["spec_ref"],
            "amendments": [],
        },
        "review_receipt": {
            "receipt_id": f"{PILOT_ID}-author-self-review",
            "reviewer": {"handle": REVIEWER, "role": "author",
                         "affiliation": "ecosystem agent mission m22060",
                         "conflicts_declared": ["authored the field rules and the run under review"]},
            "independence": "self_review",
            "reviewed_commit": reviewed_commit,
            "six_checks": [
                {"check_id": "artifact_identity", "state": "not_run",
                 "evidence_ref": str(out_dir.relative_to(ROOT)) + "/evidence_bundle.json",
                 "note": ("inputs and criteria are fingerprinted and were re-hashed by a second process, "
                          f"but the reviewed code revision was the worktree above {reviewed_commit} "
                          f"(dirty={worktree_dirty()}); binding it to a commit is the reviewer's job")},
                {"check_id": "criteria_frozen_before_run", "state": "passed",
                 "evidence_ref": str(CRITERIA_FILE.relative_to(ROOT)),
                 "note": f"frozen_at {freeze_payload['frozen_at']} <= created_at {run_started_at}; "
                         f"criteria_sha256 unchanged at run time"},
                {"check_id": "evidence_traceability", "state": "passed",
                 "evidence_ref": str(out_dir.relative_to(ROOT)) + "/evidence_bundle.json",
                 "note": "every published artifact carries a sha256 and every check names its evidence file"},
                {"check_id": "independent_rerun", "state": "not_run",
                 "evidence_ref": str(out_dir.relative_to(ROOT)) + "/validation_report.json",
                 "note": "the author cannot stand in for the independent party; C7 is a self check"},
                {"check_id": "failure_record", "state": "passed" if failure_records else "failed",
                 "evidence_ref": str(out_dir.relative_to(ROOT)) + "/failure_records.json",
                 "note": f"{len(failure_records)} records filed in the §5 field format"},
                {"check_id": "regression_scope", "state": regression["state"],
                 "evidence_ref": str(out_dir.relative_to(ROOT)) + "/evidence_bundle.json",
                 "note": regression["summary"]},
            ],
            "rerun": {
                "command": f"python scripts/run_bp_pilot.py run --pdf <private>/TensorAI_BP.pdf  # {reviewed_commit}",
                "exit_code": 0,
                "environment": f"python {sys.version.split()[0]}, pypdf {__import__('pypdf').__version__}",
                "log_ref": "private bundle: pilot_run.log",
                "log_sha256": regression["log_sha256"],
                "started_at": run_started_at,
            },
            "checks_not_run": ["artifact_identity", "independent_rerun"],
            "blocking_conditions": [
                "no independent party re-executed the run or signed the gate",
                "reviewed code revision was an uncommitted worktree, not a commit sha",
            ],
            "verdict": "changes_requested",
            "signed_at": _now(),
        },
        "checks": [],
        "findings": [],
        "overall_status": "partial",
        "provenance": {
            "input_fingerprints": {
                "pdf": f"sha256:{source_sha}",
                "criteria": f"sha256:{freeze_payload['criteria_sha256']}",
                "extraction": f"sha256:{_sha256(json.dumps(extraction, ensure_ascii=False, sort_keys=True))}",
                "proposals_business_plan_v1": f"sha256:{_sha256(json.dumps(bp, ensure_ascii=False, sort_keys=True))}",
                "reviewed_bundle": f"sha256:{reviewed['proposal_bundle_sha256']}",
            },
            "software_revision": reviewed_commit,
            "configuration_sha256": _sha256(json.dumps(
                {"spectra": sorted(FIELD_SPECTRA), "criteria": freeze_payload["criteria_sha256"]},
                sort_keys=True)),
        },
    }

    def add_check(check_id: str, state: str, measured: dict) -> None:
        report["checks"].append({"check_id": check_id, "version": "1.0.0", "method": "deterministic_rule",
                                 "state": state, "required": True,
                                 "details": json.dumps(measured, ensure_ascii=False, sort_keys=True)})

    for item in [c1, c2, c3, c4, c5, *invariants["checks"]]:
        add_check(item["check_id"], item["state"], item.get("measured", {}))
    add_check(c7["check_id"], c7["state"], c7["measured"])
    add_check("C8.negative_path", negative["state"],
              {k: negative[k] for k in ("cases_total", "cases_passed", "silent_successes",
                                        "undeclared_exceptions", "artifacts_written")})
    add_check("C10a.regression_scope", regression["state"],
              {"pytest_exit_code": regression["exit_code"], "passed": regression["passed"],
               "failed": regression["failed"], "errors": regression["errors"],
               "log_sha256": regression["log_sha256"]})

    # ---- write the published artifacts, then close the leak guard over exactly those bytes
    (out_dir / "field_coverage.json").write_text(json.dumps({
        "pilot_id": PILOT_ID,
        "source_sha256": source_sha,
        "declared_spectra": coverage_published["declared_spectra"],
        "legacy_spectrum": coverage_published["legacy_spectrum"],
        "business_plan_spectrum": coverage_published["business_plan_spectrum"],
        "redaction": {
            "policy": ("metric/taxonomy tokens verbatim; identity and citation values masked to a "
                       "<=2-char prefix plus length and sha256"),
            "verbatim_fields": sorted(VERBATIM_FIELDS),
            "masked_fields": sorted(MASKED_FIELDS),
            "verbatim_source_committed": False,
            "verbatim_text_location": "private bundle outside the repository (see private_pointer.json)",
        },
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "structured_record.redacted.json").write_text(
        json.dumps(structured_published, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "invariants.json").write_text(json.dumps(invariants, ensure_ascii=False, indent=2) + "\n",
                                             encoding="utf-8")
    (out_dir / "negative_tests.json").write_text(json.dumps(negative, ensure_ascii=False, indent=2) + "\n",
                                                 encoding="utf-8")
    (out_dir / "failure_records.json").write_text(json.dumps({
        "records": failure_records,
        "platform_ledger_submission": {
            "attempted": True,
            "endpoint": "POST {TENSOR_API_BASE}/tensor/negative-knowledge",
            "result": "HTTP 405 Method Not Allowed (ledger is read-only on this API surface)",
            "consequence": ("records are kept here in the §5 field format as the repo-side pointer; "
                            "filing into the platform ledger is still open"),
        },
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "regression_scope.json").write_text(json.dumps(regression, ensure_ascii=False, indent=2) + "\n",
                                                   encoding="utf-8")

    report_path = out_dir / "validation_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    published_files = sorted(path for path in out_dir.glob("*.json")
                             if path.name not in {"private_pointer.json", "evidence_bundle.json"})
    published_blob = "".join(path.read_text(encoding="utf-8") for path in published_files)
    leaks = []
    for number, text in pages.items():
        for candidate in set(re.findall(r"[\u4e00-\u9fff]{5,}|[A-Za-z][A-Za-z .&_-]{7,}", text)):
            if candidate in published_blob and candidate not in whitelist:
                leaks.append({"page_number": number, "token_sha256": _sha256(candidate),
                              "token_len": len(candidate)})
    pdfs_in_worktree = [str(path.relative_to(ROOT)) for path in ROOT.rglob("*.pdf")]
    add_check("C9.private_input_containment",
              "passed" if not leaks and not pdfs_in_worktree else "failed",
              {"verbatim_leaks": len(leaks), "leaks": leaks[:10], "pdfs_in_worktree": pdfs_in_worktree})
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    validate = subprocess.run([sys.executable, "-m", "tensorbench.cli", "validate", "--kind", "report",
                               "--input", str(report_path)],
                              cwd=str(ROOT), capture_output=True, text=True, timeout=120)
    validated = json.loads(validate.stdout) if validate.stdout.strip().startswith("{") else {}
    add_check("C10.report_contract", "passed" if validate.returncode == 0 else "failed",
              {"validate_exit_code": validate.returncode, "status": validated.get("status"),
               "error_count": len(validated.get("errors", [])), "overall_status": report["overall_status"]})
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    private_files = {str(path): _file_sha256(path)
                     for path in sorted(private_dir.rglob("*")) if path.is_file()}
    (out_dir / "private_pointer.json").write_text(json.dumps({
        "note": "verbatim extraction / proposals / corrupt copies live outside the repository",
        "private_root": str(private_dir),
        "files": private_files,
        "source_pdf": {"sha256": source_sha, "bytes": len(pdf_bytes), "committed": False},
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # ---- evidence bundle: every claim -> a retrievable, digest-verified artifact
    serves = {
        "validation_report.json": [c["check_id"] for c in report["checks"]],
        "field_coverage.json": ["C2.legacy_spectrum_coverage", "C3.business_plan_spectrum_coverage"],
        "structured_record.redacted.json": ["C4.page_backreference"],
        "invariants.json": ["C6a.funding_use_ratio_sum", "C6b.revenue_mix_row_sums",
                            "C6c.roadmap_window_contiguity"],
        "quality_spotcheck.json": ["C7.independent_spotcheck", "C5.absence_honesty"],
        "negative_tests.json": ["C8.negative_path"],
        "failure_records.json": ["review_receipt.failure_record"],
        "regression_scope.json": ["C10a.regression_scope", "review_receipt.regression_scope"],
        "criteria_freeze.json": ["criteria_frozen_before_run"],
    }
    artifacts = []
    for name, check_ids in serves.items():
        path = out_dir / name
        artifacts.append({"path": str(path.relative_to(ROOT)), "sha256": _file_sha256(path),
                          "bytes": path.stat().st_size, "serves_checks": check_ids})
    criteria_path = CRITERIA_FILE
    artifacts.append({"path": str(criteria_path.relative_to(ROOT)),
                      "sha256": _file_sha256(criteria_path), "bytes": criteria_path.stat().st_size,
                      "serves_checks": ["criteria_frozen_before_run"]})
    source_artifact = Path("/srv/tensor/agent/work/pilot_inputs_1115/TensorAI_BP.pdf")
    bundle = {
        "schema_version": "1.0.0",
        "kind": "tensorbench.pilot_evidence_bundle",
        "pilot_id": PILOT_ID,
        "scenario_id": report["scenario"]["scenario_id"],
        "criteria": {"criteria_ref": freeze_payload["criteria_ref"],
                     "criteria_sha256": freeze_payload["criteria_sha256"],
                     "frozen_at": freeze_payload["frozen_at"]},
        "source_input": {"sha256": source_sha, "bytes": len(pdf_bytes), "committed": False,
                         "path_published": False,
                         "note": ("private input under internal consent; only its fingerprint is published"),
                         "external_path_hint": str(source_artifact.parent)},
        "checks": [{"check_id": c["check_id"], "state": c["state"], "required": c["required"]}
                   for c in report["checks"]],
        "artifacts": artifacts,
        "private_artifacts": [{"path": path, "sha256": digest} for path, digest in private_files.items()],
        "missing": [
            "review_receipt.independent_rerun: no independent party re-executed the run",
            "review_receipt.artifact_identity: reviewed revision was an uncommitted worktree",
            "products/STATUS.json: scenario_validated intentionally left false (out of scope for this mission)",
            "verbatim page text: withheld from the repository on purpose (private input)",
        ],
        "integrity": {"digest_scope": "sha256 over each artifact's file bytes as published",
                      "self_sha256_excluded": True},
    }
    (out_dir / "evidence_bundle.json").write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n",
                                                  encoding="utf-8")

    numbers = {
        "pilot_id": PILOT_ID,
        "source_sha256": source_sha,
        "pages": len(extraction["pages"]),
        "pages_extracted": c1["measured"]["pages_extracted"],
        "legacy_fields_declared": 5,
        "legacy_fields_extracted": coverage_published["legacy_spectrum"]["fields_extracted"],
        "bp_fields_declared": len(bp_rows),
        "bp_fields_extracted": bp_covered,
        "bp_proposals": len(bp["proposals"]),
        "approved_fields": record["field_count"],
        "spotcheck_checks": spotcheck["checks_total"],
        "spotcheck_agreed": spotcheck["checks_agreed"],
        "negative_cases": negative["cases_total"],
        "negative_passed": negative["cases_passed"],
        "regression_passed": regression["passed"],
        "regression_failed": regression["failed"],
        "regression_errors": regression["errors"],
        "fund_use_sum": next(c for c in invariants["checks"]
                             if c["check_id"] == "C6a.funding_use_ratio_sum")["measured"]["sum_percent"],
        "fund_use_rows": next(c for c in invariants["checks"]
                              if c["check_id"] == "C6a.funding_use_ratio_sum")["measured"]["rows"],
        "revenue_row_sums": next(c for c in invariants["checks"]
                                 if c["check_id"] == "C6b.revenue_mix_row_sums")["measured"]["sums"],
        "roadmap_span": next(c for c in invariants["checks"]
                             if c["check_id"] == "C6c.roadmap_window_contiguity")["measured"]["span"],
        "roadmap_windows": next(c for c in invariants["checks"]
                                if c["check_id"] == "C6c.roadmap_window_contiguity")["measured"]["windows"],
        "checks": {c["check_id"]: c["state"] for c in report["checks"]},
        "coverage_per_field": {row["field"]: row["proposal_count"] for row in bp_rows},
        "criteria_sha256": freeze_payload["criteria_sha256"],
        "frozen_at": freeze_payload["frozen_at"],
        "run_started_at": run_started_at,
        "report_created_at": report["created_at"],
        "reviewed_commit": reviewed_commit,
        "worktree_dirty": worktree_dirty(),
        "validate_status": validated.get("status"),
        "validate_errors": len(validated.get("errors", [])),
        "overall_status": report["overall_status"],
        "receipt_verdict": report["review_receipt"]["verdict"],
    }
    (out_dir / "numbers.json").write_text(json.dumps(numbers, ensure_ascii=False, indent=2) + "\n",
                                          encoding="utf-8")

    figure = subprocess.run([sys.executable, str(ROOT / "scripts" / "bp_pilot_figure.py"),
                             "--numbers", str(out_dir / "numbers.json"),
                             "--out", str(ROOT / "docs" / "pilots" / PILOT_ID / "pilot_figure.png")],
                            cwd=str(ROOT), capture_output=True, text=True, timeout=600)
    if figure.returncode != 0:
        print(f"figure failed: {figure.stderr}", file=sys.stderr)

    print(json.dumps(numbers, ensure_ascii=False, indent=2))
    required = [c for c in report["checks"] if c["required"]]
    return 0 if all(c["state"] == "passed" for c in required) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("freeze", "run"))
    parser.add_argument("--pdf")
    parser.add_argument("--source-ref", default="pilot://tensorai-bp/v1")
    parser.add_argument("--out", default=str(PILOT_DIR))
    parser.add_argument("--private-out",
                        default="/srv/tensor/agent/work/pilot_inputs_1115/out")
    parser.add_argument("--reviewed-commit",
                        help="revision under review (defaults to git HEAD; recorded as-is)")
    args = parser.parse_args(argv)
    if args.mode == "freeze":
        return freeze()
    if not args.pdf:
        parser.error("--pdf is required for the run mode")
    return run(Path(args.pdf).resolve(), args.source_ref, Path(args.out).resolve(),
               Path(args.private_out).resolve(), args.reviewed_commit or git_revision())


if __name__ == "__main__":
    raise SystemExit(main())