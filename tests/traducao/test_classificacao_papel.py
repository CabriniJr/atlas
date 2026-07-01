"""Classificação de papel do bloco para o render editorial (ADR-0033)."""

from __future__ import annotations

from atlas.traducao.extracao import classificar_papel


def _bloco(texto, bbox, n_linhas=1, mono=False):
    return {"texto": texto, "bbox": bbox, "n_linhas": n_linhas, "mono": mono}


def test_prosa_paragrafo_largo_multilinha():
    b = _bloco("Uma frase longa " * 20, (72, 100, 520, 260), n_linhas=8)
    assert classificar_papel(b, largura_pagina=595) == "prosa"


def test_encaixado_legenda_curta():
    b = _bloco("Figura 1: arquitetura.", (72, 300, 300, 315), n_linhas=1)
    assert classificar_papel(b, largura_pagina=595) == "encaixado"


def test_imutavel_bloco_sem_texto():
    b = _bloco("", (72, 400, 500, 700), n_linhas=0)
    assert classificar_papel(b, largura_pagina=595) == "imutavel"


def test_imutavel_codigo_monoespacado():
    b = _bloco("def f(): return 1", (72, 420, 500, 435), n_linhas=1, mono=True)
    assert classificar_papel(b, largura_pagina=595) == "imutavel"


def test_papel_desconhecido_cai_em_encaixado_seguro():
    # bloco estreito e de 1 linha (nem prosa larga, nem imutável) → encaixado
    b = _bloco("Texto médio.", (72, 100, 200, 115), n_linhas=2)
    assert classificar_papel(b, largura_pagina=595) == "encaixado"
