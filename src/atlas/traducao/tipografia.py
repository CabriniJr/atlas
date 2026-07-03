"""Motor puro de tipografia do render editorial (ADR-0041): conversão de marcador
de ênfase inline, clustering de nível de heading e taxa de abertura de página —
sem WeasyPrint/IO pesado (mesmo padrão de ``layout.py``). ``extrair_fontes`` é a
única função que precisa do documento aberto (fitz).
"""

from __future__ import annotations

import base64
import re
from collections.abc import Callable

_RE_ENFASE = re.compile(r"\*\*(.+?)\*\*|_(.+?)_", re.DOTALL)


def converter_enfase(texto: str, escapar: Callable[[str], str]) -> str:
    """Converte marcador ``**negrito**``/``_itálico_`` em ``<b>``/``<i>``, escapando
    o restante do texto com ``escapar`` (ex.: ``html.escape``). Marcador que não
    fecha (desbalanceado) fica literal — nunca quebra o parse (ADR-0041)."""
    partes: list[str] = []
    pos = 0
    for m in _RE_ENFASE.finditer(texto):
        if m.start() > pos:
            partes.append(escapar(texto[pos : m.start()]))
        if m.group(1) is not None:
            partes.append(f"<b>{escapar(m.group(1))}</b>")
        else:
            partes.append(f"<i>{escapar(m.group(2))}</i>")
        pos = m.end()
    partes.append(escapar(texto[pos:]))
    return "".join(partes)


def clusters_titulo(tamanhos: list[float], corpo_sz: float) -> list[float]:
    """Até 3 tamanhos-âncora (h1 > h2 > h3), do maior pro menor, agrupando os
    tamanhos de fonte "grandes" do documento (>= 1.15x o corpo) por proximidade
    (gap <= 0.75pt cai no mesmo cluster). Documento sem heading grande ⇒ ``[]``
    (nenhum nível é tratado como título)."""
    grandes = sorted({round(s, 1) for s in tamanhos if s >= corpo_sz * 1.15}, reverse=True)
    if not grandes:
        return []
    clusters: list[list[float]] = [[grandes[0]]]
    for s in grandes[1:]:
        if clusters[-1][-1] - s <= 0.75:
            clusters[-1].append(s)
        else:
            clusters.append([s])
    return [c[0] for c in clusters[:3]]


def nivel_titulo(sz: float, clusters: list[float], tol: float = 0.5) -> str | None:
    """``"h1"``/``"h2"``/``"h3"`` conforme o cluster mais próximo (dentro de
    ``tol``); ``None`` se não bater com nenhum (texto de corpo comum)."""
    for nivel, ref in zip(("h1", "h2", "h3"), clusters, strict=False):
        if abs(sz - ref) <= tol:
            return nivel
    return None


def taxa_abre_pagina(
    ocorrencias: dict[str, list[bool]], min_amostra: int = 3, limiar: float = 0.6
) -> dict[str, bool]:
    """Por nível de heading, decide se ele deve forçar quebra de página: taxa de
    ocorrências que abriram a página original >= ``limiar``, com amostra mínima
    ``min_amostra`` (evita decidir por 1-2 casos isolados — ADR-0041)."""
    out: dict[str, bool] = {}
    for nivel, flags in ocorrencias.items():
        if len(flags) < min_amostra:
            out[nivel] = False
            continue
        taxa = sum(1 for f in flags if f) / len(flags)
        out[nivel] = taxa >= limiar
    return out


_MIME_FONTE = {"ttf": "font/ttf", "otf": "font/otf", "woff": "font/woff", "woff2": "font/woff2"}


def extrair_fontes(doc) -> dict[str, str]:
    """``Span.font`` (basefont) → data URI da fonte real embutida no PDF
    (ADR-0041). Fonte não extraível (Type3, CFF cru, subset corrompido) fica de
    fora do mapa — o chamador cai no fallback genérico do CSS, nunca quebra."""
    vistos: dict[str, str] = {}
    for page in doc:
        for entry in page.get_fonts(full=True):
            xref, ext, _ftype, basefont = entry[0], entry[1], entry[2], entry[3]
            if not basefont or basefont in vistos:
                continue
            if (ext or "").lower() not in _MIME_FONTE:
                continue
            try:
                _nome, ext_real, _tipo, buf = doc.extract_font(xref)
            except Exception:  # noqa: BLE001 — extração é best-effort (ADR-0006)
                continue
            if not buf:
                continue
            mime = _MIME_FONTE.get((ext_real or ext).lower(), "font/ttf")
            vistos[basefont] = f"data:{mime};base64," + base64.b64encode(buf).decode()
    return vistos


def gerar_font_faces(fontes: dict[str, str]) -> str:
    """``@font-face`` p/ cada fonte real extraída — pronto p/ embutir no
    ``<style>`` do render editorial (ADR-0041)."""
    return "\n".join(
        f'@font-face {{ font-family: "{nome}"; src: url({uri}); }}'
        for nome, uri in fontes.items()
    )
