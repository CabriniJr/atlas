"""Outline/bookmarks do PDF por papel estrutural (ADR-0046): em livro com PARTES,
Parte>Capítulo>Seção têm que aninhar de verdade — não cair todos no mesmo nível
(bug real: Prometheus tinha "Parte I" e "Capítulo 1" ambos como bookmark nível 1;
Observability tinha o rótulo solto "parte i" poluindo o outline)."""

import re

from atlas.traducao.editorial_html import _atribuir_niveis_outline


def _nivel(frag: str):
    m = re.search(r"bookmark-level:\s*(\w+)", frag)
    if not m:
        return "PADRAO"  # não tocado ⇒ WeasyPrint usa tag→nível
    return m.group(1)


def test_oreilly_parte_rotulada_aninha_capitulo_secao_subsecao():
    # Prometheus: Parte e Capítulo são AMBOS h1, distintos só pelo rótulo.
    partes = [
        '<h1 style="font-size:20pt">Prometheus: Operacional</h1>',  # título do livro
        '<h1 style="font-size:20pt">Parte I. Introdução</h1>',
        '<h1 style="font-size:20pt">Capítulo 1. O que é Prometheus?</h1>',
        '<h2 style="font-size:14pt">O que é monitoramento?</h2>',
        '<h3 style="font-size:12pt">Uma breve história</h3>',
        '<h1 style="font-size:20pt">Capítulo 2. Introdução</h1>',
        '<h1 style="font-size:20pt">Parte II. Monitoramento</h1>',
    ]
    _atribuir_niveis_outline(partes)
    assert _nivel(partes[1]) == "1"  # Parte I
    assert _nivel(partes[2]) == "2"  # Capítulo 1
    assert _nivel(partes[3]) == "3"  # Seção
    assert _nivel(partes[4]) == "4"  # Subseção
    assert _nivel(partes[6]) == "1"  # Parte II


def test_oreilly_rotulo_parte_solto_funde_no_titulo():
    # Observability: rótulo pequeno "parte i" (h3) + título grande da parte (h1).
    partes = [
        '<h3 style="x">parte i</h3>',
        '<h1 style="x">O caminho para a observabilidade</h1>',
        '<h2 style="x">O que é observabilidade?</h2>',  # capítulo (sem rótulo)
        '<h3 style="x">A definição matemática</h3>',  # seção
        '<h3 style="x">parte ii</h3>',
        '<h1 style="x">Fundamentos</h1>',
        '<h2 style="x">Eventos são a base</h2>',
    ]
    _atribuir_niveis_outline(partes)
    assert _nivel(partes[0]) == "none"  # rótulo solto: sem bookmark
    assert _nivel(partes[1]) == "1"  # título da parte vira a Parte
    assert _nivel(partes[2]) == "2"  # capítulo (h2)
    assert _nivel(partes[3]) == "3"  # seção (h3)
    assert _nivel(partes[4]) == "none"
    assert _nivel(partes[5]) == "1"
    assert _nivel(partes[6]) == "2"


def test_sem_partes_nao_mexe_no_outline():
    # Kubernetes: partes não são heading (divisor rasterizado) ⇒ não tocar.
    partes = [
        '<h1 style="x">Kubernetes in Action</h1>',
        '<h2 style="x">Apresentando o Kubernetes</h2>',
        '<h2 style="x">apêndice A Usando kubectl</h2>',
    ]
    _atribuir_niveis_outline(partes)
    assert all(_nivel(p) == "PADRAO" for p in partes)


def test_parte_da_configuracao_nao_e_falso_positivo():
    # "Parte da X" (prosa/seção) NÃO pode ser confundido com divisor de Parte.
    partes = [
        '<h2 style="x">Parte da configuração do sistema</h2>',
        '<h3 style="x">Detalhe</h3>',
    ]
    _atribuir_niveis_outline(partes)
    assert all(_nivel(p) == "PADRAO" for p in partes)  # sem parte ⇒ intocado
