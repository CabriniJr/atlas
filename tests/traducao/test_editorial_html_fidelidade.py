import fitz

from atlas.traducao.editorial_html import _elemento
from atlas.traducao.extracao import BlocoTraducao, Span


def _bloco(texto, size=11.0, bold=False, italic=False, font="Times"):
    span = Span(
        text=texto,
        bbox=(72, 100, 400, 116),
        font=font,
        size=size,
        color=0,
        flags=(1 << 4 if bold else 0) | (1 << 1 if italic else 0),
    )
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


def test_e_rodape_nativo_nao_confunde_paragrafo_normal_no_fim_da_pagina():
    """Achado real (auditoria visual, Observability Engineering): o último
    parágrafo de uma seção às vezes cai na faixa inferior da página (ainda mais
    fácil na tradução, que cresce e empurra o texto pra baixo) — mas é prosa
    normal, MESMO tamanho de fonte do corpo, não uma nota de rodapé de verdade.
    Nota real é tipograficamente menor que o corpo (ex.: 8pt vs. 10.5pt no
    Observability Engineering) — esse é o sinal que faltava."""
    from atlas.traducao.editorial_html import _e_rodape_nativo
    from atlas.traducao.extracao import BlocoTraducao, Span

    def _bloco_bottom(texto, size):
        span = Span(text=texto, bbox=(72, 600, 400, 616), font="Times", size=size, color=0, flags=0)
        return BlocoTraducao(
            id=1, pagina=0, bbox=(72.0, 600.0, 400.0, 616.0), texto=texto, spans=[span]
        )

    ultimo_paragrafo = _bloco_bottom(
        "Este livro busca apresentar as diversas considerações associadas.", size=10.5
    )
    nota_de_verdade = _bloco_bottom("1. Uma nota explicativa de verdade aqui.", size=8.0)

    assert _e_rodape_nativo(ultimo_paragrafo, ph=842.0, body_sz=10.5) is False
    assert _e_rodape_nativo(nota_de_verdade, ph=842.0, body_sz=10.5) is True
    # sem body_sz (chamador não informou) preserva a heurística antiga — nunca
    # regride quem já usa a função sem esse argumento.
    assert _e_rodape_nativo(ultimo_paragrafo, ph=842.0) is True


def test_montar_html_renderiza_nota_de_rodape_nativa(tmp_path):
    import fitz

    from atlas.traducao.editorial_html import _geometria, montar_html
    from atlas.traducao.extracao import extrair_pagina

    doc = fitz.open()
    page = doc.new_page()  # altura default ~792pt
    page.insert_text((72, 100), "Corpo do texto principal da página.", fontname="helv", fontsize=12)
    page.insert_text(
        (72, 760), "1. Nota explicativa ao pé da página aqui.", fontname="helv", fontsize=8
    )
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


def test_montar_html_converte_enfase_dentro_de_nota_de_rodape(tmp_path):
    import fitz

    from atlas.traducao.editorial_html import _geometria, montar_html
    from atlas.traducao.extracao import extrair_pagina

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Corpo do texto principal da página.", fontname="helv", fontsize=12)
    page.insert_text(
        (72, 760), "1. Nota com termo **importante** aqui embaixo.", fontname="helv", fontsize=8
    )
    p = tmp_path / "s.pdf"
    doc.save(str(p))
    doc.close()

    doc = fitz.open(str(p))
    blocos = extrair_pagina(doc[0], 0)
    traducoes = {b.id: b.texto for b in blocos if not b.skip}
    paginas = {0: (blocos, traducoes)}
    geo = _geometria(doc, paginas)
    html = montar_html(doc, paginas, geo)
    assert "<b>importante</b>" in html
    assert "**importante**" not in html
    doc.close()


