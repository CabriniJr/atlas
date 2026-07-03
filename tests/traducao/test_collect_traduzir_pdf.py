import re
from datetime import datetime, timezone
from types import SimpleNamespace

import fitz
import pytest

import atlas.rotinas.traduzir_pdf as mod
from atlas.core.resource import Resource
from atlas.core.store import ResourceStore
from atlas.rotinas import obter


@pytest.fixture(autouse=True)
def _mt_offline(monkeypatch):
    """Evita rede: MT bruta vira identidade nos testes do collect (ADR-0031)."""
    monkeypatch.setattr("atlas.traducao.pipeline.traduzir_bruto", lambda textos, cfg: list(textos))


def test_collect_registrado():
    assert obter("traduzir-pdf") is not None


def test_collect_traduz_e_atualiza_status(tmp_path, monkeypatch):
    src = tmp_path / "livro.pdf"
    doc = fitz.open()
    p = doc.new_page()
    p.insert_text((72, 100), "The pod restarts.", fontname="helv", fontsize=12)
    doc.save(src)
    doc.close()

    store = ResourceStore(":memory:")
    agora = datetime.now(timezone.utc)
    store.apply(
        Resource(
            kind="Traducao",
            name="livro",
            spec={
                "origem": str(src),
                "idioma_destino": "pt-BR",
                "assunto": "Kubernetes",
                "glossario": ["pod"],
            },
        ),
        agora,
    )

    def fake_invocar(prompt, modelo=None, timeout=60, motor="claude", **_):
        ids = re.findall(r"\[\[(\d+)\]\]", prompt)
        return "\n".join(f"[[{i}]] O contêiner reinicia." for i in ids)

    monkeypatch.setattr(mod, "invocar", fake_invocar)

    ctx = SimpleNamespace(
        rotina=SimpleNamespace(nome="traduzir-pdf", label="livro"),
        store=store,
        agora=agora,
    )
    res = mod.collect(ctx)

    t = store.get("Traducao", "livro")
    assert t.status["fase"] == "pronto"
    assert t.status["saida"].endswith(".pt-BR.pdf")
    assert t.status["paginas_prontas"] == 1
    assert t.status["progresso_pct"] == 100
    assert "✓" in res.data["_saida"]
    assert "contêiner" in fitz.open(t.status["saida"])[0].get_text()


def test_collect_status_tem_log_e_atividade(tmp_path, monkeypatch):
    src = tmp_path / "l.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((72, 100), "The pod restarts.", fontname="helv", fontsize=12)
    doc.save(src)
    doc.close()

    store = ResourceStore(":memory:")
    agora = datetime.now(timezone.utc)
    store.apply(Resource(kind="Traducao", name="livro", spec={"origem": str(src)}), agora)
    monkeypatch.setattr(mod, "invocar", lambda p, **k: "[[0]] O contêiner reinicia.")

    ctx = SimpleNamespace(
        rotina=SimpleNamespace(nome="traduzir-pdf", label="livro"), store=store, agora=agora
    )
    mod.collect(ctx)

    st = store.get("Traducao", "livro").status
    assert st["fase"] == "pronto"
    assert st["blocos_traduzidos"] == 1
    assert st["iniciado_em"]
    assert st["atividade"] == "tradução concluída"
    # log ao vivo: início + marco(s) + conclusão, cada linha com t/msg
    msgs = [e["msg"] for e in st["log"]]
    assert any("iniciada" in m for m in msgs)
    assert any("concluído" in m for m in msgs)
    assert all("t" in e and "msg" in e for e in st["log"])


def test_collect_glossario_auto_loga_deteccao(tmp_path, monkeypatch):
    src = tmp_path / "g.pdf"
    doc = fitz.open()
    doc.new_page().insert_text(
        (72, 100), "The kubectl command scales pods.", fontname="helv", fontsize=12
    )
    doc.save(src)
    doc.close()

    store = ResourceStore(":memory:")
    agora = datetime.now(timezone.utc)
    store.apply(
        Resource(kind="Traducao", name="g", spec={"origem": str(src), "glossario_auto": "true"}),
        agora,
    )

    def fake(prompt, **k):
        if "permanecer em inglês" in prompt:
            return "kubectl, pods"
        return "[[0]] O comando kubectl escala pods."

    monkeypatch.setattr(mod, "invocar", fake)
    ctx = SimpleNamespace(
        rotina=SimpleNamespace(nome="traduzir-pdf", label="g"), store=store, agora=agora
    )
    mod.collect(ctx)

    st = store.get("Traducao", "g").status
    assert "kubectl" in st["glossario_auto"]
    assert any("glossário" in e["msg"] for e in st["log"])


