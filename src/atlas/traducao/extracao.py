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
    papel: str = "encaixado"  # ADR-0033: prosa | encaixado | imutavel


def _tem_letra(texto: str) -> bool:
    return any(c.isalpha() for c in texto)


def classificar_papel(bloco: dict, largura_pagina: float) -> str:
    """Classifica o papel do bloco para o render editorial (ADR-0033).

    - ``imutavel``: sem texto tradutível OU código monoespaçado (nunca reflui).
    - ``prosa``: parágrafo largo (≥ metade da página) e multi-linha (≥ 2 linhas) —
      reflui e empurra os blocos seguintes; gera página de continuação quando cresce.
    - ``encaixado`` (default seguro): legenda/label/título de 1 linha — fit-in-place.
    """
    texto = (bloco.get("texto") or "").strip()
    if not texto or bloco.get("mono"):
        return "imutavel"
    x0, _, x1, _ = bloco["bbox"]
    largo = (x1 - x0) >= 0.5 * largura_pagina
    multilinha = bloco.get("n_linhas", 1) >= 2
    if largo and multilinha:
        return "prosa"
    return "encaixado"


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
        papel = classificar_papel(
            {"texto": texto, "bbox": tuple(bloco["bbox"]),
             "n_linhas": len(bloco["lines"]), "mono": mono},
            page.rect.width,
        )
        blocos.append(
            BlocoTraducao(
                id=bid,
                pagina=pagina,
                bbox=tuple(bloco["bbox"]),
                texto=texto,
                spans=spans,
                skip=skip,
                papel=papel,
            )
        )
    return blocos