def test_glue_continuacao_de_item_de_lista_quebrado_em_2_blocos(tmp_path):
    """Achado real (auditoria visual, Kubernetes in Action): alguns PDFs criam
    um bloco PRÓPRIO do PyMuPDF pra 2ª linha+ de um item de bullet com hanging
    indent (sem marcador de bullet nessa 2ª linha) — sem grudar, ela vira um
    <p> solto, sem indentação/bullet, cortando a frase da lista ao meio."""
    import fitz

    from atlas.traducao.editorial_html import _geometria, montar_html
    from atlas.traducao.extracao import BlocoTraducao, Span

    doc = fitz.open()
    doc.new_page()
    p = tmp_path / "s.pdf"
    doc.save(str(p))
    doc.close()
    doc = fitz.open(str(p))

    def _bloco(id_, texto, x0, y0, y1, x1=470.0):
        span = Span(text=texto, bbox=(x0, y0, x1, y1), font="Times", size=11.0, color=0, flags=0)
        return BlocoTraducao(id=id_, pagina=0, bbox=(x0, y0, x1, y1), texto=texto, spans=[span])

    def _bloco_item_lista(id_, texto_apos_bullet, x0_bullet, x0_texto, y0, y1, x1=470.0):
        # 3 spans, igual à forma real do PDF: bullet, espaço, texto (ver
        # extração real do Kubernetes in Action) — não um span único mesclado.
        spans = [
            Span(
                text="•",
                bbox=(x0_bullet, y0, x0_bullet + 4, y1),
                font="Times",
                size=11.0,
                color=0,
                flags=0,
            ),
            Span(
                text=" ",
                bbox=(x0_bullet + 4, y0, x0_texto, y1),
                font="Times",
                size=11.0,
                color=0,
                flags=0,
            ),
            Span(
                text=texto_apos_bullet,
                bbox=(x0_texto, y0, x1, y1),
                font="Times",
                size=11.0,
                color=0,
                flags=0,
            ),
        ]
        texto = f"• {texto_apos_bullet}"
        return BlocoTraducao(
            id=id_, pagina=0, bbox=(x0_bullet, y0, x1, y1), texto=texto, spans=spans
        )

    # y bem no meio da página (longe das faixas de margem/fólio, _e_folio).
    item1 = _bloco_item_lista(
        1,
        "ReplicationControllers should be replaced with ReplicaSets,",
        117.78,
        129.78,
        353.5,
        363.5,
    )
    continuacao = _bloco(2, "which provide the same functionality.", 129.78, 366.5, 376.5)
    item2 = _bloco_item_lista(
        3, "ReplicationControllers schedule pods to random nodes.", 117.78, 129.78, 389.0, 399.0
    )

    blocos = [item1, continuacao, item2]
    traducoes = {
        1: "• Os ReplicationControllers devem ser substituídos por ReplicaSets,",
        2: "que fornecem a mesma funcionalidade.",
        3: "• ReplicationControllers agendam pods para nós aleatórios.",
    }
    paginas = {0: (blocos, traducoes)}
    geo = _geometria(doc, paginas)
    html = montar_html(doc, paginas, geo)
    assert html.count("<li") == 2
    assert (
        "Os ReplicationControllers devem ser substituídos por ReplicaSets, "
        "que fornecem a mesma funcionalidade.</li>"
    ) in html
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


def test_abre_pagina_reconhece_titulo_de_capitulo_com_espaco_decorativo_acima():
    """Achado real ao auditar Kubernetes in Action: TODOS os 18 títulos de
    capítulo do livro ficam a y0=120.6pt (frac=0.181 de ph=666pt) — um pouco
    abaixo do limiar antigo de 0.18 (espaço reservado pro numeral decorativo
    "fantasma" do capítulo, acima do título). Isso fazia ``_abre_pagina``
    devolver ``False`` para TODAS as ocorrências, e o motor concluía (taxa de
    abertura baixa) que esse nível de heading não deveria forçar quebra de
    página — títulos de capítulo passavam a fluir no meio da página anterior
    em vez de abrir uma nova (ADR-0041 fix)."""
    from atlas.traducao.editorial_html import _abre_pagina

    class TituloCapitulo:
        bbox = (201.78, 120.6, 474.2, 150.6)
        texto = "Introducing Kubernetes"
        skip = False

    blocos = [TituloCapitulo()]
    assert _abre_pagina(TituloCapitulo(), blocos, ph=666.0) is True


