from atlas.traducao.editorial_html import _elemento
from atlas.traducao.extracao import BlocoTraducao, Span


def _bloco(texto, size=11.0, bold=False, italic=False, font="Times"):
    span = Span(text=texto, bbox=(72, 100, 400, 116), font=font, size=size, color=0,
                flags=(1 << 4 if bold else 0) | (1 << 1 if italic else 0))
    return BlocoTraducao(id=1, pagina=0, bbox=span.bbox, texto=texto, spans=[span])


def test_elemento_converte_marcador_de_enfase_inline():
    b = _bloco("Original com **muito** destaque.")
    from atlas.traducao.editorial_html import _estilo
    est = _estilo(b)
    html = _elemento(b, "Tradução com **muito** destaque.", est, body_sz=11.0, clusters=[])
    assert "<b>muito</b>" in html


def test_elemento_usa_fonte_real_do_span():
    b = _bloco("Texto qualquer.", font="MinhaFonteCustom")
    from atlas.traducao.editorial_html import _estilo
    est = _estilo(b)
    assert est["font"] == "MinhaFonteCustom"
    html = _elemento(b, "Texto qualquer.", est, body_sz=11.0, clusters=[])
    assert "MinhaFonteCustom" in html
