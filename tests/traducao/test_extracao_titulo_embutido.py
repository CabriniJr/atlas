"""Título "run-in" (versalete colorido) grudado ao parágrafo seguinte no MESMO
bloco do PyMuPDF (sem quebra de linha real) — bug real visto ao auditar
Kubernetes in Action: o render pega a cor do bloco inteiro de UM só span
(spans[0].color, ver editorial_html._estilo), então título e corpo saem com a
MESMA cor — a do que vier primeiro. Dividir em dois blocos na extração resolve
na raiz (cada um com sua própria cor uniforme)."""

from atlas.traducao.extracao import (
    Span,
    _bbox_uniao_spans,
    _dividir_por_titulo_embutido,
    extrair_pagina,
)

_AZUL = 0x2255AA
_PRETO = 0


def _span(texto, x0, x1, color=_PRETO, y0=100.0):
    return Span(
        text=texto, bbox=(x0, y0, x1, y0 + 10), font="Helvetica", size=11.0, color=color, flags=0
    )


def test_divide_titulo_maiusculo_colorido_do_corpo_seguinte():
    spans = [
        _span("SPLITTING MULTI-TIER APPS. ", 0, 200, color=_AZUL),
        _span("This chapter covers how you break a monolith into services.", 200, 500),
    ]
    divisao = _dividir_por_titulo_embutido(spans)
    assert divisao is not None
    titulo, corpo = divisao
    assert all(s.color == _AZUL for s in titulo)
    assert all(s.color == _PRETO for s in corpo)


def test_nao_divide_paragrafo_normal_uma_cor_so():
    spans = [
        _span("Este parágrafo inteiro é ", 0, 200),
        _span("preto do início ao fim.", 200, 400),
    ]
    assert _dividir_por_titulo_embutido(spans) is None


def test_nao_divide_titulo_sozinho_sem_corpo():
    spans = [_span("SÓ TÍTULO EM VERSALETE", 0, 200, color=_AZUL)]
    assert _dividir_por_titulo_embutido(spans) is None


def test_nao_divide_prefixo_maiusculo_curto_demais():
    # "OK" sozinho não é heading — só 1 palavra, abaixo do mínimo.
    spans = [
        _span("OK ", 0, 30, color=_AZUL),
        _span("isso aqui é só uma frase comum que começa com uma sigla.", 30, 400),
    ]
    assert _dividir_por_titulo_embutido(spans) is None


def test_nao_divide_corpo_com_mais_de_uma_cor():
    # corpo com cores mistas (ex.: link inline) não é o padrão esperado — não força.
    spans = [
        _span("INTRODUCTION TO SCALING", 0, 200, color=_AZUL),
        _span("Isto tem um link ", 200, 350),
        _span("aqui", 350, 380, color=0x0000FF),
    ]
    assert _dividir_por_titulo_embutido(spans) is None


def _bbox_pagina(spans):
    x0 = min(s.bbox[0] for s in spans)
    y0 = min(s.bbox[1] for s in spans)
    x1 = max(s.bbox[2] for s in spans)
    y1 = max(s.bbox[3] for s in spans)
    return (x0, y0, x1, y1)


class _PageFake:
    """Simula o mínimo de ``page.get_text('dict')`` que ``extrair_pagina`` usa."""

    def __init__(self, spans):
        self.rect = type("R", (), {"width": 600.0})()
        self._spans = spans

    def get_text(self, _modo):
        return {
            "blocks": [
                {
                    "bbox": _bbox_pagina(self._spans),
                    "lines": [
                        {
                            "spans": [
                                {
                                    "text": s.text,
                                    "bbox": list(s.bbox),
                                    "font": s.font,
                                    "size": s.size,
                                    "color": s.color,
                                    "flags": s.flags,
                                }
                                for s in self._spans
                            ]
                        }
                    ],
                }
            ]
        }


def test_extrair_pagina_separa_titulo_embutido_em_dois_blocos():
    spans = [
        _span("SPLITTING MULTI-TIER APPS. ", 0, 200, color=_AZUL),
        _span("This chapter covers how you break a monolith into services.", 200, 500),
    ]
    blocos = extrair_pagina(_PageFake(spans), pagina=0)
    assert len(blocos) == 2
    assert blocos[0].spans[0].color == _AZUL
    assert blocos[1].spans[0].color == _PRETO
    # ids sequenciais, sem colisão (ADR-0041: extrair_pagina agora pode gerar
    # mais blocos do que blocks do PyMuPDF — prox_id, não bid do enumerate)
    assert [b.id for b in blocos] == [0, 1]


def test_bbox_uniao_spans_cobre_todos_os_spans():
    spans = [
        Span(text="a", bbox=(10, 20, 30, 40), font="", size=1, color=0, flags=0),
        Span(text="b", bbox=(5, 25, 50, 35), font="", size=1, color=0, flags=0),
    ]
    assert _bbox_uniao_spans(spans) == (5, 20, 50, 40)
