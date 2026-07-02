"""Remontagem editorial (ADR-0033): reflow de prosa + página de continuação, figuras intactas."""

from __future__ import annotations

import fitz

from atlas.traducao.extracao import extrair_pagina
from atlas.traducao.remontagem import remontar_documento


def test_prosa_que_cresce_gera_pagina_de_continuacao(tmp_path):
    doc = fitz.open()
    page = doc.new_page()
    # parágrafo largo e multi-linha → classificado como prosa
    page.insert_textbox(
        fitz.Rect(72, 90, 520, 200),
        "Original paragraph. " * 12,
        fontname="helv",
        fontsize=11,
    )
    src = tmp_path / "src.pdf"
    doc.save(str(src))
    doc.close()

    doc = fitz.open(str(src))
    blocos = extrair_pagina(doc[0], 0)
    traducoes = {
        b.id: ("Parágrafo traduzido bem maior que o original. " * 80)
        for b in blocos
        if not b.skip
    }
    n_antes = doc.page_count
    remontar_documento(doc, {0: (blocos, traducoes)}, min_fonte_pct=90)
    assert doc.page_count > n_antes, "deveria inserir página de continuação"
    txt = "".join(doc[i].get_text() for i in range(doc.page_count))
    assert "Parágrafo traduzido" in txt
    doc.close()


def test_figura_permanece_intacta(tmp_path):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Caption near a figure.", fontsize=11)
    page.draw_rect(fitz.Rect(72, 300, 300, 450), fill=(0, 0, 1))  # proxy de figura
    src = tmp_path / "s.pdf"
    doc.save(str(src))
    doc.close()

    doc = fitz.open(str(src))
    blocos = extrair_pagina(doc[0], 0)
    traducoes = {b.id: "Legenda perto de uma figura." for b in blocos if not b.skip}
    remontar_documento(doc, {0: (blocos, traducoes)}, min_fonte_pct=90)
    assert doc[0].get_drawings(), "desenhos (figura) não podem sumir"
    doc.close()


def test_fidelidade_ordem_e_figuras(tmp_path):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 80), "Alpha.", fontsize=11)
    page.draw_rect(fitz.Rect(72, 120, 300, 260), fill=(1, 0, 0))  # figura
    page.insert_text((72, 300), "Beta.", fontsize=11)
    src = tmp_path / "s.pdf"
    doc.save(str(src))
    doc.close()

    doc = fitz.open(str(src))
    blocos = extrair_pagina(doc[0], 0)
    traducoes = {
        b.id: ("Alfa." if "Alpha" in b.texto else "Beta.")
        for b in blocos
        if not b.skip
    }
    n_draw_antes = len(doc[0].get_drawings())
    remontar_documento(doc, {0: (blocos, traducoes)}, min_fonte_pct=90)
    assert len(doc[0].get_drawings()) >= n_draw_antes  # figura preservada
    t = doc[0].get_text()
    assert "Alfa" in t and "Beta" in t
    assert t.index("Alfa") < t.index("Beta")  # ordem de leitura preservada
    doc.close()
