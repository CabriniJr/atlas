"""Motor puro de layout do render editorial (ADR-0033)."""

from __future__ import annotations

import fitz

from atlas.traducao.layout import (
    cabe_no_bbox,
    fontsize_que_cabe,
    paginar_prosa,
)


def _page():
    doc = fitz.open()
    return doc, doc.new_page()


# --- Task 2: medição ---------------------------------------------------------

def test_texto_curto_cabe():
    doc, page = _page()
    assert cabe_no_bbox(page, fitz.Rect(72, 72, 520, 200), "Uma linha curta.", 11) is True
    doc.close()


def test_texto_longo_nao_cabe_em_caixa_pequena():
    doc, page = _page()
    assert cabe_no_bbox(page, fitz.Rect(72, 72, 200, 90), "palavra " * 200, 11) is False
    doc.close()


# --- Task 3: fit com piso ----------------------------------------------------

def test_fontsize_reduz_ate_caber():
    doc, page = _page()
    fs = fontsize_que_cabe(page, fitz.Rect(72, 72, 260, 120),
                           "Legenda um pouco maior que o normal aqui.",
                           fontsize_base=12, min_pct=90)
    assert fs is not None and 10.8 <= fs <= 12  # piso = 90% de 12 = 10.8
    doc.close()


def test_fontsize_none_se_nem_no_piso_cabe():
    doc, page = _page()
    fs = fontsize_que_cabe(page, fitz.Rect(72, 72, 120, 82),
                           "texto grande demais " * 10, fontsize_base=12, min_pct=90)
    assert fs is None
    doc.close()


# --- Task 4: paginação -------------------------------------------------------

def test_paginar_divide_no_transbordo():
    doc, page = _page()
    rect = fitz.Rect(72, 72, 520, 120)
    texto = " ".join(f"Sentença de teste número {i}." for i in range(60))
    cabe, resto = paginar_prosa(page, rect, texto, fontsize=11)
    assert cabe.strip() and resto.strip()
    # nada se perde: toda palavra do original está em cabe+resto
    assert len((cabe + " " + resto).split()) == len(texto.split())
    doc.close()


def test_paginar_texto_curto_nao_transborda():
    doc, page = _page()
    cabe, resto = paginar_prosa(page, fitz.Rect(72, 72, 520, 300), "Curto.", 11)
    assert cabe.strip() == "Curto." and resto == ""
    doc.close()


def test_paginar_garante_progresso():
    # caixa minúscula: ainda assim consome ao menos 1 palavra (sem loop infinito)
    doc, page = _page()
    cabe, resto = paginar_prosa(page, fitz.Rect(72, 72, 80, 80),
                                "palavra outra mais", 11)
    assert cabe.split(), "deve consumir ao menos 1 palavra"
    doc.close()