def test_collect_parcial_pausa_e_agenda_retomada(tmp_path, monkeypatch):
    """Escassez de token (IA falha) → run parcial → status pausado + retoma_em (ADR-0035)."""
    from datetime import datetime as _dt

    src = tmp_path / "p.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((72, 100), "The pod restarts.", fontname="helv", fontsize=12)
    doc.save(src)
    doc.close()

    store = ResourceStore(":memory:")
    agora = datetime.now(timezone.utc)
    store.apply(
        Resource(kind="Traducao", name="p", spec={"origem": str(src), "janela_retomada_seg": 3600}),
        agora,
    )

    def ia_esgotada(prompt, **k):
        raise RuntimeError("rate limit / tokens acabaram")

    monkeypatch.setattr(mod, "invocar", ia_esgotada)
    ctx = SimpleNamespace(
        rotina=SimpleNamespace(nome="traduzir-pdf", label="p"), store=store, agora=agora
    )
    res = mod.collect(ctx)

    st = store.get("Traducao", "p").status
    assert st["parcial"] is True
    assert st["fase"] == "pausado"
    assert st["retoma_collect"] == "traduzir-pdf"
    # retomada agendada ~1h à frente (janela configurada)
    delta = (_dt.fromisoformat(st["retoma_em"]) - agora).total_seconds()
    assert 3500 < delta <= 3600
    assert "pausado" in res.data["_saida"] or "⏸" in res.data["_saida"]


def test_collect_timeout_faz_retry_curto_persistido(tmp_path, monkeypatch):
    """ADR-0039: timeout (não erro de cota explícito) pausa CURTO (5min default)
    e incrementa tentativas_timeout — persistido, não um sleep in-process."""
    from datetime import datetime as _dt

    src = tmp_path / "p.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((72, 100), "The pod restarts.", fontname="helv", fontsize=12)
    doc.save(src)
    doc.close()

    store = ResourceStore(":memory:")
    agora = datetime.now(timezone.utc)
    store.apply(Resource(kind="Traducao", name="p", spec={"origem": str(src)}), agora)

    def timeout_fn(prompt, **k):
        raise RuntimeError("timeout após 60s invocando IA")

    monkeypatch.setattr(mod, "invocar", timeout_fn)
    ctx = SimpleNamespace(
        rotina=SimpleNamespace(nome="traduzir-pdf", label="p"), store=store, agora=agora
    )
    mod.collect(ctx)

    st = store.get("Traducao", "p").status
    assert st["fase"] == "pausado"
    assert st["tentativas_timeout"] == 1
    delta = (_dt.fromisoformat(st["retoma_em"]) - agora).total_seconds()
    assert 290 < delta <= 300  # janela curta (default 5min), não as 5h de escassez
    assert "timeout 1/5" in st["atividade"]


def test_collect_timeout_apos_max_tentativas_vira_escassez_longa(tmp_path, monkeypatch):
    """Depois de max_tentativas_timeout retries curtos, o próximo timeout vira
    escassez confirmada: pausa longa e zera o contador (ADR-0039)."""
    from datetime import datetime as _dt

    src = tmp_path / "p.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((72, 100), "The pod restarts.", fontname="helv", fontsize=12)
    doc.save(src)
    doc.close()

    store = ResourceStore(":memory:")
    agora = datetime.now(timezone.utc)
    store.apply(
        Resource(
            kind="Traducao",
            name="p",
            spec={"origem": str(src), "janela_retomada_seg": 3600},
        ),
        agora,
    )
    store.set_status("Traducao", "p", {"tentativas_timeout": 5}, agora)  # já esgotou os 5

    def timeout_fn(prompt, **k):
        raise RuntimeError("timeout após 60s invocando IA")

    monkeypatch.setattr(mod, "invocar", timeout_fn)
    ctx = SimpleNamespace(
        rotina=SimpleNamespace(nome="traduzir-pdf", label="p"), store=store, agora=agora
    )
    mod.collect(ctx)

    st = store.get("Traducao", "p").status
    assert st["fase"] == "pausado"
    assert st["tentativas_timeout"] == 0  # zera pro próximo ciclo
    delta = (_dt.fromisoformat(st["retoma_em"]) - agora).total_seconds()
    assert 3500 < delta <= 3600  # janela longa de escassez, não mais a curta


