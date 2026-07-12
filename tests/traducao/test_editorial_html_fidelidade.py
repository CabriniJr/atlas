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


def test_elemento_rotulo_capitulo_forca_break_before_no_proprio_rotulo():
    """Achado real (auditoria visual, Observability Engineering): o RÓTULO
    ("CHAPTER N"/"PART N") ficava órfão sozinho no fim da página anterior
    enquanto o título pulava pra próxima. ``break-after:avoid`` no rótulo NÃO
    resolve — testado empiricamente que o WeasyPrint não puxa um elemento
    anterior pra frente através do break-before:always de outro; a única
    forma confiável é forçar a quebra no PRÓPRIO rótulo."""
    b = _bloco("CHAPTER 2", size=16.8)
    b.papel = "rotulo_capitulo"
    from atlas.traducao.editorial_html import _estilo

    est = _estilo(b)
    html = _elemento(b, "CAPÍTULO 2", est, body_sz=10.5, clusters=[])
    assert "break-before:always" in html


def test_elemento_apos_rotulo_suprime_o_proprio_break_before():
    """O título logo após o rótulo não pode ter SEU PRÓPRIO break-before de
    nível de heading — o rótulo já abriu a página; um segundo break deixaria
    o rótulo sozinho na página anterior de novo."""
    b = _bloco("O que é observabilidade?", size=25.2)
    from atlas.traducao.editorial_html import _estilo

    est = _estilo(b)
    html = _elemento(
        b, "O que é observabilidade?", est, body_sz=10.5, clusters=[25.2], apos_rotulo=True
    )
    assert "break-before:avoid" in html


def test_elemento_link_goto_nao_ganha_classe_ext_nem_sublinhado():
    """Achado real (auditoria visual, Kubernetes in Action): o sumário
    inteiro (e referências cruzadas em prosa, "Chapter N") saía sublinhado
    feito link de navegador — o original NUNCA sublinha referência cruzada
    interna, só uma URL externa de verdade se comporta assim."""
    from atlas.traducao.editorial_html import _estilo

    b = _bloco("Texto qualquer")
    est = _estilo(b)
    html = _elemento(b, "Texto qualquer", est, body_sz=11.0, clusters=[], link=("goto", "cap1"))
    assert 'class="ext"' not in html
    assert 'href="#cap1"' in html


def test_elemento_link_uri_ganha_classe_ext():
    from atlas.traducao.editorial_html import _estilo

    b = _bloco("Texto qualquer")
    est = _estilo(b)
    html = _elemento(
        b, "Texto qualquer", est, body_sz=11.0, clusters=[], link=("uri", "https://example.com")
    )
    assert 'class="ext"' in html


def test_estilo_cor_por_maioria_nao_pelo_primeiro_span():
    """Achado real (auditoria visual, Observability Engineering): um link
    cruzado colorido curto ("Chapter 1") no INÍCIO de um parágrafo preto
    normal pintava o parágrafo INTEIRO da cor do link, porque _estilo() usava
    spans[0].color — o primeiro span, não o dominante."""
    from atlas.traducao.editorial_html import _estilo
    from atlas.traducao.extracao import BlocoTraducao, Span

    vermelho = 0xAA2222
    preto = 0
    spans = [
        Span(
            text="Chapter 1",
            bbox=(72, 100, 120, 116),
            font="Times",
            size=10.5,
            color=vermelho,
            flags=0,
        ),
        Span(
            text=" examines the roots of the term and provides concrete "
            "questions you can ask yourself about your system.",
            bbox=(120, 100, 400, 116),
            font="Times",
            size=10.5,
            color=preto,
            flags=0,
        ),
    ]
    b = BlocoTraducao(id=1, pagina=0, bbox=(72, 100, 400, 116), texto="", spans=spans)
    assert _estilo(b)["color"] == preto


