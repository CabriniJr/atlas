import re

import fitz

from atlas.traducao.pipeline import ProgressoTraducao, traduzir_pdf
from atlas.traducao.traducao_ia import ConfigTraducao


def _fake_invocar_factory(contador):
    def fake(prompt, modelo=None, timeout=60, motor="claude"):
        contador.append(1)
        ids = re.findall(r"\[\[(\d+)\]\]", prompt)
        return "\n".join(f"[[{i}]] TRADUZIDO {i}" for i in ids)

    return fake


def test_traduz_pdf_gera_saida_e_reporta_progresso(tmp_path):
    src = tmp_path / "src.pdf"
    doc = fitz.open()
    for n in range(2):
        p = doc.new_page()
        p.insert_text((72, 100), f"Page {n} content here.", fontname="helv", fontsize=12)
    doc.save(src)

    out = tmp_path / "out.pdf"
    progresso = []
    contador = []
    cfg = ConfigTraducao()
    res = traduzir_pdf(
        str(src),
        str(out),
        cfg,
        invocar_fn=_fake_invocar_factory(contador),
        on_progress=lambda p: progresso.append(p.paginas_prontas),
    )
    assert isinstance(res, ProgressoTraducao)
    assert res.paginas_total == 2
    assert res.paginas_prontas == 2
    assert progresso == [1, 2]
    assert out.exists()
    assert "TRADUZIDO" in fitz.open(out)[0].get_text()
