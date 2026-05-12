"""Tests for POST /api/scholar/ingest — file upload, text extraction, deadline detection."""
from __future__ import annotations

import pathlib
from unittest.mock import MagicMock

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from jarvis.contract import AgentResponse
from jarvis.apps.api.app import make_app

FIXTURES = pathlib.Path(__file__).parent / "fixtures"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_lens_response(markdown: str = "# Summary\n\nTest content summary.") -> AgentResponse:
    return AgentResponse(
        agent="lens",
        intent="deep_research",
        action="researched",
        result={"markdown": markdown},
        confidence=0.85,
    )


def _mock_scholar_add_response(title: str = "Test Assignment") -> AgentResponse:
    from jarvis.contract import Task

    t = Task(title=title, tags=["school", "course:?"])
    return AgentResponse(
        agent="scholar",
        intent="add_assignment",
        action="created",
        result={"assignment": t.model_dump()},
        confidence=1.0,
    )


def _make_client_with_mocks(
    lens_response: AgentResponse | None = None,
    scholar_response: AgentResponse | None = None,
) -> TestClient:
    """Build a TestClient whose registry has mocked lens + scholar instances."""
    from jarvis.agents.registry import AgentDescriptor, build_default_registry

    reg = build_default_registry()

    lens_resp = lens_response or _mock_lens_response()
    scholar_resp = scholar_response or _mock_scholar_add_response()

    mock_lens = MagicMock()
    mock_lens.deep_research.return_value = lens_resp

    mock_scholar = MagicMock()
    mock_scholar.add_assignment.return_value = scholar_resp

    reg["lens"] = AgentDescriptor(
        name="lens",
        instance=mock_lens,
        description="mock lens",
        mode="mock",
        actions={"deep_research": mock_lens.deep_research},
        default_for_text=lambda t: mock_lens.deep_research(t),
    )
    reg["scholar"] = AgentDescriptor(
        name="scholar",
        instance=mock_scholar,
        description="mock scholar",
        mode="mock",
        actions={"add_assignment": mock_scholar.add_assignment},
        default_for_text=lambda t: mock_scholar.add_assignment(title=t, course="?"),
    )

    return TestClient(make_app(registry=reg)), mock_lens, mock_scholar


# ---------------------------------------------------------------------------
# Basic upload — TXT
# ---------------------------------------------------------------------------


def test_ingest_txt_returns_200():
    client, _, _ = _make_client_with_mocks()
    txt = (FIXTURES / "sample.txt").read_bytes()
    r = client.post(
        "/api/scholar/ingest",
        files={"file": ("sample.txt", txt, "text/plain")},
    )
    assert r.status_code == 200


def test_ingest_txt_response_shape():
    client, _, _ = _make_client_with_mocks()
    txt = (FIXTURES / "sample.txt").read_bytes()
    r = client.post(
        "/api/scholar/ingest",
        files={"file": ("sample.txt", txt, "text/plain")},
    )
    body = r.json()
    assert "summary" in body
    assert "filename" in body
    assert body["filename"] == "sample.txt"


def test_ingest_txt_calls_lens_deep_research():
    client, mock_lens, _ = _make_client_with_mocks()
    txt = (FIXTURES / "sample.txt").read_bytes()
    client.post(
        "/api/scholar/ingest",
        files={"file": ("sample.txt", txt, "text/plain")},
    )
    mock_lens.deep_research.assert_called_once()
    call_args = mock_lens.deep_research.call_args
    # First positional arg should be the file content (string)
    content_arg = call_args[0][0] if call_args[0] else call_args[1].get("content", "")
    assert "CS501" in content_arg or "Gradient" in content_arg


def test_ingest_txt_summary_in_response():
    markdown = "# Summary\n\nGradient descent explained."
    client, _, _ = _make_client_with_mocks(lens_response=_mock_lens_response(markdown))
    txt = (FIXTURES / "sample.txt").read_bytes()
    r = client.post(
        "/api/scholar/ingest",
        files={"file": ("sample.txt", txt, "text/plain")},
    )
    assert r.json()["summary"] == markdown


# ---------------------------------------------------------------------------
# Deadline detection
# ---------------------------------------------------------------------------


