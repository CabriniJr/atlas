"""Extração de blocos tradutíveis de uma página PDF (ADR-0030, estágio 1).

Usa ``page.get_text("dict")`` do PyMuPDF. Agrupa spans em blocos (unidades de
tradução). Marca ``skip=True`` para código (fonte monospace) e blocos sem letras.
"""

from __future__ import annotations

from dataclasses import dataclass, field

_FLAG_MONOSPACE = 8  # bit 3 do flags do fitz
_FLAG_ITALIC = 1 << 1
_FLAG_BOLD = 1 << 4


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


def _bold_span(s: Span) -> bool:
    return bool(s.flags & _FLAG_BOLD) or "bold" in s.font.lower() or "black" in s.font.lower()


def _italic_span(s: Span) -> bool:
    return bool(s.flags & _FLAG_ITALIC) or "italic" in s.font.lower() or "oblique" in s.font.lower()


def _marcar_enfase(spans: list[Span]) -> str:
    """Monta o texto do bloco marcando trechos que divergem do estilo dominante
    (negrito/itálico) com marcadores leves (``**b**``/``_i_``) — a tradução é
    instruída a preservá-los (ADR-0041); o render os converte em ``<b>``/``<i>``
    só no trecho, sem perder a ênfase de uma palavra isolada no meio do parágrafo.
    """
    partes_validas = [s for s in spans if s.text.strip()]
    if not partes_validas:
        return ""
    total = sum(max(1, len(s.text)) for s in partes_validas)
    peso_bold = sum(len(s.text) for s in partes_validas if _bold_span(s))
    peso_ital = sum(len(s.text) for s in partes_validas if _italic_span(s))
    dom_bold = peso_bold > total / 2
    dom_ital = peso_ital > total / 2
    saida: list[str] = []
    for s in partes_validas:
        texto = s.text.strip()
        if _bold_span(s) and not dom_bold:
            texto = f"**{texto}**"
        if _italic_span(s) and not dom_ital:
            texto = f"_{texto}_"
        saida.append(texto)
    return " ".join(saida)


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
                if s.get("flags", 0) & _FLAG_MONOSPACE:
                    mono = True
        if not spans:
            continue
        texto_plano = " ".join(s.text.strip() for s in spans if s.text.strip())
        skip = mono or not _tem_letra(texto_plano)
        texto = texto_plano if skip else _marcar_enfase(spans)
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
