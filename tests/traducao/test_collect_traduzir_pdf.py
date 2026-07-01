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

    def fake_invocar(prompt, modelo=None, timeout=60, motor="claude"):
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
    store.apply(
        Resource(kind="Traducao", name="livro", spec={"origem": str(src)}), agora
    )
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
    doc.new_page().insert_text((72, 100), "The kubectl command scales pods.", fontname="helv", fontsize=12)
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
