"""Exporta uma tradução para Markdown/EPUB (ADR-0032).

Todo o texto traduzido já está serializado no PDF de saída; aqui o
re-serializamos em Markdown (via PyMuPDF) e, para EPUB, delegamos ao
``pandoc`` — programa consagrado, em vez de reimplementar (P2/P5). Acoplado à
feature de tradução: a view do Kind ``Traducao`` oferece os botões de download.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import fitz

FORMATOS = ("md", "epub")


class PandocAusente(RuntimeError):
    """``pandoc`` não está no PATH — necessário só para EPUB."""


def pandoc_disponivel() -> bool:
    return shutil.which("pandoc") is not None


def serializar_markdown(pdf_path: str) -> str:
    """Extrai o texto do PDF traduzido, página a página, em Markdown simples.

    Separa páginas por ``---`` (regra horizontal). Mantém parágrafos; não tenta
    inferir níveis de título (o pandoc trata o resto na conversão).
    """
    doc = fitz.open(pdf_path)
    try:
        partes: list[str] = []
        for page in doc:
            txt = (page.get_text("text") or "").strip()
            if txt:
                partes.append(txt)
    finally:
        doc.close()
    return "\n\n---\n\n".join(partes) + "\n"


def exportar(pdf_path: str, fmt: str) -> str:
    """Gera o arquivo ``fmt`` ao lado do PDF e devolve o caminho.

    ``md`` não tem dependência externa; ``epub`` exige ``pandoc`` (levanta
    ``PandocAusente`` se ausente).
    """
    if fmt not in FORMATOS:
        raise ValueError(f"formato inválido: {fmt!r} (use {' ou '.join(FORMATOS)})")
    src = Path(pdf_path)
    if not src.is_file():
        raise FileNotFoundError(f"PDF de saída ausente: {pdf_path}")

    md_path = src.with_suffix(".md")
    md_path.write_text(serializar_markdown(pdf_path), encoding="utf-8")
    if fmt == "md":
        return str(md_path)

    if not pandoc_disponivel():
        raise PandocAusente("pandoc não está instalado (ex.: dnf install pandoc)")
    out = src.with_suffix(".epub")
    subprocess.run(
        ["pandoc", str(md_path), "-o", str(out), "--metadata", f"title={src.stem}"],
        check=True,
        capture_output=True,
    )
    return str(out)