def test_ingest_detects_deadline_and_creates_assignment():
    """sample.txt contains 'due on May 10, 2026' — assignment should be auto-created."""
    client, _, mock_scholar = _make_client_with_mocks()
    txt = (FIXTURES / "sample.txt").read_bytes()
    r = client.post(
        "/api/scholar/ingest",
        files={"file": ("sample.txt", txt, "text/plain")},
    )
    body = r.json()
    # Assignment should not be None when deadline found
    assert body["assignment"] is not None
    mock_scholar.add_assignment.assert_called_once()


def test_ingest_no_deadline_assignment_is_none():
    """Content with no deadline phrase → assignment key is None."""
    client, _, mock_scholar = _make_client_with_mocks()
    no_deadline_content = b"Introduction to algorithms. This is chapter 1 reading material."
    r = client.post(
        "/api/scholar/ingest",
        files={"file": ("notes.txt", no_deadline_content, "text/plain")},
    )
    body = r.json()
    assert body["assignment"] is None
    mock_scholar.add_assignment.assert_not_called()


def test_ingest_deadline_due_by_phrase():
    """'due by December 15' triggers assignment creation."""
    client, _, mock_scholar = _make_client_with_mocks()
    content = b"Project report due by December 15. Submit via portal."
    r = client.post(
        "/api/scholar/ingest",
        files={"file": ("report.txt", content, "text/plain")},
    )
    body = r.json()
    assert body["assignment"] is not None


# ---------------------------------------------------------------------------
# MD file type
# ---------------------------------------------------------------------------


def test_ingest_md_file():
    client, mock_lens, _ = _make_client_with_mocks()
    content = b"# Notes\n\nThis assignment is due on June 1.\n"
    r = client.post(
        "/api/scholar/ingest",
        files={"file": ("notes.md", content, "text/markdown")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["filename"] == "notes.md"
    mock_lens.deep_research.assert_called_once()


# ---------------------------------------------------------------------------
# PDF file type
# ---------------------------------------------------------------------------


def test_ingest_pdf_returns_200(tmp_path):
    """Uploading a minimal PDF returns 200 (content may be empty for blank page)."""
    try:
        from pypdf import PdfWriter

        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        pdf_path = tmp_path / "test.pdf"
        with pdf_path.open("wb") as f:
            writer.write(f)
        pdf_bytes = pdf_path.read_bytes()
    except Exception:
        pytest.skip("pypdf not available or PDF creation failed")

    client, _, _ = _make_client_with_mocks()
    r = client.post(
        "/api/scholar/ingest",
        files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
    )
    assert r.status_code == 200
    assert "summary" in r.json()


def test_ingest_pdf_with_text(tmp_path):
    """PDF with extractable text passes content to lens.deep_research."""
    try:
        from pypdf import PdfWriter
        from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

        writer = PdfWriter()
        page = writer.add_blank_page(width=612, height=792)

        content = b"BT /F1 12 Tf 100 700 Td (CS501 assignment due by May 15) Tj ET"
        stream = DecodedStreamObject()
        stream.set_data(content)
        page[NameObject("/Contents")] = writer._add_object(stream)

        font_dict = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        fonts = DictionaryObject({NameObject("/F1"): writer._add_object(font_dict)})
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): fonts})

        pdf_path = tmp_path / "withtext.pdf"
        with pdf_path.open("wb") as f:
            writer.write(f)
        pdf_bytes = pdf_path.read_bytes()
    except Exception:
        pytest.skip("pypdf not available or PDF creation failed")

    client, mock_lens, _ = _make_client_with_mocks()
    r = client.post(
        "/api/scholar/ingest",
        files={"file": ("withtext.pdf", pdf_bytes, "application/pdf")},
    )
    assert r.status_code == 200
    mock_lens.deep_research.assert_called_once()


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_ingest_no_file_returns_422():
    client, _, _ = _make_client_with_mocks()
    r = client.post("/api/scholar/ingest")
    assert r.status_code == 422


def test_ingest_unsupported_type_returns_400():
    client, _, _ = _make_client_with_mocks()
    r = client.post(
        "/api/scholar/ingest",
        files={"file": ("binary.exe", b"\x00\x01\x02", "application/octet-stream")},
    )
    assert r.status_code == 400
