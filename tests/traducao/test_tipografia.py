from dataclasses import dataclass

from atlas.traducao.tipografia import (
    agrupar_niveis,
    bloco_e_mono,
    clusters_titulo,
    converter_enfase,
    dividir_versalete,
    familia_fonte,
    fonte_seminegrito,
    nivel_indent,
    nivel_titulo,
    taxa_abre_pagina,
)


@dataclass
class _SpanFake:
    text: str
    font: str
    flags: int = 0


def _escapar(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def test_converte_negrito_no_meio_do_texto():
    out = converter_enfase("Isto é **muito** importante.", _escapar)
    assert out == "Isto é <b>muito</b> importante."


def test_converte_italico_no_meio_do_texto():
    out = converter_enfase("Veja _in situ_ aqui.", _escapar)
    assert out == "Veja <i>in situ</i> aqui."


def test_marcador_desbalanceado_fica_literal():
    out = converter_enfase("Preço: R$ 10 * 2 = 20", _escapar)
    assert out == "Preço: R$ 10 * 2 = 20"


def test_texto_sem_marcador_so_escapa():
    out = converter_enfase("<script>alert(1)</script>", _escapar)
    assert out == "&lt;script&gt;alert(1)&lt;/script&gt;"


def test_clusters_titulo_ate_3_niveis_do_maior_pro_menor():
    tamanhos = [11, 11, 11, 24, 24, 18, 18, 18, 14, 14, 11, 11]
    clusters = clusters_titulo(tamanhos, corpo_sz=11)
    assert clusters == [24.0, 18.0, 14.0]


def test_clusters_titulo_sem_heading_e_vazio():
    assert clusters_titulo([11, 11, 11], corpo_sz=11) == []


def test_clusters_titulo_ignora_tamanho_de_uma_ocorrencia_so():
    """Frequência-awareness (ADR-0041): um tamanho grande que aparece UMA vez
    (título de capa, rótulo de figura) é ruído, não um nível de heading. Sem o
    filtro, a capa (31.5pt, 1x) roubava a tier h1 e o cabeçalho de seção
    (18.9pt, muitas vezes) — o nível de conteúdo de verdade — era descartado."""
    # capa 31.5 (1x) + parte 28 (3x) + capítulo 25 (5x) + seção 18.9 (20x)
    tamanhos = [31.5] + [28.0] * 3 + [25.0] * 5 + [18.9] * 20
    clusters = clusters_titulo(tamanhos, corpo_sz=10.5)
    assert 31.5 not in clusters  # capa (1 ocorrência) não vira tier
    assert clusters == [28.0, 25.0, 18.9]  # parte/capítulo/seção


def test_clusters_titulo_max_niveis_configuravel():
    tamanhos = [28.0] * 3 + [25.0] * 3 + [20.0] * 3 + [16.0] * 3
    assert clusters_titulo(tamanhos, corpo_sz=10.5, max_niveis=4) == [28.0, 25.0, 20.0, 16.0]
    assert clusters_titulo(tamanhos, corpo_sz=10.5, max_niveis=2) == [28.0, 25.0]


def test_familia_fonte_classifica_serif_sans_mono():
    # corpo dos livros reais: serifada
    assert familia_fonte("MinionPro-Regular") == "serif"
    assert familia_fonte("NewBaskerville-Roman") == "serif"
    assert familia_fonte("Times-Roman") == "serif"
    # headings dos livros reais: sem serifa (O'Reilly Myriad, Manning Franklin)
    assert familia_fonte("MyriadPro-SemiboldCond") == "sans"
    assert familia_fonte("FranklinGothic-DemiItal") == "sans"
    assert familia_fonte("FuturaTEE-Book") == "sans"
    assert familia_fonte("ArialMT") == "sans"
    # monoespaçada
    assert familia_fonte("Courier-Bold") == "mono"
    assert familia_fonte("UbuntuMono-Regular") == "mono"


def test_familia_fonte_sem_pista_cai_em_serif():
    # corpo de livro é serifado — default seguro quando o nome não dá pista.
    assert familia_fonte("") == "serif"
    assert familia_fonte("Wingdings2") == "serif"


def test_fonte_seminegrito_detecta_peso_pelo_nome():
    # PyMuPDF só marca a flag bold em fontes "Bold"; "Demi"/"Semibold" (peso do
    # heading Manning/O'Reilly) passa batido — achado real (auditoria visual,
    # Kubernetes in Action: heading de seção FranklinGothic-Demi saía leve).
    assert fonte_seminegrito("FranklinGothic-DemiItal") is True
    assert fonte_seminegrito("MyriadPro-SemiboldCond") is True
    assert fonte_seminegrito("Helvetica-Black") is True
    assert fonte_seminegrito("MinionPro-Regular") is False
    assert fonte_seminegrito("NewBaskerville-Roman") is False


def test_agrupar_niveis_agrupa_x0_por_proximidade():
    # x0 das entradas do sumário (K8S): 66 (parte/cap), 148/150 (seção),
    # 186 (sub-seção) → 3 níveis de indentação.
    assert agrupar_niveis([66.2, 147.9, 150.2, 186.2, 66.2, 147.9]) == [66.2, 147.9, 186.2]


def test_nivel_indent_mapeia_x0_no_nivel_mais_proximo():
    niveis = [66.2, 147.9, 186.2]
    assert nivel_indent(66.2, niveis) == 0
    assert nivel_indent(148.0, niveis) == 1  # dentro da tolerância de 147.9
    assert nivel_indent(186.5, niveis) == 2
    assert nivel_indent(200.0, niveis) == 2  # além do último cai no mais próximo


def test_dividir_versalete_separa_cabecalho_run_in_colado():
    # Achado real (Kubernetes in Action): cabeçalho run-in small-caps sai colado
    # ao corpo ("SCALING MICROSERVICES Scaling..."). O caps deve virar versalete
    # (não caixa-alta literal — diretriz do usuário). Discriminador seguro: o
    # run-in é seguido de FRASE capitalizada, a sigla é seguida de minúscula.
    run, resto = dividir_versalete("SCALING MICROSERVICES Scaling microservices, unlike X.")
    assert run == "SCALING MICROSERVICES"
    assert resto == "Scaling microservices, unlike X."


def test_dividir_versalete_nao_toca_sigla_no_meio_do_fluxo():
    # "REST API allows..." — sigla seguida de minúscula, NÃO é cabeçalho.
    assert dividir_versalete("REST API allows you to do things.") == (
        None,
        "REST API allows you to do things.",
    )
    assert dividir_versalete("HTTP POST requests carry a body.") == (
        None,
        "HTTP POST requests carry a body.",
    )


def test_dividir_versalete_bloco_inteiro_em_caps():
    assert dividir_versalete("UNDERSTANDING IMAGE LAYERS") == ("UNDERSTANDING IMAGE LAYERS", "")
    assert dividir_versalete("PART I") == ("PART I", "")


def test_dividir_versalete_rotulo_de_admoestacao():
    # "NOTE"/"TIP"/"NOTA" (rótulo de admoestação) vira versalete mesmo sozinho.
    run, resto = dividir_versalete("NOTE If you’re using a Mac, do X.")
    assert run == "NOTE"
    assert resto == "If you’re using a Mac, do X."


def test_dividir_versalete_ignora_texto_normal():
    assert dividir_versalete("Um parágrafo normal de prosa.") == (
        None,
        "Um parágrafo normal de prosa.",
    )
    assert dividir_versalete("I am a single capital.") == (None, "I am a single capital.")


def test_nivel_titulo_bate_no_cluster_mais_proximo():
    clusters = [24.0, 18.0, 14.0]
    assert nivel_titulo(24.2, clusters) == "h1"
    assert nivel_titulo(18.0, clusters) == "h2"
    assert nivel_titulo(14.1, clusters) == "h3"
    assert nivel_titulo(11.0, clusters) is None


def test_taxa_abre_pagina_forca_quebra_com_amostra_suficiente():
    ocorrencias = {"h1": [True, True, True, False], "h2": [True, False, False]}
    out = taxa_abre_pagina(ocorrencias)
    assert out["h1"] is True  # 3/4 = 75% >= 60%
    assert out["h2"] is False  # 1/3 = 33% < 60%


def test_taxa_abre_pagina_amostra_pequena_fica_falso():
    out = taxa_abre_pagina({"h3": [True, True]})  # só 2 ocorrências
    assert out["h3"] is False


def test_extrai_fonte_real_embutida(tmp_path):
    import fitz

    from atlas.traducao.tipografia import extrair_fontes, gerar_font_faces

    fonte_path = str(
        __import__("pathlib").Path(__file__).resolve().parents[2]
        / "src"
        / "atlas"
        / "traducao"
        / "fonts"
        / "LiberationSans-Regular.ttf"
    )
    doc = fitz.open()
    page = doc.new_page()
    page.insert_font(fontname="atlasteste", fontfile=fonte_path)
    page.insert_text((72, 100), "Hello world", fontname="atlasteste", fontsize=12)
    p = tmp_path / "f.pdf"
    doc.save(str(p))
    doc.close()

    doc = fitz.open(str(p))
    fontes = extrair_fontes(doc)
    assert fontes  # pelo menos uma fonte extraída
    uri = next(iter(fontes.values()))
    assert uri.startswith("data:font/")
    css = gerar_font_faces(fontes)
    assert "@font-face" in css
    doc.close()


def test_extrai_fontes_documento_sem_fonte_embutida_nao_quebra(tmp_path):
    import fitz

    from atlas.traducao.tipografia import extrair_fontes

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Hello world", fontname="helv", fontsize=12)  # fonte base-14
    p = tmp_path / "f2.pdf"
    doc.save(str(p))
    doc.close()

    doc = fitz.open(str(p))
    fontes = extrair_fontes(doc)  # não deve levantar exceção
    assert isinstance(fontes, dict)
    doc.close()


def test_bloco_todo_em_courier_e_mono():
    spans = [
        _SpanFake("$ kubectl scale rc kubia --replicas=3", "Courier-Bold"),
        _SpanFake('replicationcontroller "kubia" scaled', "Courier"),
    ]
    assert bloco_e_mono(spans) is True


def test_bloco_prosa_com_poucos_termos_courier_nao_e_mono():
    # ADR-0041 fix: um parágrafo de prosa com 2-3 termos inline em Courier
    # (estilo "código" pontual) não deve virar bloco de código inteiro — senão
    # a prosa nunca é traduzida e vira <pre> verbatim (bug real observado).
    spans = [
        _SpanFake("You added the annotation ", "NewBaskerville-Roman"),
        _SpanFake("mycompany.com/someannotation", "Courier"),
        _SpanFake(" with the value ", "NewBaskerville-Roman"),
        _SpanFake("foo", "Courier"),
        _SpanFake(
            " bar. It's a good idea to use this format for annotation keys "
            "to prevent key collisions across tools and libraries.",
            "NewBaskerville-Roman",
        ),
    ]
    assert bloco_e_mono(spans) is False


def test_bloco_sem_spans_nao_e_mono():
    assert bloco_e_mono([]) is False
