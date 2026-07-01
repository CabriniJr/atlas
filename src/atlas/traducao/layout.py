"""Motor puro de layout do render editorial (ADR-0033).

Usa o retorno de ``page.insert_textbox`` como oráculo de medição: PyMuPDF devolve
a **altura não usada** (``>= 0`` coube; ``< 0`` faltou espaço). Medimos numa página
temporária descartável, sem desenhar nada no documento real. Tudo aqui é função
pura de (geometria, fonte, texto) ⇒ determinístico e resumível (ADR-0031).
"""

from __future__ import annotations

import fitz


def altura_livre(
    page, rect: fitz.Rect, texto: str, fontsize: float, fontname: str = "helv"
) -> float:
    """Altura sobrando (``>=0``) ou faltando (``<0``) ao encaixar ``texto`` em ``rect``.

    Mede sem desenhar, numa página temporária de mesma geometria.
    """
    tmp = fitz.open()
    tp = tmp.new_page(width=page.rect.width, height=page.rect.height)
    sobra = tp.insert_textbox(
        rect, texto, fontsize=fontsize, fontname=fontname, align=fitz.TEXT_ALIGN_LEFT
    )
    tmp.close()
    return sobra


def cabe_no_bbox(
    page, rect: fitz.Rect, texto: str, fontsize: float, fontname: str = "helv"
) -> bool:
    return altura_livre(page, rect, texto, fontsize, fontname) >= 0


def fontsize_que_cabe(
    page,
    rect: fitz.Rect,
    texto: str,
    fontsize_base: float,
    min_pct: int = 90,
    fontname: str = "helv",
    passo: float = 0.5,
) -> float | None:
    """Maior fontsize em ``[min_pct% * base, base]`` que faz ``texto`` caber em ``rect``.

    Devolve ``None`` se nem no piso couber (o chamador reflui/pagina).
    """
    piso = fontsize_base * (min_pct / 100.0)
    fs = fontsize_base
    while fs >= piso:
        if cabe_no_bbox(page, rect, texto, fs, fontname):
            return fs
        fs -= passo
    return None


def paginar_prosa(
    page, rect: fitz.Rect, texto: str, fontsize: float, fontname: str = "helv"
) -> tuple[str, str]:
    """Divide ``texto`` em ``(cabe_em_rect, resto)`` por palavras, sem perder conteúdo.

    Busca binária no nº de palavras que ainda cabe em ``rect``. Garante progresso
    (consome ≥ 1 palavra) para nunca gerar página de continuação vazia.
    """
    palavras = texto.split()
    if not palavras:
        return "", ""
    if cabe_no_bbox(page, rect, texto, fontsize, fontname):
        return texto, ""
    lo, hi, melhor = 0, len(palavras), 0
    while lo <= hi:
        mid = (lo + hi) // 2
        if mid > 0 and cabe_no_bbox(page, rect, " ".join(palavras[:mid]), fontsize, fontname):
            melhor, lo = mid, mid + 1
        else:
            hi = mid - 1
    melhor = max(melhor, 1)  # progresso garantido
    return " ".join(palavras[:melhor]), " ".join(palavras[melhor:])
