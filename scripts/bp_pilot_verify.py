#!/usr/bin/env python3
"""Independent second-path verification of one pilot extraction (criterion C7).

Deliberately shares no code with ``tensorbench.business_pdf_fields``: the PDF is
re-read here with ``pypdf`` directly, page text is re-hashed, and every accepted
value is re-derived by character-window scanning (find the label, look at the
characters just after it) instead of re-running the module's regular expressions.

Independence is mechanical only: the same agent authored the run, so the result
is a *self* check and can never be promoted to an independent-party review.

Exit code: 0 = every check agrees (and at least ``--min-checks`` were performed),
1 = disagreement or too few checks, 2 = cannot read its inputs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from io import BytesIO
from pathlib import Path

VERBATIM_FIELDS = {"document_version", "document_issue_date", "table_label_percent",
                   "ratio_block", "roadmap_window"}
METHOD = ("second code path: pypdf re-read + character-window scan around each label "
          "(no reuse of the module's regular expressions)")


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def display(field: str, value: str) -> str:
    if field in VERBATIM_FIELDS and not re.search(r"[\u4e00-\u9fff]{5,}", value):
        return value
    return f"{value[:2]}***(len={len(value)},sha256={sha256(value)[:12]})"


def read_pages(pdf_path: Path) -> tuple[str, list[str]]:
    from pypdf import PdfReader

    raw = pdf_path.read_bytes()
    reader = PdfReader(BytesIO(raw), strict=True)
    texts = []
    for page in reader.pages:
        texts.append(page.extract_text() or "")
    return hashlib.sha256(raw).hexdigest(), texts


def windows_after(text: str, label: str, width: int = 64) -> list[str]:
    """Characters just after every occurrence of ``label`` (prose may reuse a label)."""
    windows = []
    start = text.find(label)
    while start >= 0:
        begin = start + len(label)
        windows.append(text[begin:begin + width])
        start = text.find(label, start + 1)
    return windows


def unique_window(text: str, label: str) -> bool:
    return text.count(label) == 1


def first_percent(window: str) -> int | None:
    digits = ""
    for index, char in enumerate(window):
        if char.isdigit() and (index == 0 or not window[index - 1].isdigit()):
            digits = char
            for follow in window[index + 1:]:
                if follow.isdigit():
                    digits += follow
                elif follow in " \t\n%":
                    break
                else:
                    digits = ""
                    break
            if digits and "%" in window[index + len(digits):index + len(digits) + 4]:
                return int(digits)
    return None


def percent_lines(window: str) -> list[int]:
    values = []
    for line in window.split("\n"):
        stripped = line.strip()
        if stripped.endswith("%") and stripped[:-1].strip().isdigit():
            values.append(int(stripped[:-1].strip()))
        elif values:
            break
    return values


def month_span(window: str) -> str | None:
    match = re.search(r"(\d{1,2})\s*[–\-~—]\s*(\d{1,2})", window)
    if not match or "个月" not in window[match.end():match.end() + 8]:
        return None
    return f"{int(match.group(1))}-{int(match.group(2))}"


def _single(candidates: set, method: str) -> tuple[str | None, str]:
    """One distinct value across all occurrences; several distinct values is ambiguous."""
    if not candidates:
        return None, "no value token after any occurrence: " + method
    if len(candidates) == 1:
        return str(next(iter(candidates))), method
    return None, f"ambiguous: {len(candidates)} distinct values, " + method


def derive(field: str, subject: str | None, page_text: str) -> tuple[str | None, str]:
    """Re-derive one field value by scanning, without the module's rules."""
    if field == "document_title":
        for line in page_text.splitlines():
            stripped = line.strip()
            if stripped.endswith("商业计划书") and "|" not in stripped and "·" not in stripped:
                return stripped, "line ending in 商业计划书 without running header marks"
        return None, "no title line"
    if field == "document_version":
        token = ""
        for index, char in enumerate(page_text):
            if char in "Vv" and index + 1 < len(page_text) and page_text[index + 1].isdigit():
                probe = char
                for follow in page_text[index + 1:index + 9]:
                    if follow.isdigit() or follow == ".":
                        probe += follow
                    else:
                        break
                token = probe
                break
        return (token or None), "first V<digits[.digits]> token on the page"
    if field == "document_issue_date":
        index = page_text.find("年")
        if index < 4 or not page_text[index - 4:index].isdigit():
            return None, "no 年 after four digits"
        end = page_text.find("月", index)
        if end < 0:
            return None, "no 月 after 年"
        month = page_text[index + 1:end].strip()
        return (f"{page_text[index - 4:index]}-{int(month):02d}" if month.isdigit() else None,
                "four digits before 年 and digits before 月")
    if field == "legal_disclaimer":
        index = page_text.find("本文件为")
        if index < 0:
            return None, "no 本文件为"
        tail = page_text[index:]
        for stop in "，。；\n":
            cut = tail.find(stop)
            if cut > 0:
                tail = tail[:cut]
                break
        return tail, "sentence opening with 本文件为 up to the first clause break"
    if field == "financing_stage":
        index = page_text.find("建议以")
        if index < 0:
            return None, "no 建议以"
        tail = page_text[index + len("建议以"):]
        cut = tail.find("融资")
        if cut < 0:
            return None, "no 融资 after 建议以"
        stage = tail[:cut]
        if stage.endswith("战略"):
            stage = stage[:-2]
        return stage.strip(), "substring between 建议以 and the first 融资"
    if field == "table_label_percent" and subject:
        candidates = {first_percent(window) for window in windows_after(page_text, subject)} - {None}
        return _single(candidates, "first percentage token after the row label")
    if field == "ratio_block" and subject:
        candidates = {"/".join(str(v) for v in percent_lines(window)) or None
                      for window in windows_after(page_text, subject, width=120)} - {None}
        return _single(candidates, "consecutive percentage-only lines after the row label")
    if field == "roadmap_window" and subject:
        candidates = {month_span(window) for window in windows_after(page_text, subject)} - {None}
        return _single(candidates, "first month span after the phase label")
    if field == "market_reference" and subject:
        if not unique_window(page_text, subject):
            return None, "citation row (publisher + title) not uniquely present on the page"
        separator = "：" if "：" in subject else ":"
        if separator not in subject:
            return None, "citation row carries no publisher/title separator"
        publisher, _, title = subject.partition(separator)
        title_core = re.sub(r"[（(]\s*\d{4}\s*[）)]\s*$", "", title.strip()).strip()
        if publisher.strip() not in page_text or title_core not in page_text:
            return None, "publisher or title absent from the page"
        position = page_text.find(title_core) + len(title_core)
        tail = page_text[position:position + 16]
        if not any(marker in tail for marker in "（("):
            return None, "no year parenthesis right after the title"
        return title_core, "title between the publisher separator and the year parenthesis"
    return None, f"no independent rule for field {field!r}"