def _bloco_multilinha(x0_linha1, x0_cont, y0=100.0, n_cont=3, size=10.0):
    """Bloco de prosa com 1ª linha em ``x0_linha1`` e linhas de continuação em
    ``x0_cont`` (spans agrupados por y)."""
    spans = [
        Span(
            text="P" * 40,
            bbox=(x0_linha1, y0, 400, y0 + 12),
            font="Times",
            size=size,
            color=0,
            flags=0,
        )
    ]
    for i in range(n_cont):
        yy = y0 + 14 * (i + 1)
        spans.append(
            Span(
                text="c" * 40,
                bbox=(x0_cont, yy, 400, yy + 12),
                font="Times",
                size=size,
                color=0,
                flags=0,
            )
        )
    texto = "P" * 40 + " " + "c" * 40 * n_cont
    return BlocoTraducao(id=1, pagina=0, bbox=(x0_cont, y0, 400, y0 + 60), texto=texto, spans=spans)


def test_documento_recua_paragrafo_estilo_tradicional():
    # Manning: 1ª linha recuada ~18pt em relação à continuação → estilo recuo.
    from atlas.traducao.editorial_html import _documento_recua_paragrafo

    paginas = {i: ([_bloco_multilinha(x0_linha1=90.0, x0_cont=72.0)], {}) for i in range(14)}
    assert _documento_recua_paragrafo(paginas, ph=792.0) is True


def test_documento_recua_paragrafo_estilo_bloco():
    # O'Reilly: 1ª linha alinhada à continuação (sem recuo) → estilo bloco.
    from atlas.traducao.editorial_html import _documento_recua_paragrafo

    paginas = {i: ([_bloco_multilinha(x0_linha1=72.0, x0_cont=72.0)], {}) for i in range(14)}
    assert _documento_recua_paragrafo(paginas, ph=792.0) is False


def test_documento_recua_paragrafo_amostra_pequena_e_bloco():
    # poucos parágrafos multi-linha → não decide por recuo (default bloco, seguro).
    from atlas.traducao.editorial_html import _documento_recua_paragrafo

    paginas = {0: ([_bloco_multilinha(x0_linha1=90.0, x0_cont=72.0)], {})}
    assert _documento_recua_paragrafo(paginas, ph=792.0) is False


def _bloco_xy(x0, x1, y0):
    from atlas.traducao.extracao import BlocoTraducao, Span

    sp = Span(text="w", bbox=(x0, y0, x1, y0 + 10), font="Times", size=10.0, color=0, flags=0)
    return BlocoTraducao(id=1, pagina=0, bbox=(x0, y0, x1, y0 + 10), texto="w", spans=[sp])


def test_limites_colunas_detecta_indice_multicoluna():
    """Índice de 3 colunas: 3 bandas x, cada uma com vários blocos atravessando
    a página → 2 fronteiras. Coluna única (prosa) → []."""
    from atlas.traducao.editorial_html import _limites_colunas

    pw, ph = 531.0, 666.0
    # 3 colunas (x0≈66/206/346), 6 blocos cada, atravessando a página inteira
    blocos = []
    for col_x0, col_x1 in [(66, 190), (206, 330), (346, 465)]:
        for k in range(6):
            blocos.append(_bloco_xy(col_x0, col_x1, 60 + k * 90))
    lim = _limites_colunas(blocos, pw, ph)
    assert len(lim) == 2
    assert 190 < lim[0] < 206 and 330 < lim[1] < 346


def test_limites_colunas_prosa_coluna_unica_vazio():
    from atlas.traducao.editorial_html import _limites_colunas

    blocos = [_bloco_xy(72, 460, 60 + k * 50) for k in range(10)]
    assert _limites_colunas(blocos, 531.0, 666.0) == []


def test_limites_colunas_ignora_callout_lateral_curto():
    """Listagem de código com callouts numa banda lateral CURTA (poucos blocos,
    pouca altura) não é confundida com coluna (falso-positivo real, K8S p203)."""
    from atlas.traducao.editorial_html import _limites_colunas

    blocos = [_bloco_xy(93, 465, 60 + k * 40) for k in range(10)]  # corpo largo
    blocos += [_bloco_xy(34, 76, 245 + k * 12) for k in range(4)]  # callout curto lateral
    assert _limites_colunas(blocos, 531.0, 666.0) == []


