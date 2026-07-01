"""Endpoints do web shell de tradução: /_estimar, /_traduzir, schema (ADR-0030)."""

from __future__ import annotations

import time
from datetime import datetime

from atlas.core.resource import Resource
from atlas.core.store import ResourceStore


def _store_com_traducao(tmp_path, **spec):
    store = ResourceStore(str(tmp_path / "s.db"))
    base = {"origem": str(tmp_path / "x.pdf"), "motor": "ollama"}
    base.update(spec)
    store.apply(Resource(kind="Traducao", name="livro", spec=base), datetime(2026, 1, 1))
    (tmp_path / "x.pdf").write_bytes(b"%PDF-1.4\n")  # arquivo existe (conteúdo irrelevante aqui)
    return store


def test_schema_inclui_traducao():
    from atlas.api_schema import schema_payload

    kinds = schema_payload()["kinds"]
    assert "Traducao" in kinds
    campos = {c["k"] for c in kinds["Traducao"]["spec"]}
    assert {"origem", "idioma_destino", "motor"} <= campos


def test_iniciar_traducao_erros(tmp_path):
    import atlas.api as api

    store = _store_com_traducao(tmp_path)
    api._store = store

    assert api._iniciar_traducao("inexistente")[0] == 404

    # origem inválida
    store.apply(
        Resource(kind="Traducao", name="semorigem", spec={"origem": "/nao/existe.pdf"}),
        datetime(2026, 1, 1),
    )
    assert api._iniciar_traducao("semorigem")[0] == 400


def test_iniciar_traducao_conflito_quando_ja_rodando(tmp_path):
    import atlas.api as api

    store = _store_com_traducao(tmp_path)
    store.set_status("Traducao", "livro", {"fase": "traduzindo"}, datetime(2026, 1, 1))
    api._store = store
    assert api._iniciar_traducao("livro")[0] == 409


def test_iniciar_traducao_dispara_collect_em_background(tmp_path, monkeypatch):
    import atlas.api as api

    store = _store_com_traducao(tmp_path)
    api._store = store

    chamado = {}

    def stub_collect(ctx):
        chamado["label"] = ctx.rotina.label
        ctx.store.set_status("Traducao", "livro", {"fase": "pronto"}, datetime(2026, 1, 1))

        class _R:
            data = {"_saida": "ok"}

        return _R()

    monkeypatch.setattr("atlas.rotinas.obter", lambda nome: stub_collect)

    code, body = api._iniciar_traducao("livro")
    assert code == 200
    assert body["fase"] == "traduzindo"

    for _ in range(50):
        if (store.get("Traducao", "livro").status or {}).get("fase") == "pronto":
            break
        time.sleep(0.02)
    assert chamado["label"] == "livro"
    assert store.get("Traducao", "livro").status["fase"] == "pronto"