def test_montar_html_forca_quebra_quando_h1_sempre_abre_pagina(tmp_path):
    import fitz

    from atlas.traducao.editorial_html import _geometria, montar_html
    from atlas.traducao.extracao import extrair_pagina

    doc = fitz.open()
    for titulo in ("Capítulo Um", "Capítulo Dois", "Capítulo Três"):
        page = doc.new_page()
        page.insert_text((72, 70), titulo, fontname="helv", fontsize=24)  # heading grande
        page.insert_text(
            (72, 150), "Parágrafo de corpo normal desta página.", fontname="helv", fontsize=11
        )
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


def test_montar_html_gruda_titulo_de_capitulo_quebrado_em_duas_linhas(tmp_path):
    """Achado real ao auditar Kubernetes in Action: um título de capítulo
    quebrado em 2 linhas no PDF original (ex. "First steps with Docker" /
    "and Kubernetes", cada linha um bloco de texto próprio) virava 2
    elementos `<h1>` separados — a regra "esse nível sempre abre página"
    disparava em CADA um, deixando a 1ª linha sozinha numa página e
    empurrando a 2ª linha (o resto do título) pra próxima. Uma linha de
    heading adjacente ao MESMO nível (sem nada entre elas) agora gruda na
    anterior em vez de virar um `<h1>` novo (ADR-0041 fix)."""
    import fitz

    from atlas.traducao.editorial_html import _geometria, montar_html
    from atlas.traducao.extracao import extrair_pagina

    doc = fitz.open()
    for linha1, linha2 in (("Capítulo Um", "continuação"), ("Capítulo Dois", "continuação")):
        page = doc.new_page()
        page.insert_text((72, 70), linha1, fontname="helv", fontsize=24)
        page.insert_text((72, 100), linha2, fontname="helv", fontsize=24)
        page.insert_text(
            (72, 150), "Parágrafo de corpo normal desta página.", fontname="helv", fontsize=11
        )
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
    assert html.count("<h1") == 2  # 1 por página, não 1 por linha
    assert "Capítulo Um continuação" in html
    doc.close()


def test_montar_html_embute_font_face_real(tmp_path):
    from pathlib import Path

    import fitz

    from atlas.traducao.editorial_html import _geometria, montar_html
    from atlas.traducao.extracao import extrair_pagina

    fonte_path = str(
        Path(__file__).resolve().parents[2]
        / "src"
        / "atlas"
        / "traducao"
        / "fonts"
        / "LiberationSans-Regular.ttf"
    )
    doc = fitz.open()
    page = doc.new_page()
    page.insert_font(fontname="atlasteste", fontfile=fonte_path)
    page.insert_text((72, 100), "Texto com fonte embutida.", fontname="atlasteste", fontsize=12)
    p = tmp_path / "s.pdf"
    doc.save(str(p))
    doc.close()

    doc = fitz.open(str(p))
    blocos = extrair_pagina(doc[0], 0)
    traducoes = {b.id: b.texto for b in blocos if not b.skip}
    paginas = {0: (blocos, traducoes)}
    geo = _geometria(doc, paginas)
    html = montar_html(doc, paginas, geo)
    assert "@font-face" in html
    doc.close()


def test_css_nao_forca_cor_azul_no_link():
    from atlas.traducao.editorial_html import _CSS

    assert "#0645ad" not in _CSS


def test_regioes_diagrama_agrupa_desenho_vetorial_com_rotulos(tmp_path):
    import fitz

    from atlas.traducao.editorial_html import _regioes_diagrama
    from atlas.traducao.extracao import extrair_pagina

    doc = fitz.open()
    page = doc.new_page()
    # "diagrama": duas caixas DISTINTAS conectadas por uma linha, com rótulos
    # curtos dentro — >=1 subforma além do contêiner da região é o que
    # distingue de uma caixa de destaque simples (só 1 retângulo preenchido,
    # ADR-0041 fix real).
    page.draw_rect(fitz.Rect(72, 100, 130, 140), color=(0, 0, 0), fill=(0.9, 0.9, 0.9), width=0)
    page.draw_rect(fitz.Rect(140, 140, 200, 180), color=(0, 0, 0), fill=(0.9, 0.9, 0.9), width=0)
    page.draw_line((100, 140), (150, 140))
    page.insert_text((80, 120), "App A", fontname="helv", fontsize=9)
    page.insert_text((150, 160), "App B", fontname="helv", fontsize=9)
    # parágrafo comum, bem longe do diagrama — não deve entrar na região.
    page.insert_text(
        (72, 400), "Este é um parágrafo comum de texto na página.", fontname="helv", fontsize=11
    )
    p = tmp_path / "s.pdf"
    doc.save(str(p))
    doc.close()

    doc = fitz.open(str(p))
    blocos = extrair_pagina(doc[0], 0)
    regioes = _regioes_diagrama(doc[0], blocos)
    assert len(regioes) == 1
    regiao, contidos = regioes[0]
    textos_contidos = {b.texto for b in contidos}
    assert textos_contidos == {"App A", "App B"}
    doc.close()


