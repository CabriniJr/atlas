from atlas.traducao.extracao import Span, _marcar_enfase

_BOLD = 1 << 4
_ITALIC = 1 << 1


def _span(texto, flags=0):
    return Span(text=texto, bbox=(0, 0, 10, 10), font="Times", size=11.0, color=0, flags=flags)


def test_palavra_em_negrito_no_meio_ganha_marcador():
    spans = [
        _span("Isto é "),
        _span("muito", flags=_BOLD),
        _span(" importante."),
    ]
    assert _marcar_enfase(spans) == "Isto é **muito** importante."


def test_bloco_totalmente_em_negrito_nao_marca_nada():
    spans = [_span("Título", flags=_BOLD), _span("do capítulo", flags=_BOLD)]
    assert _marcar_enfase(spans) == "Título do capítulo"


def test_palavra_em_italico_no_meio_ganha_marcador():
    spans = [_span("Veja o termo "), _span("in situ", flags=_ITALIC), _span(" no texto.")]
    assert _marcar_enfase(spans) == "Veja o termo _in situ_ no texto."


def test_span_vazio_e_ignorado():
    spans = [_span("Texto"), _span("   "), _span(" normal.")]
    assert _marcar_enfase(spans) == "Texto normal."
