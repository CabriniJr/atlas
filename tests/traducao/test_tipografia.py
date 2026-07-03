from atlas.traducao.tipografia import (
    clusters_titulo,
    converter_enfase,
    nivel_titulo,
    taxa_abre_pagina,
)


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
        / "src" / "atlas" / "traducao" / "fonts" / "LiberationSans-Regular.ttf"
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
