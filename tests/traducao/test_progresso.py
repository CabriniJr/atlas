from atlas.traducao.pipeline import ProgressoTraducao
from atlas.traducao.progresso import barra_texto


def test_barra_meio():
    b = barra_texto(ProgressoTraducao(paginas_total=10, paginas_prontas=5, blocos_traduzidos=0), largura=10)
    assert "50%" in b
    assert "█████" in b  # metade preenchida
    assert "5/10" in b


def test_barra_completa():
    b = barra_texto(ProgressoTraducao(paginas_total=4, paginas_prontas=4, blocos_traduzidos=0), largura=8)
    assert "100%" in b
    assert "░" not in b  # nada vazio


def test_barra_zero_paginas_nao_quebra():
    b = barra_texto(ProgressoTraducao(paginas_total=0, paginas_prontas=0, blocos_traduzidos=0))
    assert "0%" in b
