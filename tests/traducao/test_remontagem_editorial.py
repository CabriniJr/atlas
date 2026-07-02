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
    # tradução maior que uma página inteira (o reflow agora usa a altura toda da
    # página antes de transbordar; só passa disso vira continuação).
    traducoes = {
        b.id: ("Parágrafo traduzido bem maior que o original. " * 200)
        for b in blocos
        if not b.skip
    }
    n_antes = doc.page_count
    remontar_documento(doc, {0: (blocos, traducoes)}, min_fonte_pct=90)
    assert doc.page_count > n_antes, "deveria inserir página de continuação"
    txt = "".join(doc[i].get_text() for i in range(doc.page_count))
    assert "Parágrafo traduzido" in txt
    doc.close()


def test_glyphs_unicode_preservados(tmp_path):
    """Bullet, aspas curvas e travessão devem renderizar (a fonte embutida os tem);
    a Helvetica builtin virava '?'."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_textbox(fitz.Rect(72, 90, 520, 200), "Original paragraph text here. " * 6,
                        fontname="helv", fontsize=11)
    src = tmp_path / "g.pdf"
    doc.save(str(src))
    doc.close()

    doc = fitz.open(str(src))
    blocos = extrair_pagina(doc[0], 0)
    alvo = "Itens: • primeiro — “segundo” – terceiro’s."
    traducoes = {b.id: alvo for b in blocos if not b.skip}
    remontar_documento(doc, {0: (blocos, traducoes)}, min_fonte_pct=90)
    txt = doc[0].get_text()
    for ch in ["•", "—", "“", "”", "–", "’"]:
        assert ch in txt, f"glyph {ch!r} deveria renderizar (sem virar '?')"
    assert "?" not in txt
    doc.close()


def test_prosa_nao_sobrepoe_vizinhos(tmp_path):
    """Dois parágrafos empilhados: ao crescer, o de cima empurra o de baixo — sem colisão."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_textbox(fitz.Rect(72, 90, 520, 160), "First paragraph. " * 10,
                        fontname="helv", fontsize=11)
    page.insert_textbox(fitz.Rect(72, 170, 520, 240), "Second paragraph. " * 10,
                        fontname="helv", fontsize=11)
    src = tmp_path / "s2.pdf"
    doc.save(str(src))
    doc.close()

    doc = fitz.open(str(src))
    blocos = extrair_pagina(doc[0], 0)
    traducoes = {b.id: ("Texto traduzido bem mais longo que o original. " * 8)
                 for b in blocos if not b.skip}
    remontar_documento(doc, {0: (blocos, traducoes)}, min_fonte_pct=90)
    caixas = sorted((b[:4] for b in doc[0].get_text("blocks")), key=lambda r: r[1])
    for (_, _, _, y1), (_, y0b, _, _) in zip(caixas, caixas[1:], strict=False):
        assert y0b >= y1 - 1.0, "blocos de texto não podem se sobrepor verticalmente"
    doc.close()
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


def test_nota_de_rodape_para_termo_mantido(tmp_path):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Original mentions Kubernetes here.", fontsize=11)
    src = tmp_path / "s.pdf"
    doc.save(str(src))
    doc.close()

    doc = fitz.open(str(src))
    blocos = extrair_pagina(doc[0], 0)
    traducoes = {b.id: "O texto menciona Kubernetes aqui." for b in blocos if not b.skip}
    notas = {
        b.id: [{"termo": "Kubernetes", "glosa": "orquestrador de contêineres"}]
        for b in blocos if not b.skip
    }
    remontar_documento(doc, {0: (blocos, traducoes)}, min_fonte_pct=90, notas=notas)
    txt = doc[0].get_text()
    assert "orquestrador de contêineres" in txt  # glosa impressa ao pé
    doc.close()
