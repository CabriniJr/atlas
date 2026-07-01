import fitz

from atlas.traducao.extracao import BlocoTraducao, extrair_pagina


def test_extrai_blocos_com_metadados(pdf_simples):
    doc = fitz.open(pdf_simples)
    blocos = extrair_pagina(doc[0], 0)
    assert len(blocos) >= 2
    normal = [b for b in blocos if "deployment" in b.texto][0]
    assert isinstance(normal, BlocoTraducao)
    assert normal.pagina == 0
    assert normal.skip is False
    assert normal.spans[0].size == 12


def test_marca_monospace_como_skip(pdf_simples):
    doc = fitz.open(pdf_simples)
    blocos = extrair_pagina(doc[0], 0)
    codigo = [b for b in blocos if "kubectl" in b.texto][0]
    assert codigo.skip is True
