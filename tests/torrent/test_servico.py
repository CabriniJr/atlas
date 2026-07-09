"""Máquina de estados do Kind Torrent (ADR-0049)."""

from __future__ import annotations

from datetime import datetime

import pytest

from atlas.core.store import ResourceStore
from atlas.torrent import download, servico
from atlas.torrent.download import Progresso
from atlas.torrent.scan import bencode


@pytest.fixture
def store():
    return ResourceStore(":memory:")


def _torrent_bytes(nome="filme.mkv", tam=700 * 1024 * 1024, ext_perigosa=False):
    fn = "malware.exe" if ext_perigosa else nome
    info = {b"piece length": 262144, b"name": b"pasta",
            b"files": [{b"length": tam, b"path": [fn.encode()]}]}
    return bencode({b"announce": b"http://t/x", b"info": info})


def _criar(store, tmp_path, *, chat=1, ext_perigosa=False):
    return servico.criar_do_bytes(
        store, _torrent_bytes(ext_perigosa=ext_perigosa), "a.torrent", chat,
        datetime.now(), dir_torrents=str(tmp_path),
    )


def _fake_baixar_ok(*a, **k):
    # simula on_progress + conclusão
    on = k.get("on_progress")
    if on:
        on(Progresso(pct=50, velocidade="1.0 MB/s", seeds=3))
        on(Progresso(pct=100, concluido=True))
    return download.ResultadoDownload(True, concluido=True, destino="/tmp/x")


def test_criar_do_bytes_cria_recurso_aguardando(store, tmp_path):
    res, sc = servico.criar_do_bytes(
        store, _torrent_bytes(), "filme.torrent", 42, datetime.now(), dir_torrents=str(tmp_path)
    )
    assert sc.ok
    assert res is not None
    assert res.status["fase"] == servico.AGUARDANDO
    assert res.name == sc.infohash
    assert store.get("Torrent", sc.infohash) is not None


def test_criar_do_bytes_scan_invalido_nao_cria(store, tmp_path):
    res, sc = servico.criar_do_bytes(
        store, b"lixo", "x.torrent", 42, datetime.now(), dir_torrents=str(tmp_path)
    )
    assert res is None and sc.ok is False
    assert store.list("Torrent") == []


def test_pendente_confirmacao(store, tmp_path):
    _criar(store, tmp_path)
    assert servico.pendente_confirmacao(store) is not None


def test_confirmar_dispara_download(monkeypatch, store, tmp_path):
    monkeypatch.setattr(download, "motor_disponivel", lambda: True)
    res, _ = _criar(store, tmp_path)
    disparados = []
    ok, msg = servico.confirmar(store, res.name, datetime.now(), dispatch=disparados.append)
    assert ok
    assert disparados == [res.name]
    assert store.get("Torrent", res.name).status["fase"] == servico.BAIXANDO


def test_confirmar_risco_alto_exige_forte(monkeypatch, store, tmp_path):
    monkeypatch.setattr(download, "motor_disponivel", lambda: True)
    res, sc = _criar(store, tmp_path, ext_perigosa=True)
    assert sc.risco == 2
    ok, msg = servico.confirmar(store, res.name, datetime.now(), dispatch=lambda n: None)
    assert ok is False and "SIM" in msg
    ok2, _ = servico.confirmar(store, res.name, datetime.now(), dispatch=lambda n: None, forte=True)
    assert ok2 is True


def test_confirmar_sem_motor_orienta_instalar(monkeypatch, store, tmp_path):
    monkeypatch.setattr(download, "motor_disponivel", lambda: False)
    res, _ = _criar(store, tmp_path)
    ok, msg = servico.confirmar(store, res.name, datetime.now(), dispatch=lambda n: None)
    assert ok is False and "qbittorrent-nox" in msg


def test_recusar(store, tmp_path):
    res, _ = _criar(store, tmp_path)
    ok, _ = servico.recusar(store, res.name, datetime.now())
    assert ok and store.get("Torrent", res.name).status["fase"] == servico.RECUSADO


def test_executar_download_conclui_e_notifica(store, tmp_path):
    res, _ = _criar(store, tmp_path, chat=77)
    store.set_status("Torrent", res.name, {**res.status, "fase": servico.BAIXANDO}, datetime.now())
    avisos = []
    servico.executar_download(
        store, res.name, notificar=lambda chat, msg: avisos.append((chat, msg)),
        cliente=object(), baixar_fn=_fake_baixar_ok, intervalo_s=0,
    )
    t = store.get("Torrent", res.name)
    assert t.status["fase"] == servico.CONCLUIDO
    assert t.status["progresso_pct"] == 100.0
    assert len(avisos) == 1 and avisos[0][0] == 77 and "baixado" in avisos[0][1]


def test_executar_download_erro_notifica(store, tmp_path):
    res, _ = _criar(store, tmp_path, chat=5)
    store.set_status("Torrent", res.name, {**res.status, "fase": servico.BAIXANDO}, datetime.now())

    def _falha(*a, **k):
        return download.ResultadoDownload(False, motivo="WebUI do motor não respondeu")

    avisos = []
    servico.executar_download(store, res.name, notificar=lambda c, m: avisos.append(m),
                              cliente=object(), baixar_fn=_falha, intervalo_s=0)
    assert store.get("Torrent", res.name).status["fase"] == servico.ERRO
    assert avisos and "falhou" in avisos[0]


def test_cancelar_sinaliza_flag(store, tmp_path):
    res, _ = _criar(store, tmp_path)
    store.set_status("Torrent", res.name, {**res.status, "fase": servico.BAIXANDO}, datetime.now())
    ok, _ = servico.cancelar(store, res.name, datetime.now())
    assert ok
    t = store.get("Torrent", res.name)
    assert t.status["cancelar"] is True and t.status["fase"] == servico.CANCELADO


def test_recuperar_orfaos_no_boot(store, tmp_path):
    res, _ = _criar(store, tmp_path)
    store.set_status("Torrent", res.name, {**res.status, "fase": servico.BAIXANDO}, datetime.now())
    n = servico.recuperar_orfaos_no_boot(store, datetime.now())
    assert n == 1
    assert store.get("Torrent", res.name).status["fase"] == servico.AGUARDANDO