def test_coluna_de_mapeia_x_na_banda():
    from atlas.traducao.editorial_html import _coluna_de

    lim = [200.0, 340.0]
    assert _coluna_de(100.0, lim) == 0
    assert _coluna_de(250.0, lim) == 1
    assert _coluna_de(400.0, lim) == 2
    assert _coluna_de(150.0, []) == 0


def test_termina_aberto_detecta_frase_cortada():
    from atlas.traducao.editorial_html import _termina_aberto

    assert _termina_aberto("...recover above its target threshold. This") is True
    assert _termina_aberto("...limiar-alvo. Esse") is True
    assert _termina_aberto("Um parágrafo que termina bem.") is False
    assert _termina_aberto('Ele disse "pronto."') is False  # pontuação sob aspas
    assert _termina_aberto("Uma pergunta?") is False


def test_limpar_espaco_pontuacao_remove_espaco_espurio():
    """Achado real (auditoria visual, Observability Engineering): o join de spans
    injetava espaço espúrio ("( www , docs , support )") — em pt-BR nunca há
    espaço antes de vírgula/fecha-parêntese."""
    from atlas.traducao.editorial_html import _limpar_espaco_pontuacao

    assert _limpar_espaco_pontuacao("( www , docs , support )") == "(www, docs, support)"
    assert _limpar_espaco_pontuacao("uma lista [ a , b ]") == "uma lista [a, b]"
    # NÃO mexe em ! ? : (arriscado: identificadores, saída de código)
    assert _limpar_espaco_pontuacao("em torno de !env") == "em torno de !env"
    assert _limpar_espaco_pontuacao("6380 16504 ?   Sl") == "6380 16504 ?   Sl"
    # texto normal intacto
    assert _limpar_espaco_pontuacao("Uma frase (normal) aqui.") == "Uma frase (normal) aqui."


def test_e_paragrafo_prosa_distingue_de_toc_e_heading():
    from atlas.traducao.editorial_html import _e_paragrafo_prosa

    assert _e_paragrafo_prosa('<p id="u1_2" style="x">texto</p>') is True
    assert _e_paragrafo_prosa('<p class="toc-lin">x</p>') is False
    assert _e_paragrafo_prosa("<h2>Título</h2>") is False
    assert _e_paragrafo_prosa("<li>item</li>") is False


def test_montar_html_gruda_paragrafo_cortado_na_virada_de_pagina():
    """Achado real (auditoria visual, Observability Engineering): um parágrafo
    que atravessa a quebra de página do original vira 2 blocos (1 por página) e
    saía como 2 <p>, com a última palavra ("This"/"Esse") órfã no fim da página
    e a frase cortada. Gruda num <p> só quando o anterior termina aberto e este
    começa em minúscula."""
    import fitz

    from atlas.traducao.editorial_html import _geometria, montar_html
    from atlas.traducao.extracao import BlocoTraducao, Span

    doc = fitz.open()
    doc.new_page()
    doc.new_page()

    def _bloco_p(pid, pagina, texto, y0):
        sp = Span(
            text=texto, bbox=(72, y0, 400, y0 + 12), font="Times", size=10.0, color=0, flags=0
        )
        return BlocoTraducao(
            id=pid, pagina=pagina, bbox=(72, y0, 400, y0 + 12), texto=texto, spans=[sp]
        )

    p0 = [
        _bloco_p(0, 0, "Um parágrafo anterior que termina normalmente.", 100),
        _bloco_p(1, 0, "O SLO começou a se recuperar acima do limiar-alvo. Esse", 200),
    ]
    p1 = [_bloco_p(0, 1, "provavelmente ocorre porque houve uma grande queda.", 100)]
    paginas = {0: (p0, {b.id: b.texto for b in p0}), 1: (p1, {b.id: b.texto for b in p1})}
    geo = _geometria(doc, paginas)
    html = montar_html(doc, paginas, geo)
    assert "limiar-alvo. Esse provavelmente ocorre" in html  # grudado num <p> só
    assert "Esse</p>" not in html  # não ficou órfão no fim de um <p>
    doc.close()


