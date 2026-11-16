"""Field spectra and pilot-artifact invariants (business-plan PDF ingestion).

Two groups:

* unit tests for the declared field spectra (synthetic text only, no private data);
* artifact guards for the stage-3 pilot under ``docs/pilots/BP-...``: a self review may
  never be read as acceptance, published values stay desensitized, and every evidence
  digest in the bundle resolves to a file whose bytes hash to it.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from tensorbench.business_pdf_fields import (
    FIELD_SPECTRA,
    approved_pdf_fields_to_evidence_record,
    field_names,
    field_spectrum_names,
    propose_pdf_fields,
    review_pdf_field_proposals,
)
from tensorbench.contracts import validate_file

ROOT = Path(__file__).resolve().parents[1]
PILOT_DIR = ROOT / "docs" / "pilots" / "BP-20261115-tensorai-bp-field-extraction"

BP_TEXT = """Tensor 系列商业计划书 · 投资人沟通版  |  1
 TENSOR AI INFRASTRUCTURE
 Tensor 系列商业计划书
 投资人沟通版 | V1.0 | 2026年11月
=========page break=========
 建议资金使用结构
 方向
 建议比例
 研发与核心技术
40%
平台、Agent、专业计算和验证体系
 产品工程与商业化
25%
企业部署与交付
 运营及风险储备
10%
法务与管理
 商业计划讨论稿
 本版不虚构融资金额、估值、股权比例或收入预测。
 收入结构演进（战略假设）
 早期
30%
55%
15%
0%
 成长期
40%
35%
15%
10%
 基础设施成熟
0–12个月
Agent 身份与组织
 商业化与生态
12–24个月
企业部署和订阅体系
 McKinsey：Reimagining tech infrastructure for agentic AI（2026）—
 Gartner：AI Agent 治理与 Agent Sprawl（2026）—
 免责声明：本文件为商业计划讨论稿，不构成证券投资建议。
