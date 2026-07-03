import re

import fitz

from atlas.traducao.pipeline import ProgressoTraducao, traduzir_pdf
from atlas.traducao.traducao_ia import CacheTraducao, ConfigTraducao


def _fake_invocar_factory(contador):
    def fake(prompt, modelo=None, timeout=60, motor="claude"):
        contador.append(1)
        ids = re.findall(r"\[\[(\d+)\]\]", prompt)
        return "\n".join(f"[[{i}]] TRADUZIDO {i}" for i in ids)

    return fake


def _fake_bruto(textos, cfg):  # MT offline p/ testes: prefixa BRUTO (sem rede)
    return [f"BRUTO {t}" for t in textos]


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
        bruto_fn=_fake_bruto,
    )
    assert isinstance(res, ProgressoTraducao)
    assert res.paginas_total == 2
    assert res.paginas_prontas == 2
    assert progresso == [1, 2]
    assert out.exists()
    assert "TRADUZIDO" in fitz.open(out)[0].get_text()


def test_somente_render_preferir_bruto_usa_mt_mesmo_com_refino_cacheado(tmp_path):
    src = tmp_path / "src.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((72, 100), "Page content here.", fontname="helv", fontsize=12)
    doc.save(src)

    cfg = ConfigTraducao()
    cache = CacheTraducao()
    cache.put_bruto("Page content here.", cfg, "BRUTO Page content here.")
    cache.put("Page content here.", cfg, "REFINADO Page content here.")

    out_refino = tmp_path / "out_refino.pdf"
    traduzir_pdf(str(src), str(out_refino), cfg, cache=cache, somente_render=True)
    texto_refino = fitz.open(out_refino)[0].get_text()
    assert "REFINADO" in texto_refino
    assert "BRUTO" not in texto_refino

    out_bruto = tmp_path / "out_bruto.pdf"
    traduzir_pdf(
        str(src), str(out_bruto), cfg, cache=cache, somente_render=True, preferir_bruto=True
    )
    texto_bruto = fitz.open(out_bruto)[0].get_text()
    assert "BRUTO" in texto_bruto
    assert "REFINADO" not in texto_bruto


def test_pipeline_usa_render_editorial_gera_continuacao(tmp_path):
    """Prosa + tradução gigante deve gerar página de continuação via o pipeline."""
    import re

    from atlas.traducao.pipeline import traduzir_pdf
    from atlas.traducao.traducao_ia import ConfigTraducao

    src = tmp_path / "src.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_textbox(
        fitz.Rect(72, 90, 520, 200), "Original paragraph. " * 12,
        fontname="helv", fontsize=11,
    )
    doc.save(str(src))
    doc.close()

    def invocar_gigante(prompt, modelo=None, timeout=60, motor="claude"):
        ids = re.findall(r"\[\[(\d+)\]\]", prompt)
        return "\n".join(f"[[{i}]] " + ("Tradução enorme. " * 300) for i in ids)

    out = tmp_path / "out.pdf"
    traduzir_pdf(
        str(src), str(out), ConfigTraducao(),
        invocar_fn=invocar_gigante,
        bruto_fn=lambda textos, cfg: ["BRUTO"] * len(textos),
    )
    res = fitz.open(str(out))
    assert res.page_count > 1, "render editorial deveria ter gerado página de continuação"
    res.close()
