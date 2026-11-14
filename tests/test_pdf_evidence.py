from reportlab.pdfgen import canvas

from tensorbench.pdf_evidence import PdfEvidenceError, extract_pdf_evidence


def _make_pdf(path, lines):
    pdf = canvas.Canvas(str(path))
    for line in lines:
        pdf.drawString(72, 720, line)
        pdf.showPage()
    pdf.save()


def test_pdf_extraction_keeps_page_level_source_and_hashes(tmp_path):
    source = tmp_path / "contract.pdf"
    _make_pdf(source, ["Contract No. C-001", "Payment term: net 30"])
    report = extract_pdf_evidence(source, source_ref="contract://C-001/v1")

    assert report["status"] == "complete"
    assert report["source"]["page_count"] == 2
    assert len(report["source"]["sha256"]) == 64
    assert report["pages"][0]["locator"]["page_number"] == 1
    assert "C-001" in report["pages"][0]["text"]
    assert report["pages"][1]["source_ref"] == "contract://C-001/v1"
    assert report["pages"][0]["evidence_id"].endswith(":page:1")
    assert report["pages"][0]["locator"]["page_text_sha256"] != report["pages"][1]["locator"]["page_text_sha256"]


def test_pdf_extraction_rejects_empty_source_reference(tmp_path):
    source = tmp_path / "contract.pdf"
    _make_pdf(source, ["one page"])
    try:
        extract_pdf_evidence(source, source_ref=" ")
    except PdfEvidenceError as exc:
        assert "source_ref" in str(exc)
    else:
        raise AssertionError("empty source references must be rejected")


def test_pdf_extraction_enforces_size_limit(tmp_path):
    source = tmp_path / "contract.pdf"
    _make_pdf(source, ["one page"])
    try:
        extract_pdf_evidence(source, source_ref="contract://C-001", max_bytes=10)
    except PdfEvidenceError as exc:
        assert "max_bytes" in str(exc)
    else:
        raise AssertionError("oversized PDFs must be rejected")
