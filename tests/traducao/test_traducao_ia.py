from atlas.traducao.extracao import BlocoTraducao
from atlas.traducao.traducao_ia import (
    CacheTraducao,
    ConfigTraducao,
    montar_prompt,
    parsear_resposta,
    traduzir_blocos,
)


def _bloco(bid, texto):
    return BlocoTraducao(id=bid, pagina=0, bbox=(0, 0, 1, 1), texto=texto, spans=[], skip=False)


def test_prompt_inclui_glossario_e_assunto():
    cfg = ConfigTraducao(assunto="Kubernetes", glossario=["pod", "deployment"])
    prompt = montar_prompt([_bloco(1, "The pod restarts.")], cfg)
    assert "Kubernetes" in prompt
    assert "pod" in prompt and "deployment" in prompt
    assert "[[1]]" in prompt  # marcador de bloco


def test_parseia_resposta_numerada():
    resp = "[[1]] O pod reinicia.\n[[2]] O deployment escala."
    out = parsear_resposta(resp, [1, 2])
    assert out == {1: "O pod reinicia.", 2: "O deployment escala."}


def test_traduz_usa_cache_e_nao_repaga(monkeypatch):
    cfg = ConfigTraducao()
    chamadas = []

    def fake_invocar(prompt, modelo=None, timeout=60, motor="claude"):
        chamadas.append(prompt)
        return "[[1]] O pod reinicia."

    cache = CacheTraducao()
    b = [_bloco(1, "The pod restarts.")]
    r1 = traduzir_blocos(b, cfg, cache, invocar_fn=fake_invocar)
    r2 = traduzir_blocos(b, cfg, cache, invocar_fn=fake_invocar)  # 2a vez: cache hit
    assert r1[1] == "O pod reinicia." and r2[1] == "O pod reinicia."
    assert len(chamadas) == 1  # só chamou a IA uma vez
