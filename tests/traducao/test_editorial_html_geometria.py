"""TDD — _geometria/_e_folio do motor editorial (ADR-0036).

Regressão: `_geometria` estimava a margem direita/inferior pela mediana **por
página** do bloco mais extremo; em páginas com só linhas curtas (ou documentos
com pouco texto), isso inflava a margem e estreitava a coluna útil ao ponto do
texto traduzido (mais longo) colidir com o folio/paginar no meio de uma frase
curta — visível em produção como "texto sobrepondo o número da página".
"""

from __future__ import annotations

import fitz

from atlas.traducao.editorial_html import _e_folio, _geometria
from atlas.traducao.extracao import extrair_pagina


def _pdf_com_paginas(tmp_path, *paginas_linhas):
    """Cada item de ``paginas_linhas`` é uma lista de (texto, x, y)."""
    path = tmp_path / "g.pdf"
    doc = fitz.open()
    for linhas in paginas_linhas:
        p = doc.new_page()
        for texto, x, y in linhas:
            p.insert_text((x, y), texto, fontname="helv", fontsize=12)
    doc.save(path)
    doc.close()
    return str(path)


def _paginas_dict(path):
    doc = fitz.open(path)
    paginas = {i: (extrair_pagina(doc[i], i), {}) for i in range(doc.page_count)}
    return doc, paginas


def test_geometria_uma_linha_curta_nao_estreita_a_coluna(tmp_path):
    """Regressão principal: 1 bloco curto não pode inferir margem direita de
    ~440pt (coluna de ~85pt) — usa o piso mínimo de largura útil."""
    path = _pdf_com_paginas(tmp_path, [("The pod scales.", 72, 100)])
    doc, paginas = _paginas_dict(path)
    geo = _geometria(doc, paginas)
    largura_util = geo["pw"] - geo["left"] - geo["right"]
    assert largura_util >= 300.0


def test_geometria_documento_com_linhas_longas_usa_margem_real(tmp_path):
    """Com dado suficiente (linha que realmente alcança perto da borda), a
    margem direita reflete a borda real — não o piso mínimo."""
    linha_longa = "x" * 70  # ~ocupa quase a largura útil em fontsize 12
    paginas_linhas = [[(linha_longa, 72, 100 + i * 20) for i in range(5)] for _ in range(3)]
    path = _pdf_com_paginas(tmp_path, *paginas_linhas)
    doc, paginas = _paginas_dict(path)
    geo = _geometria(doc, paginas)
    # a linha longa termina bem antes da borda física (595pt) — margem direita
    # pequena, bem menor que a inflada pelo bug antigo (~440pt).
    assert geo["right"] < 150.0


def test_geometria_pagina_de_sumario_nao_contamina_documento_com_dado_suficiente(tmp_path):
    """Uma página só de linhas curtas (tipo sumário) não deve, sozinha, estreitar
    a coluna do documento inteiro quando as outras páginas têm linhas longas."""
    curta = [("Capítulo 1 . . . . . 5", 72, 100 + i * 20) for i in range(6)]  # "sumário"
    longa = [("x" * 70, 72, 100 + i * 20) for i in range(6)]
    path = _pdf_com_paginas(tmp_path, curta, longa, longa, longa)
    doc, paginas = _paginas_dict(path)
    geo = _geometria(doc, paginas)
    assert geo["right"] < 150.0


def test_e_folio_bloco_curto_na_margem_inferior():
    class B:
        bbox = (300.0, 800.0, 310.0, 812.0)
        texto = "42"

    assert _e_folio(B(), ph=842.0) is True


def test_e_folio_paragrafo_normal_nao_e_folio():
    class B:
        bbox = (72.0, 300.0, 500.0, 316.0)
        texto = "Este é um parágrafo comum de corpo de texto, bem no meio da página."

    assert _e_folio(B(), ph=842.0) is False