def test_e_paragrafo_prosa_nao_confunde_pre_de_codigo():
    """``<pre>`` (código) começa com ``<p`` como um ``<p>`` de prosa — mas NÃO é
    parágrafo. Sem distinguir, a heurística de "grudar parágrafo cortado" (virada
    de página) trata o bloco de código como prosa e o funde no ``<p>`` anterior,
    perdendo o ``<pre>`` (quebras/indentação viram texto corrido) e herdando a cor
    da legenda — o código some (achado real, Kubernetes in Action pág. 198)."""
    from atlas.traducao.editorial_html import _e_paragrafo_prosa

    assert _e_paragrafo_prosa("<pre>env:\n- name: FIRST_VAR</pre>") is False
    assert _e_paragrafo_prosa('<pre id="u3_3">env:</pre>') is False


def test_montar_html_nao_funde_codigo_pre_na_legenda_anterior():
    """Legenda de listagem ("Listagem 7.7 …") termina aberta (sem ponto final) e
    o código logo abaixo começa em minúscula ("env:") — sem tratar ``<pre>`` à
    parte, o merge de "parágrafo cortado" fundia o código no ``<p>`` da legenda:
    o ``<pre>`` sumia, o código virava texto corrido com a cor branca da legenda
    (invisível) e sobrava um ``</`` malformado (achado real, Kubernetes in Action
    pág. 198: "está sem os códigos")."""
    import fitz

    from atlas.traducao.editorial_html import _geometria, montar_html
    from atlas.traducao.extracao import BlocoTraducao, Span

    doc = fitz.open()
    doc.new_page()

    legenda_sp = Span(
        text="Listagem 7.7 Referindo-se a uma variável de ambiente dentro de outra",
        bbox=(72, 200, 460, 212),
        font="FranklinGothic-Demi",
        size=9.0,
        color=0xFFFFFF,  # legenda Manning: texto branco sobre a barra colorida
        flags=1 << 4,
    )
    legenda = BlocoTraducao(
        id=12,
        pagina=0,
        bbox=legenda_sp.bbox,
        texto=legenda_sp.text,
        spans=[legenda_sp],
    )
    codigo_txt = 'env:\n- name: FIRST_VAR\n  value: "foo"\n- name: SECOND_VAR'
    codigo_sp = Span(
        text=codigo_txt, bbox=(72, 214, 460, 260), font="Courier", size=9.0, color=0, flags=0
    )
    codigo = BlocoTraducao(
        id=3,
        pagina=0,
        bbox=codigo_sp.bbox,
        texto=codigo_txt,
        spans=[codigo_sp],
        skip=True,
        papel="imutavel",
    )
    blocos = [legenda, codigo]
    paginas = {0: (blocos, {legenda.id: legenda.texto})}
    geo = _geometria(doc, paginas)
    html = montar_html(doc, paginas, geo)

    assert "<pre" in html  # o código sai como bloco de código próprio
    assert "env:\n- name: FIRST_VAR" in html  # quebras de linha preservadas
    assert "</</p>" not in html  # sem tag malformada
    # o código NÃO ficou dentro do <p> branco da legenda (senão seria invisível):
    # a legenda fecha o próprio <p> ANTES do <pre> começar.
    assert "</p>" in html[: html.index("<pre")]
    assert "env:" not in html[: html.index("<pre")]  # nenhum código antes do <pre>
    doc.close()


def test_cor_clara_detecta_texto_ilegivel_em_fundo_branco():
    from atlas.traducao.editorial_html import _cor_clara

    assert _cor_clara(0xFFFFFF) is True  # branco
    assert _cor_clara(0xF2F2F2) is True  # cinza claríssimo
    assert _cor_clara(0x000000) is False  # preto
    assert _cor_clara(0x4472C4) is False  # azul de link — legível no branco


