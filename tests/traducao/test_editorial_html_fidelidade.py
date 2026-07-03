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


def test_e_rodape_nativo_distingue_nota_de_folio():
    from atlas.traducao.editorial_html import _e_rodape_nativo

    class Nota:
        bbox = (72.0, 745.0, 400.0, 760.0)
        texto = "1. Este termo tem uma explicação mais longa aqui embaixo."

    class Folio:
        bbox = (300.0, 820.0, 310.0, 832.0)
        texto = "42"

    assert _e_rodape_nativo(Nota(), ph=842.0) is True
    assert _e_rodape_nativo(Folio(), ph=842.0) is False


def test_montar_html_renderiza_nota_de_rodape_nativa(tmp_path):
    import fitz
    from atlas.traducao.editorial_html import _geometria, montar_html
    from atlas.traducao.extracao import extrair_pagina

    doc = fitz.open()
    page = doc.new_page()  # altura default ~792pt
    page.insert_text((72, 100), "Corpo do texto principal da página.", fontname="helv", fontsize=12)
    page.insert_text((72, 760), "1. Nota explicativa ao pé da página aqui.", fontname="helv", fontsize=8)
    p = tmp_path / "s.pdf"
    doc.save(str(p))
    doc.close()

    doc = fitz.open(str(p))
    blocos = extrair_pagina(doc[0], 0)
    traducoes = {b.id: b.texto for b in blocos if not b.skip}
    paginas = {0: (blocos, traducoes)}
    geo = _geometria(doc, paginas)
    html = montar_html(doc, paginas, geo)
    assert 'class="rodape-nativo"' in html
    assert "Nota explicativa" in html
    doc.close()


def test_valor_folio_extrai_numero_arabico_e_romano():
    from atlas.traducao.editorial_html import _valor_folio

    class Arabico:
        texto = "18 | Chapter 1: What Is Observability?"

    class Romano:
        texto = "xviii | Preface"

    class SemNumero:
        texto = "Chapter Title"

    assert _valor_folio(Arabico()) == "18"
    assert _valor_folio(Romano()) == "xviii"
    assert _valor_folio(SemNumero()) is None


def test_montar_html_emite_marcador_de_folio_por_pagina(tmp_path):
    import fitz
    from atlas.traducao.editorial_html import _geometria, montar_html
    from atlas.traducao.extracao import extrair_pagina

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Corpo da página quarenta e dois.", fontname="helv", fontsize=12)
    page.insert_text((300, 820), "42", fontname="helv", fontsize=9)  # fólio no rodapé
    p = tmp_path / "s.pdf"
    doc.save(str(p))
    doc.close()

    doc = fitz.open(str(p))
    blocos = extrair_pagina(doc[0], 0)
    traducoes = {b.id: b.texto for b in blocos if not b.skip}
    paginas = {0: (blocos, traducoes)}
    geo = _geometria(doc, paginas)
    html = montar_html(doc, paginas, geo)
    assert "string-set: folio '42'" in html
    doc.close()


def test_abre_pagina_primeiro_bloco_perto_do_topo_e_true():
    from atlas.traducao.editorial_html import _abre_pagina

    class Titulo:
        bbox = (72.0, 70.0, 300.0, 90.0)
        texto = "Capítulo 1"
        skip = False

    class Corpo:
        bbox = (72.0, 200.0, 500.0, 400.0)
        texto = "Parágrafo qualquer bem no meio da página, bem longo mesmo."
        skip = False

    blocos = [Titulo(), Corpo()]
    assert _abre_pagina(Titulo(), blocos, ph=792.0) is True
    assert _abre_pagina(Corpo(), blocos, ph=792.0) is False


def test_montar_html_forca_quebra_quando_h1_sempre_abre_pagina(tmp_path):
    import fitz
    from atlas.traducao.editorial_html import _geometria, montar_html
    from atlas.traducao.extracao import extrair_pagina

    doc = fitz.open()
    for titulo in ("Capítulo Um", "Capítulo Dois", "Capítulo Três"):
        page = doc.new_page()
        page.insert_text((72, 70), titulo, fontname="helv", fontsize=24)  # heading grande
        page.insert_text((72, 150), "Parágrafo de corpo normal desta página.", fontname="helv", fontsize=11)
    p = tmp_path / "s.pdf"
    doc.save(str(p))
    doc.close()

    doc = fitz.open(str(p))
    paginas = {}
    for i in range(doc.page_count):
        blocos = extrair_pagina(doc[i], i)
        traducoes = {b.id: b.texto for b in blocos if not b.skip}
        paginas[i] = (blocos, traducoes)
    geo = _geometria(doc, paginas)
    html = montar_html(doc, paginas, geo)
    assert "break-before: page" in html  # aplicado no h1 (título sempre abre página)
    doc.close()
