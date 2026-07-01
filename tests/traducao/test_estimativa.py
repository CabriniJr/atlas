"""Estimativa de custo/tamanho da tradução (ADR-0030)."""

from __future__ import annotations

import fitz

from atlas.traducao.estimativa import estimar


def test_estimar_conta_paginas_e_ignora_codigo(tmp_path):
    src = tmp_path / "livro.pdf"
    doc = fitz.open()
    p = doc.new_page()
    p.insert_text((72, 100), "The deployment scales the pod.", fontname="helv", fontsize=12)
    p.insert_text((72, 200), "kubectl get pods", fontname="cour", fontsize=12)  # monospace: skip
    doc.new_page()  # 2a página em branco
    doc.save(src)
    doc.close()

    est = estimar(str(src))
    assert est.paginas == 2
    assert est.blocos_traduziveis == 1  # só o texto normal; código não conta
    assert est.caracteres >= len("The deployment scales the pod.")
    assert est.tokens_estimados > 0
    assert est.custo_usd_estimado > 0


def test_estimar_ollama_custo_zero(tmp_path):
    src = tmp_path / "l.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((72, 100), "Hello world.", fontname="helv", fontsize=12)
    doc.save(src)
    doc.close()

    est = estimar(str(src), motor="ollama")
    assert est.custo_usd_estimado == 0.0
    assert est.to_dict()["motor"] == "ollama"


def _pdf(path, texto="Hello world."):
    doc = fitz.open()
    doc.new_page().insert_text((72, 100), texto, fontname="helv", fontsize=12)
    doc.save(str(path))
    doc.close()


def test_endpoint_estimar_por_label(tmp_path):
    from atlas.api import _estimar_payload
    from atlas.core.resource import Resource
    from atlas.core.store import ResourceStore

    src = tmp_path / "a.pdf"
    _pdf(src)
    store = ResourceStore(str(tmp_path / "s.db"))
    store.apply(
        Resource(kind="Traducao", name="livro", spec={"origem": str(src), "motor": "ollama"}),
        __import__("datetime").datetime(2026, 1, 1),
    )

    code, body = _estimar_payload(store, "livro", "", "")
    assert code == 200
    assert body["paginas"] == 1
    assert body["motor"] == "ollama"
    assert body["custo_usd_estimado"] == 0.0


def test_endpoint_estimar_origem_direta(tmp_path):
    from atlas.api import _estimar_payload

    src = tmp_path / "b.pdf"
    _pdf(src, "The deployment scales the pod across the cluster nodes reliably.")
    code, body = _estimar_payload(None, "", str(src), "claude")
    assert code == 200
    assert body["custo_usd_estimado"] > 0


def test_endpoint_estimar_erros(tmp_path):
    from atlas.api import _estimar_payload
    from atlas.core.store import ResourceStore

    store = ResourceStore(str(tmp_path / "s.db"))
    assert _estimar_payload(store, "inexistente", "", "")[0] == 404
    assert _estimar_payload(store, "", "", "")[0] == 400
    assert _estimar_payload(store, "", "/nao/existe.pdf", "")[0] == 400