def test_montar_html_reproduz_barra_colorida_da_legenda():
    """Legenda de listagem Manning é texto BRANCO sobre uma faixa azul. Sem
    reproduzir a faixa, o texto claro fica invisível no fundo branco do render
    (achado real, Kubernetes in Action). Detecta o retângulo preenchido atrás do
    bloco de texto claro e o reproduz como ``background`` do elemento."""
    import fitz

    from atlas.traducao.editorial_html import _geometria, montar_html
    from atlas.traducao.extracao import BlocoTraducao, Span

    doc = fitz.open()
    page = doc.new_page()
    # barra azul (fill) atrás da legenda, cobrindo a largura da coluna.
    page.draw_rect(fitz.Rect(72, 198, 460, 214), fill=(0.44, 0.65, 0.80), color=None)
    sp = Span(
        text="Listagem 7.7 Referindo-se a uma variável de ambiente dentro de outra",
        bbox=(80, 200, 452, 212),
        font="FranklinGothic-Demi",
        size=9.0,
        color=0xFFFFFF,
        flags=1 << 4,
    )
    legenda = BlocoTraducao(id=0, pagina=0, bbox=sp.bbox, texto=sp.text, spans=[sp])
    paginas = {0: ([legenda], {0: legenda.texto})}
    geo = _geometria(doc, paginas)
    html = montar_html(doc, paginas, geo)

    assert "background:#" in html  # a faixa foi reproduzida
    assert "color:#ffffff" in html  # texto claro preservado (agora sobre a faixa)
    doc.close()


def test_montar_html_remapeia_texto_claro_sem_barra_para_legivel():
    """Texto claro SEM uma faixa colorida atrás (nada a reproduzir) nunca pode
    sair branco em fundo branco — é remapeado pra cor legível."""
    import fitz

    from atlas.traducao.editorial_html import _geometria, montar_html
    from atlas.traducao.extracao import BlocoTraducao, Span

    doc = fitz.open()
    doc.new_page()
    sp = Span(
        text="Um rótulo que por acaso ficou branco sem barra atrás dele.",
        bbox=(80, 200, 452, 212),
        font="Times",
        size=10.0,
        color=0xFFFFFF,
        flags=0,
    )
    b = BlocoTraducao(id=0, pagina=0, bbox=sp.bbox, texto=sp.text, spans=[sp])
    paginas = {0: ([b], {0: b.texto})}
    geo = _geometria(doc, paginas)
    html = montar_html(doc, paginas, geo)

    assert "color:#ffffff" not in html  # não ficou branco/invisível
    doc.close()


def test_montar_html_nao_gruda_paragrafos_distintos():
    """Não pode grudar quando o anterior TERMINA a frase e o próximo começa em
    maiúscula (parágrafos de verdade, separados)."""
    import fitz

    from atlas.traducao.editorial_html import _geometria, montar_html
    from atlas.traducao.extracao import BlocoTraducao, Span

    doc = fitz.open()
    doc.new_page()
    doc.new_page()

    def _bloco_p(pid, pagina, texto, y0):
        sp = Span(
            text=texto, bbox=(72, y0, 400, y0 + 12), font="Times", size=10.0, color=0, flags=0
        )
        return BlocoTraducao(
            id=pid, pagina=pagina, bbox=(72, y0, 400, y0 + 12), texto=texto, spans=[sp]
        )

    p0 = [_bloco_p(0, 0, "Este parágrafo termina com ponto final.", 200)]
    p1 = [_bloco_p(0, 1, "Este é um novo parágrafo que começa em maiúscula.", 100)]
    paginas = {0: (p0, {b.id: b.texto for b in p0}), 1: (p1, {b.id: b.texto for b in p1})}
    geo = _geometria(doc, paginas)
    html = montar_html(doc, paginas, geo)
    assert html.count("<p ") >= 2  # continuam 2 parágrafos separados
    doc.close()


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


def test_render_toc_bloco_converte_enfase_no_titulo():
    """Achado real (auditoria visual, Kubernetes in Action): o numeral do
    capítulo é itálico no original ("*1* Introducing Kubernetes") — a
    extração marca isso como "_1_ Apresentando o Kubernetes", mas o render do
    sumário não convertia o marcador, vazando "_1_" literal em vez de "1"
    itálico."""
    from atlas.traducao.editorial_html import _render_toc_bloco

    html = _render_toc_bloco(
        "_1_ Apresentando o Kubernetes 34", nivel=0, anchors=[], est={"italic": False}
    )
    assert "<i>1</i>" in html
    assert "_1_" not in html


