"""Endpoints do web shell de tradução: /_estimar, /_traduzir, schema (ADR-0030)."""

from __future__ import annotations

import threading
import time
from datetime import datetime
from http.client import HTTPConnection

from atlas.core.resource import Resource
from atlas.core.store import ResourceStore

_PDF_BYTES = b"%PDF-1.4\n%%EOF\n"


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


def test_salvar_upload_grava_pdf_e_atualiza_origem(tmp_path, monkeypatch):
    import atlas.api as api

    store = _store_com_traducao(tmp_path)
    api._store = store
    monkeypatch.setenv("ATLAS_PDF_DIR", str(tmp_path / "pdfs"))

    code, body = api._salvar_upload("Meu Livro!.pdf", "livro", _PDF_BYTES)
    assert code == 200
    assert body["name"] == "Meu_Livro_.pdf"  # saneado
    from pathlib import Path

    assert Path(body["path"]).read_bytes() == _PDF_BYTES
    assert store.get("Traducao", "livro").spec["origem"] == body["path"]


def test_salvar_upload_rejeita_nao_pdf(tmp_path, monkeypatch):
    import atlas.api as api

    monkeypatch.setenv("ATLAS_PDF_DIR", str(tmp_path / "pdfs"))
    assert api._salvar_upload("x.pdf", "", b"")[0] == 400  # vazio
    assert api._salvar_upload("x.pdf", "", b"nao eh pdf")[0] == 400  # sem %PDF-


def test_download_traducao_via_http(tmp_path, free_tcp_port):
    import atlas.api as api
    from http.server import ThreadingHTTPServer

    saida = tmp_path / "livro.pt-BR.pdf"
    saida.write_bytes(_PDF_BYTES)
    store = ResourceStore(str(tmp_path / "s.db"))
    store.apply(Resource(kind="Traducao", name="livro", spec={}), datetime(2026, 1, 1))
    store.set_status("Traducao", "livro", {"fase": "pronto", "saida": str(saida)}, datetime(2026, 1, 1))
    api._store = store
    api._TOKEN = ""

    server = ThreadingHTTPServer(("127.0.0.1", free_tcp_port), api._Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        c = HTTPConnection("127.0.0.1", free_tcp_port)
        c.request("GET", "/apis/atlas/v1/_download?label=livro")
        resp = c.getresponse()
        data = resp.read()
        assert resp.status == 200
        assert resp.getheader("Content-Type") == "application/pdf"
        assert "attachment" in resp.getheader("Content-Disposition", "")
        assert data == _PDF_BYTES

        # sem saída → 409
        c.request("GET", "/apis/atlas/v1/_download?label=inexistente")
        assert c.getresponse().status == 404
    finally:
        server.shutdown()
