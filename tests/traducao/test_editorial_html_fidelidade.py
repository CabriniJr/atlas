from atlas.traducao.editorial_html import _elemento
from atlas.traducao.extracao import BlocoTraducao, Span


def _bloco(texto, size=11.0, bold=False, italic=False, font="Times"):
    span = Span(text=texto, bbox=(72, 100, 400, 116), font=font, size=size, color=0,
                flags=(1 << 4 if bold else 0) | (1 << 1 if italic else 0))
    return BlocoTraducao(id=1, pagina=0, bbox=span.bbox, texto=texto, spans=[span])


def test_elemento_converte_marcador_de_enfase_inline():
    b = _bloco("Original com **muito** destaque.")
    from atlas.traducao.editorial_html import _estilo
    est = _estilo(b)
    html = _elemento(b, "Tradução com **muito** destaque.", est, body_sz=11.0, clusters=[])
    assert "<b>muito</b>" in html


def test_elemento_usa_fonte_real_do_span():
    b = _bloco("Texto qualquer.", font="MinhaFonteCustom")
    from atlas.traducao.editorial_html import _estilo
    est = _estilo(b)
    assert est["font"] == "MinhaFonteCustom"
    html = _elemento(b, "Texto qualquer.", est, body_sz=11.0, clusters=[])
    assert "MinhaFonteCustom" in html


def test_tipo_lista_reconhece_numerado_e_alfabetico():
    from atlas.traducao.editorial_html import _tipo_lista
    assert _tipo_lista("1. Primeiro item") == "ol"
    assert _tipo_lista("a) Item alfabético") == "ol"
    assert _tipo_lista("• Item com bullet") == "ul"
    assert _tipo_lista("Parágrafo comum, sem marcador.") is None


def test_montar_html_nunca_descarta_bloco_sem_traducao(tmp_path):
    import fitz
    from atlas.traducao.editorial_html import _geometria, montar_html
    from atlas.traducao.extracao import extrair_pagina

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "This block never got translated.", fontname="helv", fontsize=12)
    p = tmp_path / "s.pdf"
    doc.save(str(p))
    doc.close()

    doc = fitz.open(str(p))
    blocos = extrair_pagina(doc[0], 0)
    paginas = {0: (blocos, {})}  # dict de traduções vazio — nenhum bloco traduzido
    geo = _geometria(doc, paginas)
    html = montar_html(doc, paginas, geo)
    assert "This block never got translated" in html
    doc.close()
