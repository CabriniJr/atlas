import re

import fitz

from atlas.traducao.pipeline import traduzir_pdf
from atlas.traducao.traducao_ia import ConfigTraducao


def test_livro_multibloco_preserva_design_e_glossario(tmp_path):
    src = tmp_path / "livro.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "The pod scales automatically.", fontname="helv", fontsize=12)
    page.insert_text((72, 140), "kubectl apply -f pod.yaml", fontname="cour", fontsize=11)
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 16, 16))
    pix.set_rect(pix.irect, (0, 128, 255))
    page.insert_image(fitz.Rect(300, 90, 316, 106), pixmap=pix)
    doc.save(src)
    doc.close()

    def fake_invocar(prompt, modelo=None, timeout=60, motor="claude"):
        ids = re.findall(r"\[\[(\d+)\]\]", prompt)
        # mantém "pod" (glossário) em inglês, traduz o resto com acento
        return "\n".join(f"[[{i}]] O pod escala automaticamente." for i in ids)

    out = tmp_path / "out.pdf"
    cfg = ConfigTraducao(assunto="Kubernetes", glossario=["pod"])
    traduzir_pdf(str(src), str(out), cfg, invocar_fn=fake_invocar)

    r = fitz.open(out)[0]
    texto = r.get_text()
    assert "The pod scales automatically" not in texto  # original traduzido
    assert "pod" in texto  # glossário preservado
    assert "automaticamente" in texto  # acento renderiza
    assert "kubectl apply -f pod.yaml" in texto  # código intacto
    assert len(r.get_images()) == 1  # imagem preservada
