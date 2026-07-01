"""Remontagem: apaga o texto original e reinsere a tradução (ADR-0030, estágio 3).

Só o texto é tocado: ``add_redact_annot`` + ``apply_redactions`` removem os glyphs
originais; imagens e vetores permanecem. A tradução é reinserida no bbox do bloco
com auto-fit (encolhe a fonte até caber). Fonte builtin ``helv`` cobre acentos
latinos, evitando falta de glyphs em fontes embutidas subsetadas.
"""

from __future__ import annotations

import fitz

from atlas.traducao.extracao import BlocoTraducao

_FONTE_FALLBACK = "helv"  # Helvetica builtin — cobre latino/acentos
_MIN_FONTSIZE = 5.0


def _cor_rgb(color: int) -> tuple[float, float, float]:
    return ((color >> 16 & 255) / 255, (color >> 8 & 255) / 255, (color & 255) / 255)


def _com_folga(bbox: tuple[float, float, float, float]) -> fitz.Rect:
    x0, y0, x1, y1 = bbox
    # margem inferior extra p/ absorver PT mais longo sem estourar o bloco.
    return fitz.Rect(x0, y0, x1, y1 + (y1 - y0) * 0.6)


def remontar_pagina(page, blocos: list[BlocoTraducao], traducoes: dict[int, str]) -> None:
    # 1) Redaction dos spans dos blocos que serão traduzidos (skip fica intacto).
    for b in blocos:
        if b.skip or b.id not in traducoes:
            continue
        for s in b.spans:
            page.add_redact_annot(s.bbox)
    page.apply_redactions()

    # 2) Reinsere a tradução no bbox do bloco, com auto-fit.
    for b in blocos:
        if b.skip or b.id not in traducoes:
            continue
        texto = traducoes[b.id]
        base_size = b.spans[0].size if b.spans else 11.0
        color = _cor_rgb(b.spans[0].color if b.spans else 0)
        rect = _com_folga(b.bbox)
        size = base_size
        while size >= _MIN_FONTSIZE:
            sobra = page.insert_textbox(
                rect,
                texto,
                fontname=_FONTE_FALLBACK,
                fontsize=size,
                color=color,
                align=0,
            )
            if sobra >= 0:  # >= 0: coube
                break
            size -= 0.5  # não coube: encolhe e tenta de novo