"""


def _extraction(text: str = BP_TEXT, *, source_sha: str = "b" * 64) -> dict:
    pages = text.split("=========page break=========")
    return {
        "source": {"source_ref": "pilot://synthetic-bp/v1", "sha256": source_sha},
        "pages": [{
            "page_number": index,
            "evidence_id": f"sha256:{source_sha}:page:{index}",
            "text": page,
            "locator": {"page_number": index,
                        "page_text_sha256": hashlib.sha256(page.encode()).hexdigest()},
        } for index, page in enumerate(pages, start=1)],
    }


def test_both_declared_spectra_are_named_and_stable() -> None:
    assert field_spectrum_names() == ("business_plan_v1", "trade_documents_v1")
    assert len(field_names("trade_documents_v1")) == 5
    assert field_names("business_plan_v1") == (
        "document_title", "document_version", "document_issue_date", "legal_disclaimer",
        "financing_stage", "funding_amount", "table_label_percent", "ratio_block",
        "roadmap_window", "market_reference",
    )


def test_default_spectrum_keeps_the_trade_document_behaviour() -> None:
    """A business plan through the default (trade) spectrum must yield nothing, not noise."""
    default = propose_pdf_fields(_extraction())
    trade = propose_pdf_fields(_extraction(), spectrum="trade_documents_v1")
    assert default["field_spectrum"] == "trade_documents_v1"
    assert default["proposal_count"] == 0 and default["status"] == "no_candidates"
    assert default["proposals"] == trade["proposals"]


def test_business_plan_spectrum_extracts_page_addressable_values() -> None:
    report = propose_pdf_fields(_extraction(), spectrum="business_plan_v1")
    assert report["field_spectrum"] == "business_plan_v1"
    by_field: dict[str, list[dict]] = {}
    for proposal in report["proposals"]:
        by_field.setdefault(proposal["field"], []).append(proposal)
    assert by_field["document_version"][0]["normalized_candidate"] == "V1.0"
    assert by_field["document_issue_date"][0]["normalized_candidate"] == "2026-11"
    assert by_field["document_title"][0]["locator"]["page_number"] == 1
    roadmap = {(p["subject"], p["normalized_candidate"]) for p in by_field["roadmap_window"]}
    assert roadmap == {("基础设施成熟", "0-12"), ("商业化与生态", "12-24")}
    revenue = {p["subject"]: p["normalized_candidate"] for p in by_field["ratio_block"]}
    assert revenue == {"早期": "30/55/15/0", "成长期": "40/35/15/10"}
    citations = {p["subject"] for p in by_field["market_reference"]}
    assert citations == {"McKinsey：Reimagining tech infrastructure for agentic AI（2026）",
                         "Gartner：AI Agent 治理与 Agent Sprawl（2026）"}


def test_funding_amount_is_never_inferred_from_prose() -> None:
    """The document says it does not disclose an amount; no proposal may appear."""
    report = propose_pdf_fields(_extraction(), spectrum="business_plan_v1")
    assert not [p for p in report["proposals"] if p["field"] == "funding_amount"]


@pytest.mark.parametrize("spectrum", sorted(FIELD_SPECTRA))
def test_every_locator_addresses_exactly_its_value(spectrum: str) -> None:
    """Offsets must address the stripped value, including multi-line table blocks."""
    extraction = _extraction()
    pages = {page["page_number"]: page["text"] for page in extraction["pages"]}
    for proposal in propose_pdf_fields(extraction, spectrum=spectrum)["proposals"]:
        locator = proposal["locator"]
        span = pages[locator["page_number"]][locator["start_offset"]:locator["end_offset"]]
        assert span == proposal["raw_value"]
        assert hashlib.sha256(span.encode()).hexdigest() == locator["value_sha256"]


def test_multi_row_table_field_is_grouped_by_subject_not_flagged_as_conflict() -> None:
    report = propose_pdf_fields(_extraction(), spectrum="business_plan_v1")
    decisions = [{"proposal_id": p["proposal_id"], "decision": "accept"} for p in report["proposals"]]
    reviewed = review_pdf_field_proposals(report, decisions, reviewer="unit-test")
    assert reviewed["status"] == "reviewed"
    assert reviewed["review"]["conflicting_fields"] == []
    assert reviewed["approved_fields"]["table_label_percent#研发与核心技术"]["value"] == "40"


def test_duplicate_row_key_with_two_values_is_withheld_as_conflict() -> None:
    """The same row label on two pages with different percentages must not be merged."""
    two_pages = _extraction(BP_TEXT.replace("=========page break=========",
                                            "\n 研发与核心技术\n41%\n"
                                            "=========page break========="))
    report = propose_pdf_fields(two_pages, spectrum="business_plan_v1")
    rows = [p for p in report["proposals"]
            if p["field"] == "table_label_percent" and p.get("subject") == "研发与核心技术"]
    assert {p["normalized_candidate"] for p in rows} == {"40", "41"}
    decisions = [{"proposal_id": p["proposal_id"], "decision": "accept"} for p in report["proposals"]]
    reviewed = review_pdf_field_proposals(report, decisions, reviewer="unit-test")
    assert reviewed["status"] == "conflicted"
    assert "table_label_percent#研发与核心技术" in reviewed["review"]["conflicting_fields"]
    assert "table_label_percent#研发与核心技术" not in reviewed["approved_fields"]
    with pytest.raises(Exception):
        approved_pdf_fields_to_evidence_record(reviewed, record_type="business_plan", record_id="x")


def test_unknown_spectrum_is_rejected() -> None:
    with pytest.raises(Exception):
        propose_pdf_fields(_extraction(), spectrum="no_such_spectrum")


# ----------------------------------------------------------------- pilot artifacts

requires_pilot = pytest.mark.skipif(not PILOT_DIR.exists(), reason="pilot artifacts not built")


def _load(name: str) -> dict:
    return json.loads((PILOT_DIR / name).read_text(encoding="utf-8"))


@requires_pilot
def test_pilot_report_validates_and_is_not_promoted_by_its_author() -> None:
    result = validate_file("report", PILOT_DIR / "validation_report.json")
    assert result["status"] == "valid", result["errors"]
    report = _load("validation_report.json")
    assert report["overall_status"] == "partial"
    receipt = report["review_receipt"]
    assert receipt["independence"] == "self_review"
    assert receipt["verdict"] != "pass"
    assert receipt["blocking_conditions"] and receipt["checks_not_run"]


@requires_pilot
def test_pilot_scenario_block_declares_consent_and_input_fingerprint() -> None:
    scenario = _load("validation_report.json")["scenario"]
    assert scenario["permission_basis"] == "internal_consent"
    digest = scenario["inputs"][0]["sha256"]
    assert re.fullmatch(r"[a-f0-9]{64}", digest)
    assert not Path(scenario["inputs"][0]["ref"]).is_absolute()


@requires_pilot
def test_pilot_criteria_were_frozen_before_the_run() -> None:
    report = _load("validation_report.json")
    assert report["criteria_freeze"]["frozen_at"] <= report["created_at"]
    assert report["criteria_freeze"]["amendments"] == []
    criteria = (PILOT_DIR / "criteria_v1.md").read_bytes()
    assert hashlib.sha256(criteria).hexdigest() == report["criteria_freeze"]["criteria_sha256"]


@requires_pilot
def test_evidence_bundle_digests_resolve_to_the_published_bytes() -> None:
    bundle = _load("evidence_bundle.json")
    assert bundle["artifacts"]
    for artifact in bundle["artifacts"]:
        path = ROOT / artifact["path"]
        assert path.is_file(), artifact["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"], artifact["path"]
        assert artifact["serves_checks"]


@requires_pilot
def test_private_source_is_never_in_the_repository() -> None:
    assert list(PILOT_DIR.rglob("*.pdf")) == []
    bundle = _load("evidence_bundle.json")
    assert bundle["source_input"]["committed"] is False
    pointer = _load("private_pointer.json")
    assert pointer["source_pdf"]["committed"] is False
    assert str(pointer["private_root"]).startswith("/"), "private bundle must live outside the worktree"
    assert not Path(pointer["private_root"]).is_relative_to(ROOT)


@requires_pilot
def test_published_values_are_masked_for_identity_fields() -> None:
    coverage = _load("field_coverage.json")
    assert coverage["redaction"]["verbatim_source_committed"] is False
    masked_fields = set(coverage["redaction"]["masked_fields"])
    record = _load("structured_record.redacted.json")
    for key, entry in record["fields"].items():
        if entry["field"] in masked_fields:
            assert "***" in entry["value"], key
            assert "***" in str(entry["subject"]) if entry["subject"] else True
        else:
            assert entry["value_sha256"] == hashlib.sha256(entry["value"].encode()).hexdigest()


@requires_pilot
def test_status_file_declares_business_evidence_state_consistently() -> None:
    status_text = (ROOT / "products" / "STATUS.json").read_text(encoding="utf-8")
    status = json.loads(status_text)
    products = {entry["id"]: entry for entry in status["products"]}
    # Mission m22925 published BE as scenario_validated=true; what must hold is that a validated
    # line carries a passing verdict and both evidence refs, never a bare boolean.
    be = products["BE"]
    if be["scenario_validated"]:
        assert be["acceptance_evidence"]["verdict"] == "pass"
        assert be["acceptance_evidence"]["validation_report_ref"]
        assert be["acceptance_evidence"]["review_receipt_ref"]
    else:
        assert be["acceptance_evidence"]["verdict"] in (None, "pass")
    for line in products.values():
        if line["scenario_validated"]:
            assert line["acceptance_evidence"]["verdict"] == "pass"