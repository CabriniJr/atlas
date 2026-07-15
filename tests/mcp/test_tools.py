"""TDD — camada de ferramentas do MCP (ADR-0053). Puras, sem HTTP/MCP."""

from __future__ import annotations

from collections import namedtuple
from datetime import datetime

import pytest

from atlas.core.resource import Resource
from atlas.core.store import ResourceStore
from atlas.mcp import tools

_DU = namedtuple("du", "total used free")


@pytest.fixture
def store():
    return ResourceStore(":memory:")


def _disk(free_gb, total_gb=500):
    return lambda _p: _DU(int(total_gb * 1e9), 0, int(free_gb * 1e9))


# ── atlas_status ─────────────────────────────────────────────────────────────


def test_status_agrega_jobs_torrents_disco(store):
    store.apply(Resource(kind="Job", name="check-saude"), datetime.now())
    store.apply(
        Resource(kind="Torrent", name="t1", spec={"nome": "Debian"},
                 status={"fase": "baixando"}),
        datetime.now(),
    )
    st = tools.status(store, home="/", disk_usage=_disk(free_gb=42))
    assert st["jobs"] == 1
    assert st["torrents"] == [{"nome": "Debian", "fase": "baixando"}]
    assert st["disco_livre_gb"] == 42.0
    assert st["disco_total_gb"] == 500.0


def test_status_texto_e_humano(store):
    st_txt = tools.status_texto(store, home="/", disk_usage=_disk(free_gb=10))
    assert "Atlas" in st_txt
    assert "10" in st_txt  # disco livre aparece


# ── enfileirar_torrent ───────────────────────────────────────────────────────


class ClienteFake:
    def __init__(self, no_ar=True, add_ok=True):
        self._no_ar = no_ar
        self._add_ok = add_ok
        self.urls: list[str] = []

    def garantir_no_ar(self):
        return self._no_ar

    def adicionar_url(self, url):
        self.urls.append(url)
        return self._add_ok


def test_enfileirar_torrent_magnet_ok():
    cli = ClienteFake()
    out = tools.enfileirar_torrent(cli, "magnet:?xt=urn:btih:ABC")
    assert out["ok"] is True
    assert cli.urls == ["magnet:?xt=urn:btih:ABC"]


def test_enfileirar_torrent_sem_cliente():
    out = tools.enfileirar_torrent(None, "magnet:?x")
    assert out["ok"] is False and "podman" in out["erro"].lower()


def test_enfileirar_torrent_link_invalido():
    out = tools.enfileirar_torrent(ClienteFake(), "não é link")
    assert out["ok"] is False and "inválido" in out["erro"].lower()


def test_enfileirar_torrent_container_nao_sobe():
    out = tools.enfileirar_torrent(ClienteFake(no_ar=False), "magnet:?x")
    assert out["ok"] is False and "container" in out["erro"].lower()


# ── push_nuvem ───────────────────────────────────────────────────────────────


class _R:
    def __init__(self, rc, out="", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


def test_push_nuvem_sucesso(tmp_path):
    script = tmp_path / "push.sh"
    script.write_text("#!/bin/sh\n")
    chamadas = []
    out = tools.push_nuvem(
        script=str(script),
        runner=lambda *a, **k: (chamadas.append(a) or _R(0, "enviado")),
    )
    assert out["ok"] is True and "enviado" in out["saida"]


def test_push_nuvem_script_ausente(tmp_path):
    out = tools.push_nuvem(script=str(tmp_path / "nao-existe.sh"))
    assert out["ok"] is False and "não encontrado" in out["erro"]


def test_push_nuvem_falha(tmp_path):
    script = tmp_path / "push.sh"
    script.write_text("#!/bin/sh\n")
    out = tools.push_nuvem(script=str(script), runner=lambda *a, **k: _R(1, "", "boom"))
    assert out["ok"] is False and "boom" in out["erro"]


# ── instalar_jogo (stub — frente D) ──────────────────────────────────────────


def test_instalar_jogo_e_stub():
    out = tools.instalar_jogo("Zelda", "nuvem")
    assert out["ok"] is False
    assert "frente D" in out.get("pendente", "") or "frente D" in out.get("mensagem", "")
