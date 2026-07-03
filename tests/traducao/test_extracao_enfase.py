from atlas.traducao.extracao import Span, _juntar_spans, _marcar_enfase

_BOLD = 1 << 4
_ITALIC = 1 << 1


def _span(texto, flags=0):
    return Span(text=texto, bbox=(0, 0, 10, 10), font="Times", size=11.0, color=0, flags=flags)


def _span_pos(texto, x0, x1, y0=100.0):
    return Span(text=texto, bbox=(x0, y0, x1, y0 + 10), font="UbuntuMono", size=10.0, color=0,
                flags=0)


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


def test_juntar_spans_nao_insere_espaco_entre_tokens_adjacentes():
    # "http.server.BaseHTTPRequestHandler" com syntax highlighting: cada token
    # (incluindo os pontos) é um span separado, mas SEM espaço real entre eles.
    spans = [
        _span_pos("http", 158.4, 180.0),
        _span_pos(".", 180.0, 185.4),
        _span_pos("server", 185.4, 217.8),
        _span_pos(".", 217.8, 223.2),
        _span_pos("BaseHTTPRequestHandler", 223.2, 342.0),
    ]
    assert _juntar_spans(spans) == "http.server.BaseHTTPRequestHandler"


def test_juntar_spans_insere_espaco_quando_ha_folga_real():
    spans = [
        _span_pos("class", 72.0, 99.0),
        _span_pos("MyHandler", 104.4, 153.0),  # folga de 5.4pt = espaço real
    ]
    assert _juntar_spans(spans) == "class MyHandler"


def test_juntar_spans_insere_espaco_entre_linhas_diferentes():
    spans = [
        _span_pos("primeira", 72.0, 120.0, y0=100.0),
        _span_pos("linha", 72.0, 110.0, y0=115.0),  # y diferente = nova linha
    ]
    assert _juntar_spans(spans) == "primeira linha"


def test_juntar_spans_vazio():
    assert _juntar_spans([]) == ""
