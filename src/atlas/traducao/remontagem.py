"""Remontagem: apaga o texto original e reinsere a tradução (ADR-0030/0033, estágio 3).

Só o texto é tocado: ``add_redact_annot`` + ``apply_redactions`` removem os glyphs
originais; imagens e vetores permanecem. Render **editorial** (ADR-0033): a prosa
**reflui** empurrando os blocos seguintes para baixo (o que transborda vira página
de continuação); ``encaixado``/``imutavel`` ficam fixos no lugar. A fonte é uma TTF
Unicode **embutida** (bullets •, aspas curvas, travessões) — a Helvetica builtin não
tinha esses glyphs e virava ``?``.
"""

from __future__ import annotations

from pathlib import Path

import fitz

from atlas.traducao.extracao import BlocoTraducao
from atlas.traducao.layout import (
    altura_necessaria,
    fontsize_que_cabe,
    paginar_prosa,
)

_FONTE_FALLBACK = "helv"  # legado (remontar_pagina)
_FONTE_PATH = str(Path(__file__).resolve().parent / "fonts" / "LiberationSans-Regular.ttf")
_FONTE_NOME = "atlas"  # alias da TTF embutida no documento
_MIN_FONTSIZE = 5.0
_MARGEM = 72.0  # margem das páginas de continuação
_MARGEM_INF = 54.0  # piso do corpo na página (0.75") p/ não pisar no rodapé
_GAP = 2.0  # respiro vertical entre blocos refluídos


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
        tp.insert_font(fontname=_FONTE_NOME, fontfile=_FONTE_PATH)
        sobra = tp.insert_textbox(rect, texto, fontname=_FONTE_NOME, fontsize=fs, align=0)
        tmp.close()
        if sobra >= 0:
            return fs
        fs -= 0.5
    return _MIN_FONTSIZE


def _traduzivel(b: BlocoTraducao, traducoes: dict[int, str]) -> bool:
    """Bloco que deve ser redigido/reescrito: tem tradução e não é imutável/skip."""
    return (not b.skip) and b.papel != "imutavel" and b.id in traducoes


def _flui(b: BlocoTraducao, traducoes: dict[int, str]) -> bool:
    """Bloco de prosa que reflui (empurra os seguintes). O resto fica fixo."""
    return _traduzivel(b, traducoes) and b.papel == "prosa"


def _obstaculos(page, blocos, traducoes) -> list[tuple[float, float]]:
    """Faixas verticais fixas que a prosa não pode invadir: imagens + blocos não-fluídos.

    Imagens (blocos sem ``lines``) e blocos ``encaixado``/``imutavel``/skip mantêm a
    posição original; a prosa reflui **em volta** deles (preserva figuras e legendas).
    """
    obst: list[tuple[float, float]] = []
    d = page.get_text("dict")
    for bl in d.get("blocks", []):
        if "lines" not in bl:  # bloco de imagem
            _, y0, _, y1 = bl["bbox"]
            obst.append((y0, y1))
    for b in blocos:
        if not _flui(b, traducoes):  # encaixado/imutavel/skip = fixo
            obst.append((b.bbox[1], b.bbox[3]))
    return obst