def test_render_toc_bloco_indenta_por_nivel():
    from atlas.traducao.editorial_html import _render_toc_bloco

    h0 = _render_toc_bloco("1.1 Understanding 2", nivel=0, anchors=[], est={})
    h2 = _render_toc_bloco("1.1 Understanding 2", nivel=2, anchors=[], est={})
    assert "margin-left:0.0em" in h0
    assert "margin-left:3.0em" in h2


def test_render_toc_bloco_sub_lista_italica_fica_inline_com_bullets():
    """Sub-lista de seções (itálico) fica compacta e inline (• separando), como
    no original — não explode numa lista pontilhada."""
    from atlas.traducao.editorial_html import _render_toc_bloco

    html = _render_toc_bloco(
        "Moving from monolithic apps 3 Providing a consistent environment 6",
        nivel=2,
        anchors=[],
        est={"italic": True},
    )
    assert html.count("<p") == 1  # UMA linha, não várias
    assert "toc-sep" in html  # bullet separador
    assert "toc-sub" in html


def test_render_toc_bloco_cabecalho_de_parte_versalete():
    from atlas.traducao.editorial_html import _render_toc_bloco

    html = _render_toc_bloco("Part I. The Path to Observability", nivel=0, anchors=[], est={})
    assert "toc-parte" in html


def test_e_entrada_toc_nao_confunde_reticencias_de_prosa():
    """Leader de sumário real tem dezenas de pontos — reticências ("...") de
    prosa comum NÃO podem ser confundidas com entrada de sumário (senão um
    parágrafo com reticências viraria uma linha de TOC)."""
    from atlas.traducao.editorial_html import _e_entrada_toc

    class _B:
        bbox = (72, 100, 400, 116)

    assert _e_entrada_toc(_B(), [], "Bem... na verdade isso é só uma frase normal.") is False
    assert _e_entrada_toc(_B(), [], "Foreword. . . . . . . . . . . . xi") is True


def test_parece_sumario_mesclado_reconhece_toc_de_verdade():
    from atlas.traducao.editorial_html import _parece_sumario_mesclado

    texto = "Introducing Kubernetes 1 First Steps with Docker 25 Pods 55"
    assert _parece_sumario_mesclado(texto) is True


def test_parece_sumario_mesclado_rejeita_paragrafo_com_referencias_cruzadas():
    """Achado real (auditoria visual, Observability Engineering): um
    parágrafo comum ("Chapter 2 looks at the practices... in Part II.") tem
    2 links internos (Chapter 2, Part II) mas NÃO é um sumário — "2" de
    "Chapter 2" virava um número de página fake, e o parágrafo inteiro saía
    com estilo de sumário/link sublinhado."""
    from atlas.traducao.editorial_html import _parece_sumario_mesclado

    texto = (
        "Chapter 2 looks at the practices engineers use to triage and locate "
        "sources of issues using traditional monitoring methods. Those methods "
        "are then contrasted with methods used in observability-based systems. "
        "This chapter describes these methods at a high level, but the "
        "technical and workflow implementations will become more concrete in "
        "Part II."
    )
    assert _parece_sumario_mesclado(texto) is False


def test_parece_sumario_mesclado_rejeita_menos_de_2_entradas():
    from atlas.traducao.editorial_html import _parece_sumario_mesclado

    assert _parece_sumario_mesclado("Um parágrafo qualquer sem número nenhum aqui.") is False


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


