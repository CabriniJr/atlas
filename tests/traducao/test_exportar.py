"""Export de tradução para Markdown/EPUB (ADR-0032)."""

from __future__ import annotations

import fitz
import pytest

from atlas.traducao.exportar import (
    PandocAusente,
    exportar,
    pandoc_disponivel,
    serializar_markdown,
)


def _pdf_com_texto(path, paginas):
    doc = fitz.open()
    for txt in paginas:
        page = doc.new_page()
        page.insert_text((72, 72), txt)
    doc.save(str(path))
    doc.close()


def test_serializar_markdown_junta_paginas(tmp_path):
    pdf = tmp_path / "t.pdf"
    _pdf_com_texto(pdf, ["Primeira pagina", "Segunda pagina"])
    md = serializar_markdown(str(pdf))
    assert "Primeira pagina" in md
    assert "Segunda pagina" in md
    assert "---" in md  # separador de páginas


def test_exportar_md_escreve_arquivo(tmp_path):
    pdf = tmp_path / "livro.pdf"
    _pdf_com_texto(pdf, ["Conteudo traduzido"])
    out = exportar(str(pdf), "md")
    assert out.endswith(".md")
    assert "Conteudo traduzido" in (tmp_path / "livro.md").read_text(encoding="utf-8")


def test_exportar_formato_invalido(tmp_path):
    pdf = tmp_path / "x.pdf"
    _pdf_com_texto(pdf, ["a"])
    with pytest.raises(ValueError):
        exportar(str(pdf), "docx")


def test_exportar_epub(tmp_path):
    pdf = tmp_path / "obra.pdf"
    _pdf_com_texto(pdf, ["Capitulo um", "Capitulo dois"])
    if not pandoc_disponivel():
        with pytest.raises(PandocAusente):
            exportar(str(pdf), "epub")
        pytest.skip("pandoc ausente — só valida o erro gracioso")
    out = exportar(str(pdf), "epub")
    assert out.endswith(".epub")
    assert (tmp_path / "obra.epub").stat().st_size > 0
