"""One-shot script to create test fixtures.  Run once: python tests/fixtures/create_fixtures.py"""
from __future__ import annotations

import pathlib

HERE = pathlib.Path(__file__).parent


def _make_pdf() -> None:
    """Write a tiny but valid PDF containing readable text."""
    try:
        from pypdf import PdfWriter
        from pypdf.generic import DecodedStreamObject, NameObject

        writer = PdfWriter()
        page = writer.add_blank_page(width=612, height=792)

        # Build a minimal content stream with BT/ET text operators
        content = b"BT /F1 12 Tf 100 700 Td (CS501 Assignment due by May 10 2026) Tj ET"
        stream = DecodedStreamObject()
        stream.set_data(content)
        page[NameObject("/Contents")] = writer._add_object(stream)

        # Add a minimal font resource so the PDF is well-formed
        font = {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
        from pypdf.generic import DictionaryObject
        font_dict = DictionaryObject(font)
        fonts_dict = DictionaryObject({NameObject("/F1"): writer._add_object(font_dict)})
        resources = DictionaryObject({NameObject("/Font"): fonts_dict})
        page[NameObject("/Resources")] = resources

        dest = HERE / "sample.pdf"
        with dest.open("wb") as f:
            writer.write(f)
        print(f"Written: {dest}")
    except Exception as exc:
        print(f"ERROR: {exc}")
        raise


if __name__ == "__main__":
    _make_pdf()
