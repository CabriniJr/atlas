"""Motor puro de layout do render editorial (ADR-0033).

Usa o retorno de ``page.insert_textbox`` como oráculo de medição: PyMuPDF devolve
a **altura não usada** (``>= 0`` coube; ``< 0`` faltou espaço). Medimos numa página
temporária descartável, sem desenhar nada no documento real. Tudo aqui é função
pura de (geometria, fonte, texto) ⇒ determinístico e resumível (ADR-0031).

Quando o render usa uma fonte embutida (TTF), passamos ``fontfile`` para que a
medição use as **mesmas métricas** do desenho — senão o reflow erra a altura.
"""

from __future__ import annotations

import fitz


def _medir(page, rect, texto, fontsize, fontname, fontfile):
    tmp = fitz.open()
    tp = tmp.new_page(width=page.rect.width, height=page.rect.height)
    if fontfile:
        tp.insert_font(fontname=fontname, fontfile=fontfile)
    sobra = tp.insert_textbox(
        rect, texto, fontsize=fontsize, fontname=fontname, align=fitz.TEXT_ALIGN_LEFT
    )
    tmp.close()
    return sobra


def altura_livre(
    page, rect: fitz.Rect, texto: str, fontsize: float,
    fontname: str = "helv", fontfile: str | None = None,
) -> float:
    """Altura sobrando (``>=0``) ou faltando (``<0``) ao encaixar ``texto`` em ``rect``.

    Mede sem desenhar, numa página temporária de mesma geometria.
    """
    return _medir(page, rect, texto, fontsize, fontname, fontfile)


def cabe_no_bbox(
    page, rect: fitz.Rect, texto: str, fontsize: float,
    fontname: str = "helv", fontfile: str | None = None,
) -> bool:
    return altura_livre(page, rect, texto, fontsize, fontname, fontfile) >= 0


def altura_necessaria(
    page,
    largura: float,
    texto: str,
    fontsize: float,
    fontname: str = "helv",
    fontfile: str | None = None,
    teto: float = 100000.0,
) -> float:
    """Altura que ``texto`` ocupa numa coluna de ``largura`` na ``fontsize`` dada.

    Mede numa caixa muito alta e descobre quanto foi usado (``teto - sobra``). É a
    base do reflow: sabendo a altura de cada bloco, o motor empurra os seguintes
    para baixo em vez de sobrepô-los. Função pura de (largura, texto, fonte).
    """
    if not texto.strip():
        return 0.0
    rect = fitz.Rect(0, 0, largura, teto)
    sobra = altura_livre(page, rect, texto, fontsize, fontname, fontfile)
    if sobra < 0:  # nem no teto coube (texto gigante) — devolve o teto
        return teto
    return teto - sobra


def fontsize_que_cabe(
    page,
    rect: fitz.Rect,
    texto: str,
    fontsize_base: float,
    min_pct: int = 90,
    fontname: str = "helv",
    fontfile: str | None = None,
    passo: float = 0.5,
) -> float | None:
    """Maior fontsize em ``[min_pct% * base, base]`` que faz ``texto`` caber em ``rect``.

    Devolve ``None`` se nem no piso couber (o chamador reflui/pagina).
    """
    piso = fontsize_base * (min_pct / 100.0)
    fs = fontsize_base
    while fs >= piso:
        if cabe_no_bbox(page, rect, texto, fs, fontname, fontfile):
            return fs
        fs -= passo
    return None


def paginar_prosa(
    page, rect: fitz.Rect, texto: str, fontsize: float,
    fontname: str = "helv", fontfile: str | None = None,
) -> tuple[str, str]:
    """Divide ``texto`` em ``(cabe_em_rect, resto)`` por palavras, sem perder conteúdo.

    Busca binária no nº de palavras que ainda cabe em ``rect``. Garante progresso
    (consome ≥ 1 palavra) para nunca gerar página de continuação vazia.
    """
    palavras = texto.split()
    if not palavras:
        return "", ""
    if cabe_no_bbox(page, rect, texto, fontsize, fontname, fontfile):
        return texto, ""
    lo, hi, melhor = 0, len(palavras), 0
    while lo <= hi:
        mid = (lo + hi) // 2
        if mid > 0 and cabe_no_bbox(
            page, rect, " ".join(palavras[:mid]), fontsize, fontname, fontfile
        ):
            melhor, lo = mid, mid + 1
        else:
            hi = mid - 1
    melhor = max(melhor, 1)  # progresso garantido
    return " ".join(palavras[:melhor]), " ".join(palavras[melhor:])
