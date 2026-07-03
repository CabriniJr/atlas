from atlas.traducao.tipografia import converter_enfase


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
