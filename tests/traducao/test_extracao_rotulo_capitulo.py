""" "CHAPTER N"/"PART N" (rótulo pequeno) grudado ao título do capítulo (fonte
bem maior) no MESMO bloco do PyMuPDF, sem espaço entre eles — achado real,
sistemático em TODOS os 20 capítulos ao auditar Observability Engineering
("CHAPTER 2How Debugging Practices Differ..."). Sem dividir, o capítulo nunca
abre página sozinho: o título fica com tamanho de fonte contaminado pelo
rótulo, não bate com o cluster dos OUTROS títulos do documento."""

from atlas.traducao.extracao import Span, _dividir_por_rotulo_capitulo, extrair_pagina


def _span(texto, x0, x1, size, y0=100.0):
    return Span(
        text=texto, bbox=(x0, y0, x1, y0 + size), font="Helvetica", size=size, color=0, flags=0
    )


class _PageFakeLinhas:
    """Simula ``page.get_text('dict')`` com o rótulo e o título em LINHAS
    separadas do MESMO bloco (forma real do PDF)."""

    def __init__(self, linhas_spans):
        self.rect = type("R", (), {"width": 600.0})()
        self._linhas_spans = linhas_spans

    def get_text(self, _modo):
        bbox = [
            min(s.bbox[0] for linha in self._linhas_spans for s in linha),
            min(s.bbox[1] for linha in self._linhas_spans for s in linha),
            max(s.bbox[2] for linha in self._linhas_spans for s in linha),
            max(s.bbox[3] for linha in self._linhas_spans for s in linha),
        ]
        return {
            "blocks": [
                {
                    "bbox": bbox,
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
                                for s in linha
                            ]
                        }
                        for linha in self._linhas_spans
                    ],
                }
            ]
        }


def test_extrair_pagina_marca_papel_rotulo_capitulo_no_bloco_do_rotulo():
    """O bloco do RÓTULO ganha ``papel="rotulo_capitulo"`` — usado no render
    pra impedir que ele fique órfão no fim da página anterior enquanto o
    título (que abre página sozinho) pula pra próxima (ADR-0041 fix)."""
    linhas = [
        [_span("CHAPTER 2", 372.8, 432.0, size=16.8, y0=75.8)],
        [_span("How Debugging Practices Differ", 248.1, 432.0, size=25.2, y0=97.8)],
    ]
    blocos = extrair_pagina(_PageFakeLinhas(linhas), pagina=0)
    assert len(blocos) == 2
    assert blocos[0].texto == "CHAPTER 2"
    assert blocos[0].papel == "rotulo_capitulo"
    assert blocos[1].texto == "How Debugging Practices Differ"
    assert blocos[1].papel != "rotulo_capitulo"


def test_divide_rotulo_capitulo_do_titulo_maior():
    spans = [
        _span("CHAPTER 2", 0, 60, size=16.8),
        _span("How Debugging Practices Differ", 60, 400, size=25.2),
    ]
    divisao = _dividir_por_rotulo_capitulo(spans)
    assert divisao is not None
    rotulo, titulo = divisao
    assert all(s.size == 16.8 for s in rotulo)
    assert all(s.size == 25.2 for s in titulo)


def test_nao_divide_paragrafo_normal_um_tamanho_so():
    spans = [
        _span("Este parágrafo inteiro é ", 0, 200, size=10.5),
        _span("do mesmo tamanho do início ao fim.", 200, 400, size=10.5),
    ]
    assert _dividir_por_rotulo_capitulo(spans) is None


def test_nao_divide_salto_de_tamanho_pequeno_demais():
    # negrito/ênfase local costuma variar 1-2pt — não é rótulo de capítulo.
    spans = [
        _span("Um termo ", 0, 60, size=10.5),
        _span("enfatizado", 60, 150, size=12.0),
        _span(" no meio da frase.", 150, 300, size=10.5),
    ]
    assert _dividir_por_rotulo_capitulo(spans) is None


def test_nao_divide_rotulo_sozinho_sem_titulo():
    spans = [_span("CHAPTER 2", 0, 60, size=16.8)]
    assert _dividir_por_rotulo_capitulo(spans) is None


def test_nao_divide_rotulo_longo_demais():
    # um "rótulo" de 6 palavras não é "CHAPTER N"/"PART N" — não força.
    spans = [
        _span("Isto aqui parece uma frase normal e", 0, 200, size=11.0),
        _span("não deveria ser confundido com rótulo.", 200, 450, size=25.0),
    ]
    assert _dividir_por_rotulo_capitulo(spans) is None


def test_nao_divide_quando_titulo_nao_e_uniforme():
    # se o "título" tiver tamanhos mistos, pode não ser esse padrão — não força.
    spans = [
        _span("PART I", 0, 60, size=16.8),
        _span("Observability", 60, 300, size=25.2),
        _span("Basics", 300, 400, size=20.0),
    ]
    assert _dividir_por_rotulo_capitulo(spans) is None
