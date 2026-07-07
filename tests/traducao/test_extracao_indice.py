"""Reconstrução de entradas do índice remissivo (ADR-0041): PyMuPDF quebra cada
entrada multi-linha (hanging indent) em linhas que não batem com a entrada
lógica; juntar as continuações por referência-de-página deixa o índice legível.
"""

from atlas.traducao.extracao import agrupar_entradas_indice


def test_agrupar_junta_continuacao_ate_a_pagina():
    # linhas reais de uma coluna do índice (Kubernetes in Action, p594):
    # termo principal (x66), sub-entradas (x84), continuação de quebra (x102).
    # (x0, y0, texto)
    linhas = [
        (66.2, 100.0, "applications (continued)"),
        (84.2, 112.0, "locating containers 21"),
        (84.2, 124.0, "outside of Kubernetes during"),
        (102.2, 136.0, "development 502–503"),
        (84.2, 148.0, "scaling number of copies 21"),
        (84.2, 160.0, "through services using single"),
        (102.2, 172.0, "YAML file 255"),
    ]
    entradas = agrupar_entradas_indice(linhas)
    textos = [t for _x, _y, t in entradas]
    assert "applications (continued)" in textos  # termo principal, sozinho
    assert "outside of Kubernetes during development 502–503" in textos  # wrap juntado
    assert "through services using single YAML file 255" in textos
    assert "scaling number of copies 21" in textos
    # 5 entradas: termo + 4 sub-entradas (nenhum fragmento solto)
    assert len(entradas) == 5


def test_agrupar_termo_principal_nao_gruda_com_subentrada():
    # termo no recuo mínimo (sem página) NÃO absorve a sub-entrada seguinte.
    linhas = [(66.0, 100.0, "arguments"), (84.0, 112.0, "defining in Docker 193–195")]
    entradas = agrupar_entradas_indice(linhas)
    assert entradas == [(66.0, 100.0, "arguments"), (84.0, 112.0, "defining in Docker 193–195")]


def test_agrupar_vazio():
    assert agrupar_entradas_indice([]) == []
