#!/usr/bin/env python3
"""End-to-end demo of the Business Evidence Engine chain (mission m22925, packaging increment).

It walks the *real* product surface — four CLI commands, in sequence, in one process tree —
on a synthetic invoice PDF, then reconciles the extracted invoice against a purchase order:

    extract-pdf -> propose-pdf-fields -> review-pdf-fields -> reconcile-business

Two reconciliation bundles are run: a consistent one (invoice total == PO total) and an
inconsistent one (PO total differs by 0.50). The second exists to show that a mismatch is
reported, not smoothed over. Every stage is timed so the value record's duration/automation
dimensions have measured inputs instead of guesses.

Artifacts land in ``docs/m22925/demo/`` (committed; not in runs/artifacts, which the pusher
filters out). Deterministic: the same PDF and bundle set produce byte-identical JSON apart
from the ``created_at`` timestamps.

    python3 docs/m22925/run_demo.py
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DEMO = HERE / "demo"
PY = sys.executable


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(stage: str, argv: list[str]) -> dict:
    """Run one real CLI command, time it, and record everything needed to re-run it."""
    started = time.perf_counter()
    proc = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True)
    elapsed = time.perf_counter() - started
    if proc.returncode not in (0, 1):
        sys.stderr.write(proc.stdout + proc.stderr)
        raise SystemExit(f"stage {stage} failed with exit {proc.returncode}")
    return {
        "stage": stage,
        "command": " ".join(Path(a).name if i == 0 and a == PY else a for i, a in enumerate(argv)),
        "cwd": "worktree root",
        "exit_code": proc.returncode,
        "wall_seconds": round(elapsed, 3),
        "stdout_bytes": len(proc.stdout.encode()),
    }


def main() -> int:
    DEMO.mkdir(parents=True, exist_ok=True)
    stages: list[dict] = []

    # stage 0 — build the synthetic demo PDF (input generation, not part of the product)
    pdf = DEMO / "demo_invoice.pdf"
    subprocess.run([PY, str(HERE / "make_demo_pdf.py"), str(pdf)], cwd=ROOT, check=True,
                   capture_output=True, text=True)
    pdf_sha = sha256_file(pdf)

    # stage 1 — PDF -> page-addressable text evidence
    stages.append(run("extract-pdf", [
        PY, "-m", "tensorbench", "extract-pdf",
        "--input", str(pdf.relative_to(ROOT)),
        "--source-ref", "demo://m22925/demo-invoice/v1",
        "--output", str((DEMO / "1_pages.json").relative_to(ROOT)),
    ]))

    # stage 2 — text evidence -> unverified field proposals
    stages.append(run("propose-pdf-fields", [
        PY, "-m", "tensorbench", "propose-pdf-fields",
        "--input", str((DEMO / "1_pages.json").relative_to(ROOT)),
        "--spectrum", "trade_documents_v1",
        "--output", str((DEMO / "2_proposals.json").relative_to(ROOT)),
    ]))
    proposals = json.loads((DEMO / "2_proposals.json").read_text(encoding="utf-8"))

    # stage 3 — explicit review decisions. The demo reviewer accepts the first proposal of
    # each field and is named as an automated demo reviewer, so no claim of human review is made.
    decisions = []
    seen_fields: set[str] = set()
    for proposal in proposals["proposals"]:
        field = proposal["field"]
        decisions.append({
            "proposal_id": proposal["proposal_id"],
            "decision": "accept" if field not in seen_fields else "reject",
        })
        seen_fields.add(field)
    (DEMO / "3_decisions.json").write_text(
        json.dumps(decisions, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    stages.append(run("review-pdf-fields", [
        PY, "-m", "tensorbench", "review-pdf-fields",
        "--input", str((DEMO / "2_proposals.json").relative_to(ROOT)),
        "--decisions", str((DEMO / "3_decisions.json").relative_to(ROOT)),
        "--reviewer", "demo-auto-review (TensorBench onboarding demo, not a human reviewer)",
        "--document-type", "invoice",
        "--doc-id", "INV-2026-001",
        "--output", str((DEMO / "4_reviewed.json").relative_to(ROOT)),
    ]))
    reviewed = json.loads((DEMO / "4_reviewed.json").read_text(encoding="utf-8"))
    invoice = dict(reviewed["normalized_document"])
    # Normalisation step performed by the caller (documented in DEMO.md): the extracted
    # po_number becomes the po_ref used for matching, and the line items come from the ERP
    # export that accompanies the PDF. Nothing here is inferred by the adapter.
    invoice["po_ref"] = invoice.get("po_number")
    invoice["supplier_id"] = "SUP-001"
    invoice["buyer_id"] = "BUY-001"
    invoice["line_items"] = [{"sku": "A-1", "quantity": 10, "unit_price": 123.45, "amount": 1234.50}]

    purchase_order = {
        "doc_id": "PO-2026-077",
        "document_type": "purchase_order",
        "po_number": "PO-2026-077",
        "supplier_id": "SUP-001",
        "buyer_id": "BUY-001",
        "currency": invoice.get("currency", "CNY"),
        "document_date": "2026-11-02",
        "line_items": [{"sku": "A-1", "quantity": 10, "unit_price": 123.45, "amount": 1234.50}],
        "total_amount": "1234.50",
        "source_ref": "erp://demo/purchase-order/PO-2026-077/v1",
        "sha256": hashlib.sha256(b"demo purchase order PO-2026-077").hexdigest(),
    }

    # stage 4 — consistent bundle
    bundle_happy = {"documents": [invoice, purchase_order]}
    (DEMO / "5_bundle_happy.json").write_text(
        json.dumps(bundle_happy, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    stages.append(run("reconcile-business (consistent)", [
        PY, "-m", "tensorbench", "reconcile-business",
        "--input", str((DEMO / "5_bundle_happy.json").relative_to(ROOT)),
        "--output", str((DEMO / "6_reconcile_happy.json").relative_to(ROOT)),
    ]))

    # stage 5 — deliberately inconsistent bundle: the PO total is 0.50 lower than the invoice
    purchase_order_mismatch = dict(purchase_order)
    purchase_order_mismatch["line_items"] = [
        {"sku": "A-1", "quantity": 10, "unit_price": 123.40, "amount": 1234.00}]
    purchase_order_mismatch["total_amount"] = "1234.00"
    bundle_bad = {"documents": [invoice, purchase_order_mismatch]}
    (DEMO / "7_bundle_mismatch.json").write_text(
        json.dumps(bundle_bad, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    stages.append(run("reconcile-business (total mismatch)", [
        PY, "-m", "tensorbench", "reconcile-business",
        "--input", str((DEMO / "7_bundle_mismatch.json").relative_to(ROOT)),
        "--output", str((DEMO / "8_reconcile_mismatch.json").relative_to(ROOT)),
    ]))

    happy = json.loads((DEMO / "6_reconcile_happy.json").read_text(encoding="utf-8"))
    bad = json.loads((DEMO / "8_reconcile_mismatch.json").read_text(encoding="utf-8"))
    review_summary = reviewed["review"]["review"]

    report = {
        "demo_id": "BE-m22925-onboarding-demo",
        "product_id": "business-evidence-engine",
        "tensorbench_version": _version(),
        "run_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "environment": {
            "python": sys.version.split()[0],
            "pypdf": _pypdf_version(),
            "cwd": "worktree root",
        },
        "input": {
            "pdf": pdf.relative_to(ROOT).as_posix(),
            "pdf_sha256": pdf_sha,
            "pdf_bytes": pdf.stat().st_size,
            "synthetic": True,
        },
        "stages": stages,
        "spectrum": {
            "name": proposals.get("field_spectrum"),
            "fields_declared": len({p["field"] for p in proposals["proposals"]}) + _absent_fields(proposals),
            "note": "fields_declared counts the declared spectrum; absent fields produce no proposal by design.",
        },
        "totals": {
            "stages": len(stages),
            "wall_seconds_total": round(sum(s["wall_seconds"] for s in stages), 3),
            "auto_steps": len(stages),
            "manual_steps": 1,
            "manual_step_note": "review-pdf-fields decisions must be supplied by a named reviewer; "
                                "in this demo the acceptances were generated (demo auto-review).",
        },
        "extraction": {
            "pages": len(json.loads((DEMO / "1_pages.json").read_text(encoding="utf-8"))["pages"]),
            "proposals": len(proposals["proposals"]),
            "fields_with_proposals": sorted({p["field"] for p in proposals["proposals"]}),
            "reviewed_fields": sorted(reviewed["review"]["approved_fields"]),
            "conflicting_fields": review_summary.get("conflicting_fields", []),
            "pending_proposals": len(review_summary.get("pending_proposal_ids", [])),
        },
        "reconciliation": {
            "consistent_bundle": {
                "overall_status": happy["overall_status"],
                "failed_checks": [c["check_id"] for c in happy["checks"] if c["state"] == "failed"],
                "checks": len(happy["checks"]),
            },
            "mismatch_bundle": {
                "overall_status": bad["overall_status"],
                "failed_checks": [c["check_id"] for c in bad["checks"] if c["state"] == "failed"],
                "findings": bad["summary"]["finding_count"],
            },
        },
        "artifacts": {
            path.name: sha256_file(path)
            for path in sorted(DEMO.glob("*"))
            if path.is_file() and path.name != "timing.json"
        },
    }
    (DEMO / "timing.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(json.dumps({
        "stages": report["totals"]["stages"],
        "wall_seconds_total": report["totals"]["wall_seconds_total"],
        "extraction": report["extraction"],
        "reconciliation": report["reconciliation"],
    }, indent=2))
    if happy["overall_status"] != "passed" or bad["overall_status"] == "passed":
        print("unexpected demo outcome", file=sys.stderr)
        return 1
    return 0


SPECTRUM_FIELDS = ("invoice_number", "contract_number", "purchase_order_number",
                   "document_date", "total_amount")


def _absent_fields(proposals: dict) -> int:
    present = {p["field"] for p in proposals["proposals"]}
    return len([f for f in SPECTRUM_FIELDS if f not in present])


def _version() -> str:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import tensorbench
    return getattr(tensorbench, "__version__", "unknown")


def _pypdf_version() -> str:
    try:
        import pypdf
        return pypdf.__version__
    except Exception:  # pragma: no cover - pypdf is a hard dependency of the demo
        return "absent"


if __name__ == "__main__":
    os.chdir(ROOT)
    raise SystemExit(main())