"""Remontagem: apaga o texto original e reinsere a tradução (ADR-0030, estágio 3).

Só o texto é tocado: ``add_redact_annot`` + ``apply_redactions`` removem os glyphs
originais; imagens e vetores permanecem. A tradução é reinserida no bbox do bloco
com auto-fit (encolhe a fonte até caber). Fonte builtin ``helv`` cobre acentos
latinos, evitando falta de glyphs em fontes embutidas subsetadas.
"""

from __future__ import annotations

import fitz

from atlas.traducao.extracao import BlocoTraducao
from atlas.traducao.layout import fontsize_que_cabe, paginar_prosa

_FONTE_FALLBACK = "helv"  # Helvetica builtin — cobre latino/acentos
_MIN_FONTSIZE = 5.0
_MARGEM = 72.0  # margem das páginas de continuação


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


def _maior_fonte_que_cabe(page, rect: fitz.Rect, texto: str, inicio: float) -> float:
    """Encolhe de ``inicio`` até ``_MIN_FONTSIZE`` para o texto caber em ``rect``.

    Fit-in-place para encaixados que não cabem nem no piso de legibilidade: melhor
    uma legenda menor no lugar certo do que truncada/repaginada (ADR-0033).
    """
    fs = inicio
    while fs > _MIN_FONTSIZE:
        tmp = fitz.open()
        tp = tmp.new_page(width=page.rect.width, height=page.rect.height)
        sobra = tp.insert_textbox(rect, texto, fontname=_FONTE_FALLBACK, fontsize=fs, align=0)
        tmp.close()
        if sobra >= 0:
            return fs
        fs -= 0.5
    return _MIN_FONTSIZE


def _traduzivel(b: BlocoTraducao, traducoes: dict[int, str]) -> bool:
    """Bloco que deve ser redigido/reescrito: tem tradução e não é imutável/skip."""
    return (not b.skip) and b.papel != "imutavel" and b.id in traducoes


def remontar_documento(
    doc,
    paginas: dict[int, tuple[list[BlocoTraducao], dict[int, str]]],
    min_fonte_pct: int = 90,
    notas: dict[int, list[dict]] | None = None,
) -> None:
    """Remonta o doc in-place em nível editorial (ADR-0033).

    ``paginas``: ``{indice_original: (blocos, traducoes)}``. Por papel de bloco:
    ``prosa`` reflui (o que não cabe vai para página de continuação inserida logo
    após a de origem, preservando a ordem); ``encaixado`` encaixa no bbox com piso
    de legibilidade; ``imutavel``/``skip`` ficam intactos (imagens/charts/código).
    Percorre em ordem decrescente de índice para os inserts não deslocarem as
    páginas ainda não processadas.
    """
    for idx in sorted(paginas, reverse=True):
        blocos, traducoes = paginas[idx]
        page = doc[idx]

        # 1) redação só dos spans tradutíveis (imagens/desenhos/imutáveis intactos).
        for b in blocos:
            if _traduzivel(b, traducoes):
                for s in b.spans:
                    page.add_redact_annot(s.bbox)
        page.apply_redactions()

        # 2) reinsere por papel; prosa que transborda vira overflow.
        overflow: list[str] = []
        glosas: list[dict] = []
        for b in blocos:
            if not _traduzivel(b, traducoes):
                continue
            if notas and b.id in notas:
                glosas.extend(notas[b.id])
            texto = traducoes[b.id]
            base = b.spans[0].size if b.spans else 11.0
            color = _cor_rgb(b.spans[0].color if b.spans else 0)
            rect = _com_folga(b.bbox)
            if b.papel == "prosa":
                cabe, resto = paginar_prosa(page, rect, texto, base, _FONTE_FALLBACK)
                page.insert_textbox(rect, cabe, fontname=_FONTE_FALLBACK, fontsize=base,
                                    color=color, align=0)
                if resto.strip():
                    overflow.append(resto)
            else:  # encaixado: fit-in-place — nunca transborda (legenda/label/célula)
                # Preferência: caber com fonte ≥ piso de legibilidade. Se não couber
                # nem no piso, encolhe até _MIN_FONTSIZE (fitting manda; não trunca).
                fs = fontsize_que_cabe(page, rect, texto, base, min_fonte_pct, _FONTE_FALLBACK)
                if fs is None:
                    fs = _maior_fonte_que_cabe(page, rect, texto, base * min_fonte_pct / 100.0)
                page.insert_textbox(rect, texto, fontname=_FONTE_FALLBACK, fontsize=fs,
                                    color=color, align=0)

        # 3) notas de rodapé (termos mantidos no idioma de origem) ao pé da página.
        _inserir_rodape(page, glosas)

        # 4) página(s) de continuação para o transbordo (preserva ordem de leitura).
        _inserir_continuacao(doc, idx, overflow)


def _inserir_rodape(page, glosas: list[dict]) -> None:
    """Escreve as glosas numeradas ao pé da página, em fonte pequena (ADR-0033)."""
    if not glosas:
        return
    largura, altura = page.rect.width, page.rect.height
    linhas = [
        f"{i}. {g.get('termo', '')} — {g.get('glosa', '')}".strip(" —")
        for i, g in enumerate(glosas, 1)
    ]
    corpo = "\n".join(linhas)
    # faixa ~ (n+1) linhas de 9pt acima da margem inferior; separador fino em cima.
    altura_faixa = 9 * (len(linhas) + 1)
    topo = altura - _MARGEM / 2 - altura_faixa
    page.draw_line((_MARGEM, topo - 2), (largura / 2, topo - 2), width=0.5)
    rect = fitz.Rect(_MARGEM, topo, largura - _MARGEM, altura - _MARGEM / 4)
    page.insert_textbox(rect, corpo, fontname=_FONTE_FALLBACK, fontsize=8, align=0)


def _inserir_continuacao(doc, idx: int, overflow: list[str]) -> None:
    if not overflow:
        return
    origem = doc[idx]
    largura, altura = origem.rect.width, origem.rect.height
    corpo = fitz.Rect(_MARGEM, _MARGEM, largura - _MARGEM, altura - _MARGEM)
    texto = "\n\n".join(overflow)
    pos = idx + 1
    while texto.strip():
        nova = doc.new_page(pno=pos, width=largura, height=altura)
        cabe, texto = paginar_prosa(nova, corpo, texto, 11.0, _FONTE_FALLBACK)
        nova.insert_textbox(corpo, cabe, fontname=_FONTE_FALLBACK, fontsize=11.0, align=0)
        nova.insert_text((_MARGEM, altura - _MARGEM / 2), "(cont.)", fontsize=8)
        pos += 1