def test_regioes_diagrama_ignora_tabela_com_grade_interna(tmp_path):
    """Achado real ao auditar Kubernetes in Action: uma tabela de referência
    (cabeçalho com fundo cinza + linhas de grade internas) virou uma imagem
    rasterizada em INGLÊS — a "forma cheia" do cabeçalho colorido passava no
    filtro de diagrama. Uma grade de linhas finas internas (bordas de
    linha/coluna) denuncia tabela, não diagrama."""
    import fitz

    from atlas.traducao.editorial_html import _regioes_diagrama
    from atlas.traducao.extracao import extrair_pagina

    doc = fitz.open()
    page = doc.new_page()
    # cabeçalho com fundo cinza (forma "cheia" >= 400 sq pt).
    page.draw_rect(fitz.Rect(60, 100, 460, 122), color=(0, 0, 0), fill=(0.9, 0.9, 0.9), width=0)
    # réguas internas finas (linhas de linha/coluna, com espessura real, como
    # PyMuPDF reporta em PDFs de verdade) — sinal de grade de tabela.
    page.draw_rect(fitz.Rect(60, 149.75, 460, 150.25), color=(0, 0, 0), fill=(0, 0, 0), width=0)
    page.draw_rect(fitz.Rect(199.75, 100, 200.25, 300), color=(0, 0, 0), fill=(0, 0, 0), width=0)
    page.insert_text((65, 115), "Header A", fontname="helv", fontsize=9)
    page.insert_text((205, 115), "Header B", fontname="helv", fontsize=9)
    page.insert_text((65, 140), "Row 1 A", fontname="helv", fontsize=9)
    page.insert_text((205, 140), "Row 1 B", fontname="helv", fontsize=9)
    p = tmp_path / "s.pdf"
    doc.save(str(p))
    doc.close()

    doc = fitz.open(str(p))
    blocos = extrair_pagina(doc[0], 0)
    regioes = _regioes_diagrama(doc[0], blocos)
    assert regioes == []
    doc.close()


def test_regioes_diagrama_ignora_caixa_de_destaque_com_prosa(tmp_path):
    """Achado real ao auditar Prometheus Up & Running: uma caixa de destaque
    (título curto + parágrafo de prosa) tem >=2 blocos e uma forma cheia
    (fundo colorido) — passava no filtro de diagrama antes de chegar em
    ``_regioes_destaque`` (que exclui blocos já reclamados pelo diagrama),
    perdendo a tradução do parágrafo (rasterizado em inglês). Um bloco de
    prosa de verdade (frase longa) denuncia caixa de destaque, não diagrama."""
    import fitz

    from atlas.traducao.editorial_html import _regioes_diagrama
    from atlas.traducao.extracao import extrair_pagina

    doc = fitz.open()
    page = doc.new_page()
    page.draw_rect(fitz.Rect(72, 100, 460, 200), color=(0, 0, 0), fill=(0.95, 0.95, 0.95), width=0)
    page.insert_text((80, 120), "TIP", fontname="helv", fontsize=10)
    page.insert_text(
        (80, 140),
        "This is a long paragraph of real prose text that explains something "
        "in detail across many words, not a short diagram label.",
        fontname="helv",
        fontsize=9,
    )
    p = tmp_path / "s.pdf"
    doc.save(str(p))
    doc.close()

    doc = fitz.open(str(p))
    blocos = extrair_pagina(doc[0], 0)
    regioes = _regioes_diagrama(doc[0], blocos)
    assert regioes == []
    doc.close()