def test_abre_pagina_reconhece_titulo_precedido_do_proprio_rotulo():
    """Achado real (auditoria visual, Observability Engineering): "CHAPTER
    N"/"PART N" fica numa LINHA PRÓPRIA, acima do título (bloco próprio depois
    do split de _dividir_por_rotulo_capitulo) — o rótulo, não o título, é o
    bloco literalmente mais perto do topo. ``_abre_pagina`` só reconhecia o
    bloco EXATAMENTE mais próximo do topo como "abre página": o título nunca
    contava, e taxa_abre_pagina concluía (0% de abertura) que esse nível de
    heading não deveria forçar quebra de página — capítulos passavam a fluir
    no meio da página anterior em vez de abrir uma nova (ADR-0041 fix)."""
    from atlas.traducao.editorial_html import _abre_pagina

    class Rotulo:
        bbox = (372.8, 75.8, 432.0, 96.0)
        texto = "CHAPTER 1"
        skip = False

    class Titulo:
        bbox = (248.1, 97.8, 432.0, 128.0)
        texto = "What Is Observability?"
        skip = False

    class CorpoDistante:
        bbox = (72.0, 300.0, 432.0, 400.0)
        texto = "Parágrafo qualquer bem mais abaixo na página, bem longo mesmo."
        skip = False

    blocos = [Rotulo(), Titulo(), CorpoDistante()]
    assert _abre_pagina(Titulo(), blocos, ph=792.0) is True
    assert _abre_pagina(CorpoDistante(), blocos, ph=792.0) is False


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


def test_regioes_destaque_ignora_fundo_espurio_fora_da_pagina(tmp_path):
    """Achado real ao auditar Learning OpenTelemetry: o PDF recomprimido
    (``_compress``) tem UM retângulo preenchido gigante por página — ~468x11250pt
    começando em y=-5760 (14 páginas de altura, origem muito acima do topo) — um
    fundo de coluna/documento espúrio do compressor, NÃO um callout. Sem guard,
    ``_regioes_destaque`` o trata como caixa e embrulha TODA a página (prosa
    normal inclusa) num ``.destaque`` cinza. Uma caixa de destaque real cabe
    dentro da página; um fill que extravasa os limites é artefato e deve ser
    ignorado."""
    import fitz

    from atlas.traducao.editorial_html import _regioes_destaque
    from atlas.traducao.extracao import extrair_pagina

    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    # fundo espúrio: preenchido, largo, mas extravasando muito acima/abaixo da página.
    page.draw_rect(fitz.Rect(72, -5760, 540, 5490), color=None, fill=(0.95, 0.95, 0.95), width=0)
    page.insert_text(
        (80, 200),
        "Paragrafo comum de corpo que por acaso cai sobre o fundo espurio gigante.",
        fontname="helv",
        fontsize=11,
    )
    p = tmp_path / "s.pdf"
    doc.save(str(p))
    doc.close()

    doc = fitz.open(str(p))
    blocos = extrair_pagina(doc[0], 0)
    regioes = _regioes_destaque(doc[0], blocos, ids_diagrama=set())
    assert regioes == []
    doc.close()


def test_montar_html_nao_infla_imagem_pequena(tmp_path):
    """Achado real ao auditar Learning OpenTelemetry: um ícone/decoração de 9x9pt
    era INFLADO pelo piso de 15% da largura de figura, virando um borrão gigante
    no meio do texto. Imagem pequena deve sair no tamanho real (pt), preservada
    (nunca perde conteúdo, ADR-0031), mas sem estourar."""
    import fitz

    from atlas.traducao.editorial_html import _geometria, montar_html
    from atlas.traducao.extracao import extrair_pagina

    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text(
        (72, 120), "Paragrafo de corpo antes do icone decorativo.", fontname="helv", fontsize=11
    )
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 9, 9))
    pix.set_rect(pix.irect, (10, 20, 30))
    page.insert_image(fitz.Rect(300, 130, 309, 139), pixmap=pix)  # 9x9pt
    p = tmp_path / "s.pdf"
    doc.save(str(p))
    doc.close()

    doc = fitz.open(str(p))
    blocos = extrair_pagina(doc[0], 0)
    render_paginas = {0: (blocos, {b.id: b.texto for b in blocos if not b.skip})}
    html = montar_html(doc, render_paginas, _geometria(doc, render_paginas))
    doc.close()
    # a imagem é preservada (figura presente) mas NÃO inflada a 15%.
    assert "<figure><img" in html
    assert "width:15%" not in html
    assert "width:9pt" in html


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
