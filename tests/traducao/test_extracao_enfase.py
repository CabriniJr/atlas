import itertools

from atlas.traducao.extracao import Span, _juntar_spans, _marcar_enfase

_BOLD = 1 << 4
_ITALIC = 1 << 1
_contador_x = itertools.count()


def _span(texto, flags=0):
    # x0 sempre avança com folga real (>1pt) entre chamadas — spans de texto
    # corrido têm espaço de verdade entre si (diferente do teste de
    # adjacência, que usa _span_pos com posições explícitas sem folga).
    x0 = next(_contador_x) * 20
    return Span(
        text=texto, bbox=(x0, 0, x0 + 10, 10), font="Times", size=11.0, color=0, flags=flags
    )


def _span_pos(texto, x0, x1, y0=100.0):
    return Span(
        text=texto, bbox=(x0, y0, x1, y0 + 10), font="UbuntuMono", size=10.0, color=0, flags=0
    )


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


def test_marcar_enfase_nao_insere_espaco_entre_tokens_adjacentes():
    # Achado real (auditoria visual, Kubernetes in Action): tipografia
    # versalete/small-caps é feita variando o TAMANHO por span ("P" maior +
    # "ART" menor, sem gap real entre eles) — _marcar_enfase juntava tudo com
    # um espaço fixo, direto, virando "P ART 3 B EYOND" em vez de "PART 3
    # BEYOND" (mesma lógica de adjacência que _juntar_spans já tinha).
    spans = [
        _span_pos("P", 57.18, 65.87),
        _span_pos("ART", 65.85, 88.48),
        _span_pos(" 3", 88.47, 99.39),
        _span_pos("B", 113.37, 122.62),
        _span_pos("EYOND", 122.61, 162.92),
    ]
    assert _marcar_enfase(spans) == "PART 3 BEYOND"


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