def test_regioes_diagrama_ignora_caixa_unica_com_lista_de_topicos(tmp_path):
    """Achado real ao auditar Kubernetes in Action: o quadro de abertura de
    capítulo "This chapter covers" (título + itens de lista, cada um curto —
    não passa no filtro de prosa longa) é desenhado como UM único retângulo
    preenchido, sem nenhuma subforma — mas tinha >=2 blocos e uma "forma
    cheia", passando no filtro de diagrama e virando uma imagem rasterizada em
    INGLÊS. Uma subforma distinta do próprio contêiner da região (>=2 caixas,
    como um diagrama de verdade) agora é exigida (ADR-0041 fix)."""
    import fitz

    from atlas.traducao.editorial_html import _regioes_diagrama
    from atlas.traducao.extracao import extrair_pagina

    doc = fitz.open()
    page = doc.new_page()
    page.draw_rect(fitz.Rect(72, 100, 330, 240), color=(0, 0, 0), fill=(0.97, 0.96, 0.91), width=0)
    page.insert_text((80, 120), "This chapter covers", fontname="helv", fontsize=11)
    page.insert_text((80, 140), "Understanding containers", fontname="helv", fontsize=9)
    page.insert_text((80, 155), "Isolating applications", fontname="helv", fontsize=9)
    page.insert_text((80, 170), "Making jobs easier", fontname="helv", fontsize=9)
    p = tmp_path / "s.pdf"
    doc.save(str(p))
    doc.close()

    doc = fitz.open(str(p))
    blocos = extrair_pagina(doc[0], 0)
    regioes = _regioes_diagrama(doc[0], blocos)
    assert regioes == []
    doc.close()


def test_renderizar_diagrama_gera_data_uri_png(tmp_path):
    import fitz

    from atlas.traducao.editorial_html import _renderizar_diagrama

    doc = fitz.open()
    page = doc.new_page()
    page.draw_rect(fitz.Rect(72, 100, 200, 140), color=(0, 0, 0), width=1)
    p = tmp_path / "s.pdf"
    doc.save(str(p))
    doc.close()

    doc = fitz.open(str(p))
    uri = _renderizar_diagrama(doc[0], fitz.Rect(72, 100, 200, 140))
    assert uri.startswith("data:image/png;base64,")
    doc.close()


def test_montar_html_rasteriza_diagrama_em_vez_de_paragrafos_soltos(tmp_path):
    import fitz

    from atlas.traducao.editorial_html import _geometria, montar_html
    from atlas.traducao.extracao import extrair_pagina

    doc = fitz.open()
    page = doc.new_page()
    page.draw_rect(fitz.Rect(72, 100, 130, 140), color=(0, 0, 0), fill=(0.9, 0.9, 0.9), width=0)
    page.draw_rect(fitz.Rect(140, 140, 200, 180), color=(0, 0, 0), fill=(0.9, 0.9, 0.9), width=0)
    page.draw_line((100, 140), (150, 140))
    page.insert_text((80, 120), "App A", fontname="helv", fontsize=9)
    page.insert_text((150, 160), "App B", fontname="helv", fontsize=9)
    page.insert_text(
        (72, 400), "Este é um parágrafo comum de texto na página.", fontname="helv", fontsize=11
    )
    p = tmp_path / "s.pdf"
    doc.save(str(p))
    doc.close()

    doc = fitz.open(str(p))
    blocos = extrair_pagina(doc[0], 0)
    traducoes = {b.id: b.texto for b in blocos if not b.skip}
    paginas = {0: (blocos, traducoes)}
    geo = _geometria(doc, paginas)
    html = montar_html(doc, paginas, geo)
    assert "<img" in html
    assert "App A" not in html  # rótulo do diagrama não vira <p> solto
    assert "App B" not in html
    assert "Este é um parágrafo comum" in html  # texto normal continua intacto
    doc.close()


