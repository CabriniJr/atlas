"""Camada conversacional stateful do Torrent no Telegram (ADR-0049)."""

from __future__ import annotations

from datetime import datetime

import pytest

from atlas import torrent_cmd
from atlas.core.store import ResourceStore
from atlas.torrent import download, servico
from atlas.torrent.scan import bencode


@pytest.fixture
def store():
    return ResourceStore(":memory:")


def _bytes(fn="filme.mkv", tam=700 * 1024 * 1024):
    info = {b"piece length": 262144, b"name": b"pasta",
            b"files": [{b"length": tam, b"path": [fn.encode()]}]}
    return bencode({b"announce": b"http://t/x", b"info": info})


def _receber(store, tmp_path, **kw):
    return torrent_cmd.receber_documento(
        store, _bytes(**kw), "f.torrent", 5, datetime.now(),
        destino=str(tmp_path / "dl"),
    )


def test_receber_documento_pergunta_confirmacao(store, tmp_path, monkeypatch):
    monkeypatch.setattr(servico, "DIR_TORRENTS", str(tmp_path / "torr"))
    msg = _receber(store, tmp_path)
    assert "sim / não" in msg
    assert servico.pendente_confirmacao(store) is not None


def test_receber_documento_invalido(store):
    msg = torrent_cmd.receber_documento(store, b"lixo", "x.torrent", 5, datetime.now())
    assert "não consegui ler" in msg
    assert store.list("Torrent") == []


def test_sim_confirma_e_dispara(store, tmp_path, monkeypatch):
    monkeypatch.setattr(servico, "DIR_TORRENTS", str(tmp_path / "torr"))
    monkeypatch.setattr(download, "motor_disponivel", lambda: True)
    _receber(store, tmp_path)
    disparados = []
    r = torrent_cmd.responder_conversa("sim", store, datetime.now(), dispatch=disparados.append)
    assert r is not None and "baixando" in r.lower()
    assert len(disparados) == 1


def test_nao_recusa(store, tmp_path, monkeypatch):
    monkeypatch.setattr(servico, "DIR_TORRENTS", str(tmp_path / "torr"))
    _receber(store, tmp_path)
    r = torrent_cmd.responder_conversa("não", store, datetime.now(), dispatch=lambda n: None)
    assert r is not None
    pend = store.list("Torrent")[0]
    assert pend.status["fase"] == servico.RECUSADO


def test_texto_qualquer_nao_intercepta(store):
    # sem torrent pendente, "sim" não é do torrent → deixa o roteador base seguir
    d = lambda n: None  # noqa: E731
    assert torrent_cmd.responder_conversa("sim", store, datetime.now(), dispatch=d) is None
    assert torrent_cmd.responder_conversa("oi tudo bem", store, datetime.now(), dispatch=d) is None


def test_progresso_mostra_andamento(store, tmp_path, monkeypatch):
    monkeypatch.setattr(servico, "DIR_TORRENTS", str(tmp_path / "torr"))
    _receber(store, tmp_path)
    t = store.list("Torrent")[0]
    store.set_status("Torrent", t.name,
                     {**t.status, "fase": servico.BAIXANDO, "progresso_pct": 42.0,
                      "velocidade": "3.0 MB/s", "seeds": 5}, datetime.now())
    r = torrent_cmd.responder_conversa("progresso", store, datetime.now(), dispatch=lambda n: None)
    assert "42.0%" in r and "seeds: 5" in r


def test_cancelar_sinaliza(store, tmp_path, monkeypatch):
    monkeypatch.setattr(servico, "DIR_TORRENTS", str(tmp_path / "torr"))
    _receber(store, tmp_path)
    t = store.list("Torrent")[0]
    store.set_status("Torrent", t.name, {**t.status, "fase": servico.BAIXANDO}, datetime.now())
    r = torrent_cmd.responder_conversa("cancelar", store, datetime.now(), dispatch=lambda n: None)
    assert "cancelado" in r.lower()
    assert store.get("Torrent", t.name).status["cancelar"] is True


def test_slash_torrents_lista(store, tmp_path, monkeypatch):
    monkeypatch.setattr(servico, "DIR_TORRENTS", str(tmp_path / "torr"))
    _receber(store, tmp_path)
    r = torrent_cmd.responder_conversa("/torrents", store, datetime.now(), dispatch=lambda n: None)
    assert "Torrents" in r and "pasta" in r


def test_risco_alto_pede_SIM_maiusculo(store, tmp_path, monkeypatch):
    monkeypatch.setattr(servico, "DIR_TORRENTS", str(tmp_path / "torr"))
    monkeypatch.setattr(download, "motor_disponivel", lambda: True)
    msg = _receber(store, tmp_path, fn="virus.exe")
    assert "SIM (maiúsculo)" in msg
    # "sim" minúsculo não basta
    r = torrent_cmd.responder_conversa("sim", store, datetime.now(), dispatch=lambda n: None)
    assert "SIM" in r
    # "SIM" maiúsculo confirma
    disparados = []
    torrent_cmd.responder_conversa("SIM", store, datetime.now(), dispatch=disparados.append)
    assert len(disparados) == 1
