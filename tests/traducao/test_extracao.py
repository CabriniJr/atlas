import fitz

from atlas.traducao.extracao import BlocoTraducao, extrair_pagina


def test_extrai_blocos_com_metadados(pdf_simples):
    doc = fitz.open(pdf_simples)
    blocos = extrair_pagina(doc[0], 0)
    assert len(blocos) >= 2
    normal = [b for b in blocos if "deployment" in b.texto][0]
    assert isinstance(normal, BlocoTraducao)
    assert normal.pagina == 0
    assert normal.skip is False
    assert normal.spans[0].size == 12


def test_marca_monospace_como_skip(pdf_simples):
    doc = fitz.open(pdf_simples)
    blocos = extrair_pagina(doc[0], 0)
    codigo = [b for b in blocos if "kubectl" in b.texto][0]
    assert codigo.skip is True


def test_bloco_de_codigo_preserva_quebra_de_linha_e_indentacao(tmp_path):
    """Achado real (auditoria visual, Kubernetes in Action): um bloco de
    código YAML de 6 linhas virava UMA linha só, separada por espaço, com a
    indentação (2 espaços de "  name: ...") perdida — o código deixava de ser
    reproduzível/legível. Código é ``skip=True`` (nunca traduzido) e vira
    ``<pre>`` no render: precisa do texto ORIGINAL linha a linha, ipsis
    litteris (ADR-0041 fix)."""
    path = tmp_path / "codigo.pdf"
    doc = fitz.open()
    page = doc.new_page()
    linhas = [
        "apiVersion: v1",
        "kind: Service",
        "metadata:",
        "  name: kubia-nodeport",
        "spec:",
        "  type: NodePort",
    ]
    y = 200
    for linha in linhas:
        page.insert_text((72, y), linha, fontname="cour", fontsize=10)
        y += 12
    doc.save(str(path))
    doc.close()

    doc = fitz.open(str(path))
    blocos = extrair_pagina(doc[0], 0)
    codigo = [b for b in blocos if "kubia-nodeport" in b.texto][0]
    assert codigo.skip is True
    assert codigo.texto == "\n".join(linhas)