def test_regioes_destaque_detecta_caixa_com_fundo_e_prosa(tmp_path):
    import fitz

    from atlas.traducao.editorial_html import _regioes_destaque
    from atlas.traducao.extracao import extrair_pagina

    doc = fitz.open()
    page = doc.new_page()
    page.draw_rect(fitz.Rect(72, 100, 450, 200), color=(0, 0, 0), fill=(0.92, 0.92, 0.92), width=1)
    page.insert_text((80, 120), "DICA", fontname="helv", fontsize=10)
    page.insert_text(
        (80, 140),
        "Este e um paragrafo de dica com bastante texto explicativo aqui.",
        fontname="helv",
        fontsize=9,
    )
    page.insert_text(
        (72, 400),
        "Paragrafo comum de corpo, bem longe da caixa de destaque.",
        fontname="helv",
        fontsize=11,
    )
    p = tmp_path / "s.pdf"
    doc.save(str(p))
    doc.close()

    doc = fitz.open(str(p))
    blocos = extrair_pagina(doc[0], 0)
    regioes = _regioes_destaque(doc[0], blocos, ids_diagrama=set())
    assert len(regioes) == 1
    _reg, contidos = regioes[0]
    textos = {b.texto for b in contidos}
    assert any("paragrafo de dica" in t.lower() for t in textos)
    assert not any("comum de corpo" in t.lower() for t in textos)
    doc.close()


def test_regioes_destaque_ignora_caixa_sem_preenchimento(tmp_path):
    import fitz

    from atlas.traducao.editorial_html import _regioes_destaque
    from atlas.traducao.extracao import extrair_pagina

    doc = fitz.open()
    page = doc.new_page()
    page.draw_rect(fitz.Rect(72, 100, 450, 200), color=(0, 0, 0), width=1)  # sem fill
    page.insert_text(
        (80, 140),
        "Este e um paragrafo qualquer com bastante texto aqui dentro.",
        fontname="helv",
        fontsize=9,
    )
    p = tmp_path / "s.pdf"
    doc.save(str(p))
    doc.close()

    doc = fitz.open(str(p))
    blocos = extrair_pagina(doc[0], 0)
    regioes = _regioes_destaque(doc[0], blocos, ids_diagrama=set())
    assert regioes == []
    doc.close()


def test_regioes_destaque_ignora_regua_fina_perto_de_fundo_decorativo(tmp_path):
    """Achado real ao auditar Kubernetes in Action: o fundo cinza decorativo
    do numeral "fantasma" de capítulo (ex. o grande "6" atrás do título) e a
    régua colorida fina sob o título de capítulo TÊM preenchimento — se
    juntam (por proximidade) numa única região que, por coincidência,
    também cobre o bloco do TÍTULO do capítulo, fazendo-o virar uma caixa
    de destaque (borda + fundo cinza) em vez do título estilizado normal.
    Réguas finas (uma dimensão <= 2pt) são excluídas do fundo de destaque —
    só uma forma robusta conta como fundo de caixa real (ADR-0041 fix)."""
    import fitz

    from atlas.traducao.editorial_html import _regioes_destaque
    from atlas.traducao.extracao import extrair_pagina

    doc = fitz.open()
    page = doc.new_page()
    # fundo decorativo do numeral "fantasma" (forma robusta e preenchida).
    page.draw_rect(fitz.Rect(394, 65, 506, 220), color=(0, 0, 0), fill=(0.9, 0.9, 0.9), width=0)
    # régua fina colorida logo abaixo do título — preenchida, mas fina.
    page.draw_rect(fitz.Rect(180, 185.5, 474, 186), color=(0, 0, 0), fill=(0.3, 0.4, 0.5), width=0)
    page.insert_text(
        (183, 150), "Volumes: attaching disk storage to containers", fontname="helv", fontsize=24
    )
    p = tmp_path / "s.pdf"
    doc.save(str(p))
    doc.close()

    doc = fitz.open(str(p))
    blocos = extrair_pagina(doc[0], 0)
    regioes = _regioes_destaque(doc[0], blocos, ids_diagrama=set())
    assert regioes == []
    doc.close()


