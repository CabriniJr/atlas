import re
from datetime import datetime, timezone
from types import SimpleNamespace

import fitz

import atlas.rotinas.traduzir_pdf as mod
from atlas.core.resource import Resource
from atlas.core.store import ResourceStore
from atlas.rotinas import obter


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
