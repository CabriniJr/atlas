"""Extração de blocos tradutíveis de uma página PDF (ADR-0030, estágio 1).

Usa ``page.get_text("dict")`` do PyMuPDF. Agrupa spans em blocos (unidades de
tradução). Marca ``skip=True`` para código (fonte monospace) e blocos sem letras.
"""

from __future__ import annotations

from dataclasses import dataclass, field

_FLAG_MONOSPACE = 8  # bit 3 do flags do fitz


@dataclass
class Span:
    text: str
    bbox: tuple[float, float, float, float]
    font: str
    size: float
    color: int
    flags: int


@dataclass
class BlocoTraducao:
    id: int
    pagina: int
    bbox: tuple[float, float, float, float]
    texto: str
    spans: list[Span] = field(default_factory=list)
    skip: bool = False


def _tem_letra(texto: str) -> bool:
    return any(c.isalpha() for c in texto)


def extrair_pagina(page, pagina: int) -> list[BlocoTraducao]:
    d = page.get_text("dict")
    blocos: list[BlocoTraducao] = []
    for bid, bloco in enumerate(d.get("blocks", [])):
        if "lines" not in bloco:  # bloco de imagem — ignora
            continue
        spans: list[Span] = []
        partes: list[str] = []
        mono = False
        for linha in bloco["lines"]:
            for s in linha.get("spans", []):
                spans.append(
                    Span(
                        text=s["text"],
                        bbox=tuple(s["bbox"]),
                        font=s.get("font", ""),
                        size=s.get("size", 0.0),
                        color=s.get("color", 0),
                        flags=s.get("flags", 0),
                    )
                )
                partes.append(s["text"])
                if s.get("flags", 0) & _FLAG_MONOSPACE:
                    mono = True
        if not spans:
            continue
        texto = " ".join(p.strip() for p in partes if p.strip())
        skip = mono or not _tem_letra(texto)
        blocos.append(
            BlocoTraducao(
                id=bid,
                pagina=pagina,
                bbox=tuple(bloco["bbox"]),
                texto=texto,
                spans=spans,
                skip=skip,
            )
        )
    return blocos