def remontar_documento(
    doc,
    paginas: dict[int, tuple[list[BlocoTraducao], dict[int, str]]],
    min_fonte_pct: int = 90,
    notas: dict[int, list[dict]] | None = None,
) -> None:
    """Remonta o doc in-place em nível editorial (ADR-0033).

    ``paginas``: ``{indice_original: (blocos, traducoes)}``. Por papel de bloco:
    ``prosa`` reflui top-to-bottom **empurrando os blocos seguintes** (o que passar do
    fundo da página vai para uma página de continuação inserida logo após); ``encaixado``
    encaixa no bbox com piso de legibilidade; ``imutavel``/skip/imagens ficam intactos.
    Percorre em ordem decrescente de índice para os inserts não deslocarem as páginas
    ainda não processadas.
    """
    for idx in sorted(paginas, reverse=True):
        blocos, traducoes = paginas[idx]
        page = doc[idx]

        # obstáculos são as posições ORIGINAIS (antes de redigir/refluir).
        obst = _obstaculos(page, blocos, traducoes)

        # 1) redação só dos spans tradutíveis (imagens/desenhos/imutáveis intactos).
        for b in blocos:
            if _traduzivel(b, traducoes):
                for s in b.spans:
                    page.add_redact_annot(s.bbox)
        page.apply_redactions()
        page.insert_font(fontname=_FONTE_NOME, fontfile=_FONTE_PATH)

        glosas: list[dict] = []
        for b in blocos:
            if _traduzivel(b, traducoes) and notas and b.id in notas:
                glosas.extend(notas[b.id])

        # 2a) encaixados: fit-in-place na posição original (fixos).
        for b in blocos:
            if not _traduzivel(b, traducoes) or b.papel == "prosa":
                continue
            texto = traducoes[b.id]
            base = b.spans[0].size if b.spans else 11.0
            color = _cor_rgb(b.spans[0].color if b.spans else 0)
            rect = _com_folga(b.bbox)
            fs = fontsize_que_cabe(page, rect, texto, base, min_fonte_pct, _FONTE_NOME, _FONTE_PATH)
            if fs is None:
                fs = _maior_fonte_que_cabe(page, rect, texto, base * min_fonte_pct / 100.0)
            page.insert_textbox(rect, texto, fontname=_FONTE_NOME, fontsize=fs,
                                color=color, align=0)

        # 2b) prosa: reflui top-to-bottom empurrando; transbordo → continuação.
        overflow = _refluir_prosa(page, blocos, traducoes, obst)

        # 3) notas de rodapé (termos mantidos no idioma de origem) ao pé da página.
        _inserir_rodape(page, glosas)

        # 4) página(s) de continuação para o transbordo (preserva ordem de leitura).
        _inserir_continuacao(doc, idx, overflow)


def _refluir_prosa(page, blocos, traducoes, obst) -> list[str]:
    """Posiciona os blocos de prosa em fluxo vertical, empurrando os seguintes.

    Cada bloco começa em ``max(topo_original, fim_do_anterior)`` e é limitado pelo
    próximo obstáculo abaixo (imagem/legenda) ou pelo fundo do corpo. O que não couber
    vira ``overflow`` (página de continuação). Assim os blocos nunca se sobrepõem.
    """
    prosa = sorted(
        (b for b in blocos if _flui(b, traducoes)),
        key=lambda b: (round(b.bbox[1], 1), b.bbox[0]),
    )
    fundo = page.rect.height - _MARGEM_INF
    cursor: float | None = None
    overflow: list[str] = []
    for b in prosa:
        texto = traducoes[b.id]
        x0, y0, x1, _ = b.bbox
        largura = x1 - x0
        base = b.spans[0].size if b.spans else 11.0
        color = _cor_rgb(b.spans[0].color if b.spans else 0)

        topo = y0 if cursor is None else max(y0, cursor)
        # empurra para baixo se o topo cair dentro de um obstáculo (imagem/legenda).
        for oy0, oy1 in obst:
            if oy0 - 0.5 <= topo < oy1:
                topo = oy1 + _GAP
        # limite inferior: próximo obstáculo abaixo do topo, ou fundo do corpo.
        abaixo = [oy0 for oy0, oy1 in obst if oy0 >= topo - 0.5]
        limite = min([fundo, *abaixo])
        if limite - topo < base:  # sem espaço útil aqui: joga tudo pra continuação.
            overflow.append(texto)
            continue

        alt = altura_necessaria(page, largura, texto, base, _FONTE_NOME, _FONTE_PATH)
        if topo + alt <= limite:
            rect = fitz.Rect(x0, topo, x1, topo + alt + 1)
            page.insert_textbox(rect, texto, fontname=_FONTE_NOME, fontsize=base,
                                color=color, align=0)
            cursor = topo + alt + _GAP
        else:
            rect = fitz.Rect(x0, topo, x1, limite)
            cabe, resto = paginar_prosa(page, rect, texto, base, _FONTE_NOME, _FONTE_PATH)
            page.insert_textbox(rect, cabe, fontname=_FONTE_NOME, fontsize=base,
                                color=color, align=0)
            if resto.strip():
                overflow.append(resto)
            cursor = limite + _GAP
    return overflow


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
    page.insert_textbox(rect, corpo, fontname=_FONTE_NOME, fontsize=8, align=0)


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
        nova.insert_font(fontname=_FONTE_NOME, fontfile=_FONTE_PATH)
        cabe, texto = paginar_prosa(nova, corpo, texto, 11.0, _FONTE_NOME, _FONTE_PATH)
        nova.insert_textbox(corpo, cabe, fontname=_FONTE_NOME, fontsize=11.0, align=0)
        nova.insert_text((_MARGEM, altura - _MARGEM / 2), "(cont.)",
                         fontname=_FONTE_NOME, fontsize=8)
        pos += 1