def test_montar_html_envolve_caixa_de_destaque_em_div(tmp_path):
    import fitz

    from atlas.traducao.editorial_html import _geometria, montar_html
    from atlas.traducao.extracao import extrair_pagina

    doc = fitz.open()
    page = doc.new_page()
    page.draw_rect(fitz.Rect(72, 100, 450, 200), color=(0, 0, 0), fill=(0.92, 0.92, 0.92), width=1)
    page.insert_text(
        (80, 140),
        "Este e um paragrafo de dica com bastante texto explicativo aqui.",
        fontname="helv",
        fontsize=9,
    )
    page.insert_text(
        (72, 400),
        "Paragrafo comum de corpo, bem longe da caixa de destaque.",
        fontname="helv",
        fontsize=11,
    )
    p = tmp_path / "s.pdf"
    doc.save(str(p))
    doc.close()

    doc = fitz.open(str(p))
    blocos = extrair_pagina(doc[0], 0)
    traducoes = {b.id: b.texto for b in blocos if not b.skip}
    paginas = {0: (blocos, traducoes)}
    geo = _geometria(doc, paginas)
    html = montar_html(doc, paginas, geo)
    assert 'class="destaque"' in html
    assert "paragrafo de dica" in html.lower()
    assert "comum de corpo" in html.lower()
    doc.close()


def test_tipo_lista_reconhece_glifo_pua_de_fonte_icone():
    """Achado real ao auditar Kubernetes in Action: o quadro "This chapter
    covers" usa um glifo de fonte de ícone (Wingdings/Symbol, área de Uso
    Privado U+E000-U+F8FF) como marcador de bullet — não estava na lista de
    bullets Unicode comuns, então o item nunca virava ``<li>`` (ficava um
    ``<p>`` solto com o glifo cru, sem marcador visível, ADR-0041 fix)."""
    from atlas.traducao.editorial_html import _tipo_lista

    assert _tipo_lista(" Understanding how containers work") == "ul"


def test_montar_html_gruda_continuacao_de_item_de_lista_dentro_de_destaque(tmp_path):
    """Achado real ao auditar Kubernetes in Action: um item de lista quebrado
    em 2 linhas (cada linha um bloco de texto próprio no PDF) virava DOIS
    elementos — o primeiro um `<li>`, o segundo um `<p>` solto sem marcador
    nem indentação, cortando a frase ao meio visualmente. A linha de
    continuação (sem marcador de bullet, começando em minúscula) agora gruda
    no `<li>` anterior (ADR-0041 fix)."""
    import fitz

    from atlas.traducao.editorial_html import _geometria, montar_html
    from atlas.traducao.extracao import extrair_pagina

    doc = fitz.open()
    page = doc.new_page()
    page.draw_rect(fitz.Rect(72, 100, 330, 240), color=(0, 0, 0), fill=(0.97, 0.96, 0.91), width=0)
    page.insert_text((80, 120), "This chapter covers", fontname="helv", fontsize=11)
    page.insert_text(
        (80, 140), "- Understanding how software development", fontname="helv", fontsize=9
    )
    page.insert_text(
        (80, 155), "and deployment has changed over the years", fontname="helv", fontsize=9
    )
    page.insert_text((80, 175), "- Isolating applications", fontname="helv", fontsize=9)
    p = tmp_path / "s.pdf"
    doc.save(str(p))
    doc.close()

    doc = fitz.open(str(p))
    blocos = extrair_pagina(doc[0], 0)
    traducoes = {b.id: b.texto for b in blocos if not b.skip}
    paginas = {0: (blocos, traducoes)}
    geo = _geometria(doc, paginas)
    html = montar_html(doc, paginas, geo)
    assert html.count("<li") == 2
    assert (
        "Understanding how software development and deployment has changed over the years" in html
    )
    doc.close()


def test_link_do_bloco_ignora_url_que_cobre_so_uma_fracao_pequena():
    from atlas.traducao.editorial_html import _link_do_bloco
    from atlas.traducao.extracao import BlocoTraducao

    # parágrafo de 5 linhas; só a última linha (uma URL) tem link — não deve
    # fazer o PARÁGRAFO INTEIRO virar <a> (ADR-0041 fix).
    bloco = BlocoTraducao(id=1, pagina=0, bbox=(102.0, 148.0, 474.0, 210.0), texto="...")
    links = [(fitz.Rect(102.0, 198.0, 270.0, 210.0), "uri", "http://example.com/docs")]
    assert _link_do_bloco(bloco, links) is None


