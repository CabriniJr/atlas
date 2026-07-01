import fitz

from atlas.traducao.extracao import extrair_pagina
from atlas.traducao.remontagem import remontar_pagina


def test_substitui_texto_preservando_imagem_e_pulando_codigo(tmp_path):
    path = tmp_path / "in.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "The pod restarts.", fontname="helv", fontsize=12)
    page.insert_text((72, 200), "kubectl get pods", fontname="cour", fontsize=12)
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 20, 20))
    pix.set_rect(pix.irect, (255, 0, 0))
    page.insert_image(fitz.Rect(300, 80, 320, 100), pixmap=pix)
    doc.save(path)

    doc = fitz.open(path)
    page = doc[0]
    blocos = extrair_pagina(page, 0)
    normal = [b for b in blocos if "pod" in b.texto and not b.skip][0]
    traducoes = {normal.id: "O contêiner reinicia."}
    remontar_pagina(page, blocos, traducoes)
    out = tmp_path / "out.pdf"
    doc.save(out)

    doc2 = fitz.open(out)
    texto = doc2[0].get_text()
    assert "The pod restarts" not in texto  # original removido
    assert "contêiner" in texto  # tradução com acento presente
    assert "kubectl get pods" in texto  # código intacto (skip)
    assert len(doc2[0].get_images()) == 1  # imagem preservada