def verify(pdf_path: Path, private_record: Path) -> dict:
    bundle = json.loads(private_record.read_text(encoding="utf-8"))
    record = bundle["record"]
    review = bundle["reviewed"]
    # Locators address the *raw* span; the record stores the normalized value.
    raw_by_proposal = {p["proposal_id"]: p["raw_value"]
                       for p in (bundle.get("proposals") or review.get("proposals") or [])}
    file_sha, pages = read_pages(pdf_path)
    source_sha = record["source"]["sha256"]

    checks = []
    for key, entry in sorted(record["fields"].items()):
        for evidence in entry["evidence"]:
            locator = evidence["locator"]
            page_no = locator["page_number"]
            text = pages[page_no - 1] if 0 < page_no <= len(pages) else ""
            start, end = locator["start_offset"], locator["end_offset"]
            raw_value = raw_by_proposal.get(evidence["proposal_id"])
            slice_ok = (raw_value is not None and 0 <= start < end <= len(text)
                        and text[start:end] == raw_value)
            independent, method = derive(entry["field"], entry.get("subject"), text)
            check = {
                "field": entry["field"],
                "subject": display(entry["field"], entry["subject"]) if entry.get("subject") else None,
                "page_number": page_no,
                "start_offset": start,
                "end_offset": end,
                "raw_span_sha256": sha256(raw_value) if raw_value is not None else None,
                "declared_value": display(entry["field"], str(entry["value"])),
                "declared_value_sha256": sha256(str(entry["value"])),
                "independent_value": display(entry["field"], independent) if independent else None,
                "independent_value_sha256": sha256(independent) if independent else None,
                "independent_method": method,
                "page_text_sha256_recomputed": sha256(text),
                "page_text_sha256_declared": locator.get("page_text_sha256"),
                "page_anchor_ok": sha256(text) == locator.get("page_text_sha256"),
                "value_sha256_ok": raw_value is not None and sha256(raw_value) == locator.get("value_sha256"),
                "slice_matches_declared": slice_ok,
                "agrees": bool(slice_ok and independent is not None
                               and independent.strip() == str(entry["value"]).strip()
                               and sha256(raw_value) == locator.get("value_sha256")
                               and sha256(text) == locator.get("page_text_sha256")),
            }
            checks.append(check)

    # Absence must be re-confirmed, not assumed (criterion C5).
    absence = []
    for index, text in enumerate(pages, start=1):
        for needle in ("融资金额", "估值"):
            position = text.find(needle)
            if position >= 0:
                tail = text[position:position + 40]
                labeled = re.match(r"(融资金额|估值)\s*[:：]\s*\S", tail) is not None
                absence.append({"page_number": index, "needle": needle,
                                "followed_by_numeric_field": labeled,
                                "context_sha256": sha256(tail)})

    agreed = sum(1 for check in checks if check["agrees"])
    returned = {
        "method": METHOD,
        "independence": "self_check (same agent authored the run; not an independent party)",
        "pdf_sha256_recomputed": file_sha,
        "pdf_sha256_declared": source_sha,
        "pdf_sha256_matches": file_sha == source_sha,
        "pages_reread": len(pages),
        "proposal_bundle_sha256": review.get("proposal_bundle_sha256"),
        "fields_checked": sorted({check["field"] for check in checks}),
        "checks_total": len(checks),
        "checks_agreed": agreed,
        "funding_amount_absence": {
            "occurrences": absence,
            "numeric_disclosure_found": any(item["followed_by_numeric_field"] for item in absence),
        },
        "checks": checks,
    }
    return returned


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--private-record", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--out-private")
    parser.add_argument("--min-checks", type=int, default=5)
    args = parser.parse_args(argv)
    try:
        result = verify(Path(args.pdf), Path(args.private_record))
    except Exception as exc:  # noqa: BLE001 - a verifier that cannot read its inputs must say so
        print(f"verifier error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    state = "passed" if (result["checks_agreed"] == result["checks_total"]
                         and result["checks_total"] >= args.min_checks
                         and result["pdf_sha256_matches"]
                         and not result["funding_amount_absence"]["numeric_disclosure_found"]) else "failed"
    result["state"] = state
    result["min_checks"] = args.min_checks
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.out_private:
        Path(args.out_private).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                                          encoding="utf-8")
    print(f"{state}: {result['checks_agreed']}/{result['checks_total']} checks agree "
          f"over {len(result['fields_checked'])} fields")
    return 0 if state == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())