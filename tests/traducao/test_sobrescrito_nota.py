"""Marcadores de nota de rodapé (span sobrescrito do original) viram um número
solto na linha de base depois da concatenação/tradução ("membro 1 da CNCF").
_aplicar_sobrescritos re-eleva pro glifo sobrescrito Unicode (ADR-0047)."""

from types import SimpleNamespace

from atlas.traducao.editorial_html import _aplicar_sobrescritos


def _span(text, flags=0):
    return SimpleNamespace(text=text, flags=flags)


def _bloco(*spans):
    return SimpleNamespace(spans=list(spans))


def test_reeleva_marcador_de_nota():
    b = _bloco(_span("tornou-se o segundo membro "), _span("1", flags=1), _span(" da CNCF."))
    out = _aplicar_sobrescritos("tornou-se o segundo membro 1 da CNCF.", b)
    assert out == "tornou-se o segundo membro¹ da CNCF."


def test_nao_toca_ano_de_quatro_digitos():
    # marcador "4" NÃO pode elevar o "4" dentro de "1994".
    b = _bloco(_span("scripts."), _span("4", flags=1), _span(" O ano de 1994 e 1997"))
    out = _aplicar_sobrescritos("scripts. 4 O ano de 1994 e 1997", b)
    assert out == "scripts.⁴ O ano de 1994 e 1997"
    assert "199⁴" not in out and "1994" in out


def test_sem_span_sobrescrito_nao_altera():
    b = _bloco(_span("veja a seção 2 para detalhes"))  # "2" comum, sem flag
    txt = "veja a seção 2 para detalhes"
    assert _aplicar_sobrescritos(txt, b) == txt


def test_dois_marcadores():
    b = _bloco(_span("texto"), _span("1", flags=1), _span(" mais"), _span("2", flags=1))
    out = _aplicar_sobrescritos("um texto 1 com mais 2 aqui", b)
    assert out == "um texto¹ com mais² aqui"
