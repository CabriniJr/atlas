from datetime import datetime

from atlas.core.resource import Resource
from atlas.core.store import ResourceStore
from atlas.traducao.extracao import BlocoTraducao
from atlas.traducao.traducao_ia import (
    CacheTraducao,
    ConfigTraducao,
    montar_prompt,
    montar_prompt_refino,
    parsear_resposta,
    resolver_agente_refino,
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


# ---------------------------------------------------------------------------
# ADR-0040 — Agente de refino (persona/motor pluggable via Traducao.spec.agente_refino)
# ---------------------------------------------------------------------------


def test_prompt_refino_usa_instrucao_customizada_mas_mantem_contrato():
    cfg = ConfigTraducao(
        glossario=["pod"],
        instrucao_refino="Você é um revisor obcecado por fidelidade máxima ao original.",
    )
    prompt = montar_prompt_refino([(1, "The pod scales.", "O pod escala.")], cfg)
    assert "fidelidade máxima" in prompt
    assert "pod" in prompt  # glossário sempre presente
    assert "[[N]] <tradução final>" in prompt  # contrato de formato sempre presente
    assert "ORIGEM: The pod scales." in prompt and "BRUTO: O pod escala." in prompt


def test_prompt_refino_sem_instrucao_usa_padrao():
    cfg = ConfigTraducao()
    prompt = montar_prompt_refino([(1, "A.", "a")], cfg)
    assert "revisa a tradução" in prompt


def test_resolver_agente_refino_sem_agente_devolve_none():
    store = ResourceStore(":memory:")
    t = Resource(kind="Traducao", name="x", spec={"origem": "a.pdf"})
    assert resolver_agente_refino(t, store) == (None, None, None)


def test_resolver_agente_refino_via_provider():
    store = ResourceStore(":memory:")
    agora = datetime.now()
    store.apply(
        Resource(
            kind="LLMProvider",
            name="ollama-dev",
            spec={"motor": "ollama", "modelo": "qwen3.6", "endpoint": "http://192.168.86.38:11434"},
        ),
        agora,
    )
    store.apply(
        Resource(
            kind="Agente",
            name="tradutor-fidelidade",
            spec={"provider": "ollama-dev", "prompt": "Máxima fidelidade ao original."},
        ),
        agora,
    )
    t = Resource(kind="Traducao", name="x", spec={"agente_refino": "tradutor-fidelidade"})
    motor, modelo, instrucao = resolver_agente_refino(t, store)
    assert motor == "ollama"
    assert modelo == "qwen3.6"
    assert instrucao == "Máxima fidelidade ao original."


def test_resolver_agente_refino_modelo_do_agente_sobrepoe_provider():
    store = ResourceStore(":memory:")
    agora = datetime.now()
    store.apply(
        Resource(kind="LLMProvider", name="p", spec={"motor": "ollama", "modelo": "gemma4"}), agora
    )
    store.apply(
        Resource(
            kind="Agente", name="a", spec={"provider": "p", "modelo": "qwen3.6", "prompt": "x"}
        ),
        agora,
    )
    t = Resource(kind="Traducao", name="x", spec={"agente_refino": "a"})
    motor, modelo, _ = resolver_agente_refino(t, store)
    assert motor == "ollama"
    assert modelo == "qwen3.6"


def test_resolver_agente_refino_agente_inexistente_devolve_none():
    store = ResourceStore(":memory:")
    t = Resource(kind="Traducao", name="x", spec={"agente_refino": "nao-existe"})
    assert resolver_agente_refino(t, store) == (None, None, None)
