#!/usr/bin/env python3
"""Generate the synthetic demo invoice PDF used by ``docs/m22925/run_demo.py``.

The file is written with the raw PDF object syntax (no third-party writer), so the demo
depends only on ``pypdf`` for reading — the same dependency the product adapter declares.
The document is **synthetic**: three labels and a total, invented for the demo, carrying no
customer data. It is not evidence for the pilot; it exists so the product chain can be
walked end-to-end by a newcomer without access to a private document.

    python3 docs/m22925/make_demo_pdf.py [out.pdf]
"""
from __future__ import annotations

import sys
from pathlib import Path

DEFAULT_OUT = Path(__file__).resolve().parent / "demo" / "demo_invoice.pdf"

LINES = [
    "ACME Trading Co., Ltd. (synthetic demo document)",
    "Invoice No: INV-2026-001",
    "Purchase Order No: PO-2026-077",
    "Invoice Date: 2026-11-16",
    "Total Amount: 1,234.50 CNY",
    "This document is generated for the TensorBench BE onboarding demo.",
]


def _escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def build_pdf(lines: list[str]) -> bytes:
    content_lines = ["BT", "/F1 11 Tf", "50 760 Td", "16 TL"]
    for line in lines:
        content_lines.append(f"({_escape(line)}) Tj")
        content_lines.append("T*")
    content_lines.append("ET")
    stream = "\n".join(content_lines).encode("latin-1")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        b"trailer\n<< /Size " + str(len(objects) + 1).encode() + b" /Root 1 0 R >>\n"
        b"startxref\n" + str(xref_at).encode() + b"\n%%EOF\n"
    )
    return bytes(out)


def main(argv: list[str]) -> int:
    out = Path(argv[1]) if len(argv) > 1 else DEFAULT_OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(build_pdf(LINES))
    print(f"wrote {out} ({out.stat().st_size} bytes, {len(LINES)} text lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))