def test_link_do_bloco_aceita_link_que_cobre_a_maior_parte_do_bloco():
    from atlas.traducao.editorial_html import _link_do_bloco
    from atlas.traducao.extracao import BlocoTraducao

    # título/legenda de 1 linha cujo link cobre quase todo o bbox — deve
    # continuar funcionando (não regride o caso normal).
    bloco = BlocoTraducao(id=1, pagina=0, bbox=(100.0, 100.0, 300.0, 112.0), texto="Título")
    links = [(fitz.Rect(100.0, 100.0, 300.0, 112.0), "uri", "http://example.com")]
    assert _link_do_bloco(bloco, links) == ("uri", "http://example.com")


def test_injetar_string_set_em_elemento_com_style_existente():
    from atlas.traducao.editorial_html import _injetar_string_set

    el = '<p id="u1_2" style="font-size:11.0pt;">Texto aqui</p>'
    out = _injetar_string_set(el, "42")
    assert out == '<p id="u1_2" style="string-set: folio \'42\';font-size:11.0pt;">Texto aqui</p>'


def test_injetar_string_set_em_elemento_sem_style():
    from atlas.traducao.editorial_html import _injetar_string_set

    el = "<pre>codigo aqui</pre>"
    out = _injetar_string_set(el, "42")
    assert out == "<pre style=\"string-set: folio '42';\">codigo aqui</pre>"


def test_comeca_minuscula_detecta_continuacao():
    from atlas.traducao.editorial_html import _comeca_minuscula

    assert _comeca_minuscula("finally returns it in a response.") is True
    assert _comeca_minuscula("Finally returns it in a response.") is False
    assert _comeca_minuscula("“minúscula entre aspas") is True
    assert _comeca_minuscula("123 não tem letra antes") is True
    assert _comeca_minuscula("") is False


def test_montar_html_gruda_continuacao_de_nota_na_pagina_seguinte(tmp_path):
    import fitz

    from atlas.traducao.editorial_html import _geometria, montar_html
    from atlas.traducao.extracao import extrair_pagina

    doc = fitz.open()
    p0 = doc.new_page()  # altura default ~792pt
    p0.insert_text(
        (72, 100), "Corpo do texto principal da primeira página.", fontname="helv", fontsize=12
    )
    p0.insert_text(
        (72, 760),
        "1. Nota explicativa que estoura pra proxima pagina e",
        fontname="helv",
        fontsize=8,
    )
    p1 = doc.new_page()
    # continuação da nota: primeiro bloco da página, começa com minúscula,
    # longe da margem (não seria pego por _e_rodape_nativo sozinho).
    p1.insert_text(
        (72, 90), "continua aqui no topo da pagina seguinte.", fontname="helv", fontsize=8
    )
    p1.insert_text(
        (72, 150), "Parágrafo comum de corpo da segunda página.", fontname="helv", fontsize=12
    )
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
    assert html.count('class="rodape-nativo"') == 1  # uma nota só, não duas soltas
    assert "estoura pra proxima pagina e continua aqui no topo da pagina seguinte." in html
    assert "Parágrafo comum de corpo da segunda página." in html
    doc.close()


def test_regressao_nenhum_texto_e_perdido_no_render(tmp_path):
    import fitz

    from atlas.traducao.editorial_html import remontar_editorial_html
    from atlas.traducao.extracao import extrair_pagina

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (72, 100), "1. Primeiro item da lista numerada aqui.", fontname="helv", fontsize=11
    )
    page.insert_text(
        (72, 120), "2. Segundo item da lista numerada aqui.", fontname="helv", fontsize=11
    )
    page.insert_text(
        (72, 300),
        "Parágrafo comum de corpo bem no meio da página inteira.",
        fontname="helv",
        fontsize=11,
    )
    p = tmp_path / "s.pdf"
    doc.save(str(p))
    doc.close()

    doc = fitz.open(str(p))
    blocos = extrair_pagina(doc[0], 0)
    traducoes = {b.id: b.texto for b in blocos if not b.skip}  # simula tradução = original
    out = tmp_path / "out.pdf"
    remontar_editorial_html(doc, {0: (blocos, traducoes)}, str(out))

    out_doc = fitz.open(str(out))
    texto_final = "".join(out_doc[i].get_text() for i in range(out_doc.page_count))
    assert "Primeiro item" in texto_final
    assert "Segundo item" in texto_final
    assert "Parágrafo comum" in texto_final
    out_doc.close()
