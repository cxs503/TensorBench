"""Deterministic cross-document reconciliation for extracted business records.

The engine consumes normalized extraction output. OCR, legal interpretation,
fraud decisions and payment execution are explicitly outside this module.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from pathlib import Path
from typing import Any


class BusinessEvidenceError(ValueError):
    """Invalid normalized business-document bundle."""


def _decimal(value: Any) -> Decimal | None:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result.is_finite() else None


def _money(value: Decimal) -> str:
    try:
        return format(value.quantize(Decimal("0.01")), "f")
    except InvalidOperation:
        # Keep diagnostics available for unusually large values that exceed the
        # active Decimal context precision; validation itself still uses Decimal.
        return format(value, "f")


def _fingerprint(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def reconcile_bundle(bundle: Any, *, tolerance: str = "0.01") -> dict[str, Any]:
    """Reconcile a normalized bundle of contract, PO, delivery and invoice records."""
    if not isinstance(bundle, dict) or not isinstance(bundle.get("documents"), list):
        raise BusinessEvidenceError("bundle.documents must be an array")
    docs = bundle["documents"]
    if not docs:
        raise BusinessEvidenceError("bundle.documents must not be empty")
    tol = _decimal(tolerance)
    if tol is None or tol < 0:
        raise BusinessEvidenceError("tolerance must be a non-negative decimal amount")
    for index, doc in enumerate(docs):
        if not isinstance(doc, dict):
            raise BusinessEvidenceError(f"documents[{index}] must be an object")
        for key in ("doc_id", "document_type"):
            if not doc.get(key):
                raise BusinessEvidenceError(f"documents[{index}].{key} is required")
        if doc["document_type"] not in {"contract", "purchase_order", "delivery", "invoice", "payment"}:
            raise BusinessEvidenceError(f"unsupported document_type: {doc['document_type']}")

    by_id: dict[str, dict[str, Any]] = {}
    for doc in docs:
        if doc["doc_id"] in by_id:
            raise BusinessEvidenceError(f"duplicate doc_id: {doc['doc_id']}")
        by_id[doc["doc_id"]] = doc
    purchase_orders = {
        doc.get("po_number") or doc["doc_id"]: doc
        for doc in docs if doc["document_type"] == "purchase_order"
    }
    invoices = [doc for doc in docs if doc["document_type"] == "invoice"]
    deliveries = [doc for doc in docs if doc["document_type"] == "delivery"]

    evidence_refs: list[str] = []
    source_metadata_missing = []
    for doc in docs:
        source_ref = doc.get("source_ref")
        digest = str(doc.get("sha256") or "")
        if not source_ref or not re.fullmatch(r"[a-fA-F0-9]{64}", digest):
            source_metadata_missing.append(doc)
        ref = doc.get("evidence_ref") or (
            f"document:{doc['doc_id']}:sha256:{digest}" if digest else f"document:{doc['doc_id']}"
        )
        evidence_refs.append(ref)

    checks: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []

    def add(check_id: str, state: str, details: str, *, required: bool = True,
            severity: str = "medium", docs_involved: list[dict[str, Any]] | None = None) -> None:
        checks.append({
            "check_id": check_id,
            "version": "0.1.0",
            "method": "deterministic_rule",
            "state": state,
            "required": required,
            "details": details,
        })
        if state in {"failed", "inconclusive"}:
            involved = docs_involved or docs[:1]
            refs = [d.get("evidence_ref") or f"document:{d['doc_id']}" for d in involved]
            findings.append({
                "finding_id": f"{check_id}:{len(findings) + 1}",
                "check_id": check_id,
                "status": "confirmed" if state == "failed" else "inconclusive",
                "severity": severity if state == "failed" else "info",
                "summary": details,
                "rationale": details,
                "evidence_refs": refs,
                "review_state": "unreviewed",
                "limitations": ["Finding is a document discrepancy signal, not a fraud or legal conclusion."],
            })

    if source_metadata_missing:
        for doc in source_metadata_missing:
            add("source.provenance", "inconclusive",
                f"{doc['doc_id']} lacks a source_ref or valid SHA-256 content fingerprint.",
                docs_involved=[doc])
    else:
        add("source.provenance", "passed",
            "Every document has a source reference and a valid SHA-256 content fingerprint.")

    # 1. Document-level arithmetic.
    arithmetic_errors: list[tuple[dict[str, Any], str]] = []
    arithmetic_unresolved: list[tuple[dict[str, Any], str]] = []
    for doc in docs:
        lines = doc.get("line_items")
        if doc["document_type"] in {"purchase_order", "invoice"}:
            if lines is None or not lines:
                arithmetic_unresolved.append((doc, "line_items are missing or empty"))
            if _decimal(doc.get("total_amount")) is None:
                arithmetic_unresolved.append((doc, "total_amount is missing or not numeric"))
        # Delivery rows carry accepted quantities, not necessarily financial
        # unit prices/amounts. Arithmetic is applicable only to PO/invoice rows.
        if doc["document_type"] not in {"purchase_order", "invoice"} or lines is None:
            continue
        if not isinstance(lines, list):
            arithmetic_errors.append((doc, "line_items must be an array"))
            continue
        line_sum = Decimal("0")
        invalid = False
        for item in lines:
            if not isinstance(item, dict):
                invalid = True
                break
            qty = _decimal(item.get("quantity"))
            price = _decimal(item.get("unit_price"))
            amount = _decimal(item.get("amount"))
            if qty is None or price is None or amount is None:
                invalid = True
                break
            expected = qty * price
            if abs(expected - amount) > tol:
                arithmetic_errors.append((doc, f"line {item.get('sku', '<unknown>')}: quantity × unit_price "
                                                 f"({_money(expected)}) differs from amount ({_money(amount)})"))
            line_sum += amount
        total = _decimal(doc.get("total_amount"))
        if invalid:
            arithmetic_errors.append((doc, "one or more line items contain invalid numeric fields"))
        elif total is not None and abs(line_sum - total) > tol:
            arithmetic_errors.append((doc, f"line-item sum ({_money(line_sum)}) differs from document total "
                                             f"({_money(total)})"))
    for doc, message in arithmetic_errors:
        add("document.arithmetic", "failed", f"{doc['doc_id']}: {message}",
            severity="high", docs_involved=[doc])
    for doc, message in arithmetic_unresolved:
        add("document.arithmetic", "inconclusive", f"{doc['doc_id']}: {message}",
            docs_involved=[doc])
    if not arithmetic_errors and not arithmetic_unresolved:
        add("document.arithmetic", "passed", "All supplied line-item arithmetic and document totals reconcile.")

    # 2. Invoice identifiers and PO matching.
    invoice_numbers: dict[str, list[dict[str, Any]]] = {}
    for invoice in invoices:
        number = str(invoice.get("invoice_number") or "").strip()
        if number:
            invoice_numbers.setdefault(number, []).append(invoice)
    duplicate_invoices = [items for items in invoice_numbers.values() if len(items) > 1]
    for items in duplicate_invoices:
        add("invoice.duplicate_number", "failed",
            f"Invoice number {items[0].get('invoice_number')!r} appears in multiple documents.",
            severity="critical", docs_involved=items)
    if not duplicate_invoices:
        add("invoice.duplicate_number", "passed", "No duplicate invoice numbers found.")

    match_errors = []
    unresolved = []
    for invoice in invoices:
        po_ref = invoice.get("po_ref")
        if not po_ref:
            unresolved.append((invoice, "invoice has no po_ref; purchase-order matching cannot be performed"))
            continue
        po = purchase_orders.get(str(po_ref)) or by_id.get(str(po_ref))
        if po is None:
            unresolved.append((invoice, f"referenced purchase order {po_ref!r} is absent from this bundle"))
            continue
        fields = ("supplier_id", "buyer_id", "currency")
        missing_fields = [
            field for field in fields
            if not invoice.get(field) or not po.get(field)
        ]
        if missing_fields:
            unresolved.append((invoice, f"required comparison fields missing: {', '.join(missing_fields)}"))
            continue
        mismatches = [
            f"{field}: invoice={invoice.get(field)!r}, PO={po.get(field)!r}"
            for field in fields
            if invoice.get(field) != po.get(field)
        ]
        inv_total, po_total = _decimal(invoice.get("total_amount")), _decimal(po.get("total_amount"))
        if inv_total is None or po_total is None:
            unresolved.append((invoice, "invoice or PO total_amount is missing/non-numeric"))
            continue
        if abs(inv_total - po_total) > tol:
            mismatches.append(f"total_amount: invoice={_money(inv_total)}, PO={_money(po_total)}")
        if mismatches:
            match_errors.append((invoice, po, "; ".join(mismatches)))
    for invoice, po, message in match_errors:
        add("invoice.purchase_order_match", "failed",
            f"Invoice {invoice['doc_id']} does not match PO {po['doc_id']}: {message}",
            severity="high", docs_involved=[invoice, po])
    for invoice, message in unresolved:
        add("invoice.purchase_order_match", "inconclusive",
            f"Invoice {invoice['doc_id']}: {message}", docs_involved=[invoice])
    if not match_errors and not unresolved:
        add("invoice.purchase_order_match", "passed", "All invoice-to-PO references resolve and key fields reconcile.")

    # 3. Delivery quantity against invoice quantity.
    delivery_errors = []
    delivery_unresolved = []
    for invoice in invoices:
        delivery_ref = invoice.get("delivery_ref")
        if not delivery_ref:
            continue
        delivery = by_id.get(str(delivery_ref))
        if delivery is None or delivery["document_type"] != "delivery":
            delivery_unresolved.append((invoice, f"delivery reference {delivery_ref!r} cannot be resolved"))
            continue
        delivery_lines = delivery.get("line_items")
        invoice_lines = invoice.get("line_items")
        if not isinstance(delivery_lines, list) or not delivery_lines or not isinstance(invoice_lines, list) or not invoice_lines:
            delivery_unresolved.append((invoice, "linked invoice or delivery has missing/invalid line_items"))
            continue
        delivered: dict[str, Decimal] = {}
        duplicate_skus: set[str] = set()
        malformed_delivery = False
        for line in delivery_lines:
            if not isinstance(line, dict) or not line.get("sku"):
                malformed_delivery = True
                break
            sku = str(line["sku"])
            accepted_qty = _decimal(line.get("accepted_quantity", line.get("quantity")))
            if accepted_qty is None:
                malformed_delivery = True
                break
            if sku in delivered:
                duplicate_skus.add(sku)
            delivered[sku] = delivered.get(sku, Decimal("0")) + accepted_qty
        if malformed_delivery or duplicate_skus:
            delivery_unresolved.append((invoice,
                "linked delivery has malformed lines or duplicate SKU rows; normalize before comparison"))
            continue
        for item in invoice_lines:
            if not isinstance(item, dict) or not item.get("sku"):
                delivery_unresolved.append((invoice, "invoice contains a malformed line item without SKU"))
                continue
            sku = str(item["sku"])
            qty = _decimal(item.get("quantity"))
            accepted = delivered.get(sku)
            if qty is None:
                delivery_unresolved.append((invoice, f"invoice SKU {sku} has missing/non-numeric quantity"))
            elif accepted is None:
                delivery_unresolved.append((invoice, f"invoice SKU {sku} is absent from linked accepted delivery"))
            elif qty > accepted + tol:
                delivery_errors.append((invoice, delivery,
                    f"invoice SKU {sku} quantity {qty} exceeds accepted delivery quantity {accepted}"))
    for invoice, delivery, message in delivery_errors:
        add("invoice.delivery_quantity", "failed", message, severity="high",
            docs_involved=[invoice, delivery])
    for invoice, message in delivery_unresolved:
        add("invoice.delivery_quantity", "inconclusive", message,
            required=True, docs_involved=[invoice])
    if not delivery_errors and not delivery_unresolved:
        add("invoice.delivery_quantity", "passed",
            "No invoice quantity exceeds a linked accepted-delivery quantity.", required=False)

    # 4. Supplier bank-account changes are flagged for human verification only.
    master = bundle.get("vendor_master") or {}
    bank_warnings = []
    if isinstance(master, dict):
        expected_accounts = master.get("bank_accounts") or {}
        for doc in docs:
            supplier = str(doc.get("supplier_id") or "")
            account = doc.get("bank_account")
            expected = expected_accounts.get(supplier)
            if account and expected and account != expected:
                bank_warnings.append(doc)
                add("supplier.bank_account_change", "failed",
                    f"Bank account on {doc['doc_id']} differs from the supplied vendor master; "
                    "verify through an independent trusted channel.",
                    required=True, severity="high", docs_involved=[doc])
    if not bank_warnings:
        add("supplier.bank_account_change", "passed",
            "No bank-account difference found against the supplied vendor master.", required=False)

    required_failed = any(c["required"] and c["state"] == "failed" for c in checks)
    required_unresolved = any(c["required"] and c["state"] in {"inconclusive", "not_measured"} for c in checks)
    overall = "failed" if required_failed else "inconclusive" if required_unresolved else "passed"
    digest = _fingerprint(bundle)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return {
        "schema_version": "0.1.0",
        "product_id": "business-evidence-engine",
        "product_version": "0.1.0",
        "run_id": f"business-evidence-{digest[:16]}",
        "created_at": now,
        "input_refs": evidence_refs,
        "input_fingerprints": {"bundle_sha256": digest},
        "checks": checks,
        "findings": findings,
        "evidence_refs": sorted(set(evidence_refs)),
        "overall_status": overall,
        "summary": {
            "document_count": len(docs),
            "invoice_count": len(invoices),
            "purchase_order_count": len(purchase_orders),
            "finding_count": len(findings),
            "note": "Structured extraction input only; no OCR, legal verdict or fraud determination.",
        },
        "provenance": {"input_fingerprints": {"bundle_sha256": digest}},
    }


def reconcile_file(path: str | Path, *, tolerance: str = "0.01") -> dict[str, Any]:
    source = Path(path)
    try:
        bundle = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BusinessEvidenceError(f"cannot read bundle {source}: {exc}") from exc
    return reconcile_bundle(bundle, tolerance=tolerance)
