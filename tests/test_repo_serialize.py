"""TDD — serialização incremental (ADR-0023 §3, E7-04): presets + extratores."""

from __future__ import annotations

import io
import zipfile

from atlas.rotinas.repo_sync import serialize

# ── presets ────────────────────────────────────────────────────────────────────


def test_should_serialize_presets():
    assert serialize.should_serialize("docs/x.md", "docs") is True
    assert serialize.should_serialize("src/a.py", "docs") is False
    assert serialize.should_serialize("src/a.py", "docs+code") is True
    assert serialize.should_serialize("manual.docx", "docs") is True
    assert serialize.should_serialize("img.png", "docs+code") is False
    assert serialize.should_serialize("x.bin", "off") is False


def test_should_serialize_glob_extra():
    assert serialize.should_serialize("data/x.bin", "off", ["*.bin"]) is True
    assert serialize.should_serialize("data/x.txt", "off", ["*.bin"]) is False


# ── extratores ─────────────────────────────────────────────────────────────────


def test_extrair_texto():
    assert "olá" in serialize.extrair("olá mundo".encode(), "nota.md")


def _docx(texto: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(
            "word/document.xml",
            '<?xml version="1.0"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f"<w:body><w:p><w:r><w:t>{texto}</w:t></w:r></w:p></w:body></w:document>",
        )
    return buf.getvalue()


def test_extrair_docx_stdlib():
    out = serialize.extrair(_docx("contrato importante"), "manual.docx")
    assert out is not None
    assert "contrato importante" in out


def _pptx(texto: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(
            "ppt/slides/slide1.xml",
            '<?xml version="1.0"?>'
            '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'
            ' xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
            f"<a:t>{texto}</a:t></p:sld>",
        )
    return buf.getvalue()


def test_extrair_pptx_stdlib():
    out = serialize.extrair(_pptx("slide um"), "deck.pptx")
    assert out is not None
    assert "slide um" in out


def test_extrair_pdf_invalido_degrada():
    # Sem pdftotext (ou PDF inválido) → None, sem levantar.
    assert serialize.extrair(b"isto nao e um pdf", "doc.pdf") is None


def test_extrair_office_corrompido_degrada():
    assert serialize.extrair(b"nao e um zip", "x.docx") is None
