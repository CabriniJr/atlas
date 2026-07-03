"""Bullet duplicado (glifo desenhado 2x na mesma posição) — achado real ao
auditar Observability Engineering: o PDF de origem emite o marcador de bullet
como uma "linha" extra do bloco do PyMuPDF, com o MESMO bbox do bullet já
capturado na primeira linha. Sem filtrar, o `•` extra some junto ao texto e
vaza como um segundo bullet solto no FIM de cada item da lista traduzida."""

from atlas.traducao.extracao import extrair_pagina


class _PageFakeBlocosCrus:
    """Simula ``page.get_text('dict')`` a partir de uma lista de blocks JÁ
    NO FORMATO CRU do PyMuPDF (permite reproduzir a estrutura exata do bug:
    2 "lines" no mesmo bloco, uma delas só com o bullet duplicado)."""

    def __init__(self, blocks):
        self.rect = type("R", (), {"width": 600.0})()
        self._blocks = blocks

    def get_text(self, _modo):
        return {"blocks": self._blocks}


def _span_cru(texto, x0, x1, y0, y1, font="MinionPro-Regular", size=11.0):
    return {
        "text": texto,
        "bbox": [x0, y0, x1, y1],
        "font": font,
        "size": size,
        "color": 0,
        "flags": 0,
    }


def test_extrai_pagina_remove_bullet_duplicado_em_linha_extra():
    # Reproduz a forma exata achada no PDF real: bullet + espaço + texto na
    # "line 0"; "line 1" é só o MESMO bullet, bbox idêntico (glifo repetido).
    bloco = {
        "bbox": [80.65, 355.3, 410.27, 369.47],
        "lines": [
            {
                "spans": [
                    _span_cru("•", 80.6529, 84.7479, 355.308, 369.4725),
                    _span_cru(" ", 84.7479, 89.9949, 355.308, 369.4725),
                    _span_cru(
                        "What observability means in the context of software",
                        89.9949,
                        410.2764,
                        355.308,
                        369.4725,
                    ),
                ]
            },
            {"spans": [_span_cru("•", 80.6529, 84.7479, 355.308, 369.4725)]},
        ],
    }
    blocos = extrair_pagina(_PageFakeBlocosCrus([bloco]), pagina=0)
    assert len(blocos) == 1
    assert blocos[0].texto == "• What observability means in the context of software"
    assert blocos[0].texto.count("•") == 1


def test_extrai_pagina_preserva_bullets_legitimos_de_itens_diferentes():
    # Dois itens de lista DE VERDADE (bboxes diferentes) não devem ser
    # confundidos com duplicata — cada um vira seu próprio bloco.
    item1 = {
        "bbox": [80.65, 355.3, 300.0, 369.47],
        "lines": [
            {
                "spans": [
                    _span_cru("•", 80.65, 84.74, 355.3, 369.47),
                    _span_cru(" ", 84.74, 89.99, 355.3, 369.47),
                    _span_cru("Primeiro item", 89.99, 200.0, 355.3, 369.47),
                ]
            }
        ],
    }
    item2 = {
        "bbox": [80.65, 371.9, 300.0, 386.07],
        "lines": [
            {
                "spans": [
                    _span_cru("•", 80.65, 84.74, 371.9, 386.07),
                    _span_cru(" ", 84.74, 89.99, 371.9, 386.07),
                    _span_cru("Segundo item", 89.99, 200.0, 371.9, 386.07),
                ]
            }
        ],
    }
    blocos = extrair_pagina(_PageFakeBlocosCrus([item1, item2]), pagina=0)
    assert [b.texto for b in blocos] == ["• Primeiro item", "• Segundo item"]