def test_collect_sucesso_reseta_tentativas_timeout(tmp_path, monkeypatch):
    src = tmp_path / "p.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((72, 100), "The pod restarts.", fontname="helv", fontsize=12)
    doc.save(src)
    doc.close()

    store = ResourceStore(":memory:")
    agora = datetime.now(timezone.utc)
    store.apply(Resource(kind="Traducao", name="p", spec={"origem": str(src)}), agora)
    store.set_status("Traducao", "p", {"tentativas_timeout": 3}, agora)

    def fake_invocar(prompt, modelo=None, timeout=60, motor="claude", **_):
        ids = re.findall(r"\[\[(\d+)\]\]", prompt)
        return "\n".join(f"[[{i}]] O pod reinicia." for i in ids)

    monkeypatch.setattr(mod, "invocar", fake_invocar)
    ctx = SimpleNamespace(
        rotina=SimpleNamespace(nome="traduzir-pdf", label="p"), store=store, agora=agora
    )
    mod.collect(ctx)

    st = store.get("Traducao", "p").status
    assert st["fase"] == "pronto"
    assert st["tentativas_timeout"] == 0


def test_collect_log_fino_de_ia_no_refino(tmp_path, monkeypatch):
    """Cada chamada de IA no refino vira uma linha em status.log_ia (visibilidade)."""
    src = tmp_path / "f.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((72, 100), "The pod restarts.", fontname="helv", fontsize=12)
    doc.save(src)
    doc.close()

    store = ResourceStore(":memory:")
    agora = datetime.now(timezone.utc)
    store.apply(Resource(kind="Traducao", name="f", spec={"origem": str(src)}), agora)
    monkeypatch.setattr(mod, "invocar", lambda p, **k: "[[0]] O contêiner reinicia.")

    ctx = SimpleNamespace(
        rotina=SimpleNamespace(nome="traduzir-pdf", label="f"), store=store, agora=agora
    )
    mod.collect(ctx)

    log_ia = store.get("Traducao", "f").status.get("log_ia") or []
    assert log_ia, "deveria registrar ao menos uma chamada de IA no refino"
    assert any("lote" in e["msg"] and "blocos" in e["msg"] for e in log_ia)
    assert all("ok" in e for e in log_ia)


def test_collect_usa_agente_refino_quando_configurado(tmp_path, monkeypatch):
    """ADR-0040: Traducao.spec.agente_refino dita motor/persona do refino."""
    src = tmp_path / "livro.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((72, 100), "The pod restarts.", fontname="helv", fontsize=12)
    doc.save(src)
    doc.close()

    store = ResourceStore(":memory:")
    agora = datetime.now(timezone.utc)
    store.apply(
        Resource(
            kind="LLMProvider",
            name="ollama-dev",
            spec={"motor": "ollama", "modelo": "qwen3.6"},
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
    store.apply(
        Resource(
            kind="Traducao",
            name="livro",
            spec={"origem": str(src), "agente_refino": "tradutor-fidelidade"},
        ),
        agora,
    )

    vistos = []

    def fake_invocar(prompt, modelo=None, timeout=60, motor="claude", **_):
        vistos.append((motor, modelo, prompt))
        ids = re.findall(r"\[\[(\d+)\]\]", prompt)
        return "\n".join(f"[[{i}]] O contêiner reinicia." for i in ids)

    monkeypatch.setattr(mod, "invocar", fake_invocar)
    ctx = SimpleNamespace(
        rotina=SimpleNamespace(nome="traduzir-pdf", label="livro"), store=store, agora=agora
    )
    mod.collect(ctx)

    assert store.get("Traducao", "livro").status["fase"] == "pronto"
    motor_refino, modelo_refino, prompt_refino = vistos[-1]  # refino é a última chamada
    assert motor_refino == "ollama"
    assert modelo_refino == "qwen3.6"
    assert "Máxima fidelidade ao original." in prompt_refino


def test_collect_traducao_inexistente(tmp_path):
    store = ResourceStore(":memory:")
    agora = datetime.now(timezone.utc)
    ctx = SimpleNamespace(
        rotina=SimpleNamespace(nome="traduzir-pdf", label="nao-existe"),
        store=store,
        agora=agora,
    )
    res = mod.collect(ctx)
    assert "não encontrada" in res.data["_saida"]
