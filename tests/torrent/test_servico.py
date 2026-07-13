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
    # última notificação é a de conclusão
    assert avisos[-1][0] == 77 and "baixado" in avisos[-1][1]


def test_notifica_marcos_10_50_90(store, tmp_path):
    res, _ = _criar(store, tmp_path, chat=9)
    store.set_status("Torrent", res.name, {**res.status, "fase": servico.BAIXANDO}, datetime.now())

    def _baixar_marcos(*a, **k):
        on = k["on_progress"]
        for pct in (5, 12, 55, 92, 100):  # cruza 10, 50, 90 e conclui
            on(Progresso(pct=pct, velocidade="2.0 MB/s", concluido=pct >= 100))
        return download.ResultadoDownload(True, concluido=True, destino="/tmp/x")

    marcos = []
    servico.executar_download(
        store, res.name, notificar=lambda c, m: marcos.append(m),
        cliente=object(), baixar_fn=_baixar_marcos, intervalo_s=0,
    )
    texto = "\n".join(marcos)
    assert "10%" in texto and "50%" in texto and "90%" in texto
    assert "baixado" in texto  # conclusão
    # cada marco só uma vez
    assert texto.count("10%") == 1 and texto.count("50%") == 1 and texto.count("90%") == 1


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


def test_retomar_no_boot_auto_resume(store, tmp_path):
    """Persistência (ADR-0049): um torrent que estava baixando retoma sozinho
    após restart — re-despachado, não volta pra confirmação."""
    from atlas.torrent.pool import TorrentPool

    res, _ = _criar(store, tmp_path)
    store.set_status("Torrent", res.name, {**res.status, "fase": servico.BAIXANDO}, datetime.now())
    disparados = []
    n = servico.retomar_no_boot(
        store, datetime.now(), dispatch=disparados.append, pool=TorrentPool(3)
    )
    assert n == 1
    assert disparados == [res.name]  # re-despachado (retomou)
    assert store.get("Torrent", res.name).status["fase"] == servico.BAIXANDO


def test_confirmar_alem_do_teto_vai_pra_fila(monkeypatch, store, tmp_path):
    from atlas.torrent.pool import TorrentPool

    monkeypatch.setattr(download, "motor_disponivel", lambda: True)
    pool = TorrentPool(max_concorrente=1)
    a, _ = servico.criar_do_bytes(
        store, _torrent_bytes(nome="a.mkv"), "a.torrent", 1, datetime.now(),
        dir_torrents=str(tmp_path),
    )
    # 2º torrent (infohash diferente)
    b, _ = servico.criar_do_bytes(
        store, _torrent_bytes(nome="b.mkv", tam=123), "b.torrent", 1, datetime.now(),
        dir_torrents=str(tmp_path),
    )
    disparados = []
    d = disparados.append
    ok1, _ = servico.confirmar(store, a.name, datetime.now(), dispatch=d, pool=pool)
    ok2, msg2 = servico.confirmar(store, b.name, datetime.now(), dispatch=d, pool=pool)
    assert ok1 and ok2
    assert disparados == [a.name]  # só o 1º baixa
    assert store.get("Torrent", a.name).status["fase"] == servico.BAIXANDO
    assert store.get("Torrent", b.name).status["fase"] == servico.FILA
    assert "fila" in msg2.lower()


def test_ao_concluir_slot_despacha_proximo(store, tmp_path):
    from atlas.torrent.pool import TorrentPool

    pool = TorrentPool(max_concorrente=1)
    a, _ = servico.criar_do_bytes(
        store, _torrent_bytes(nome="a.mkv"), "a.torrent", 1, datetime.now(),
        dir_torrents=str(tmp_path),
    )
    b, _ = servico.criar_do_bytes(
        store, _torrent_bytes(nome="b.mkv", tam=9), "b.torrent", 1, datetime.now(),
        dir_torrents=str(tmp_path),
    )
    pool.tentar_iniciar(a.name)
    pool.tentar_iniciar(b.name)  # b na fila
    store.set_status("Torrent", b.name, {**b.status, "fase": servico.FILA}, datetime.now())
    prox = servico.ao_concluir_slot(store, a.name, pool=pool)
    assert prox == b.name
    assert store.get("Torrent", b.name).status["fase"] == servico.BAIXANDO


def test_cancelar_da_fila(monkeypatch, store, tmp_path):
    from atlas.torrent.pool import TorrentPool

    pool = TorrentPool(max_concorrente=1)
    res, _ = _criar(store, tmp_path)
    pool.tentar_iniciar("ocupa-o-slot")
    pool.tentar_iniciar(res.name)  # vai pra fila
    store.set_status("Torrent", res.name, {**res.status, "fase": servico.FILA}, datetime.now())
    ok, msg = servico.cancelar(store, res.name, datetime.now(), pool=pool)
    assert ok and "fila" in msg.lower()
    assert store.get("Torrent", res.name).status["fase"] == servico.CANCELADO
    assert pool.posicao_na_fila(res.name) is None


def test_executar_download_verifica_integridade_falha(store, tmp_path):
    """Ao concluir, um .nsz sem magic PFS0 → integridade=falha + aviso."""
    res, _ = _criar(store, tmp_path, chat=7)
    dest = tmp_path / "dl"
    (dest / res.spec["nome"]).mkdir(parents=True)
    (dest / res.spec["nome"] / "jogo.nsz").write_bytes(b"LIXO" + b"\x00" * 10)
    store.set_status(
        "Torrent", res.name,
        {**res.status, "fase": servico.BAIXANDO, "destino": str(dest)}, datetime.now(),
    )
    # o spec.destino também precisa apontar pro dest
    store.patch("Torrent", res.name, {"destino": str(dest)}, datetime.now())
    avisos = []
    servico.executar_download(
        store, res.name, notificar=lambda c, m: avisos.append(m),
        cliente=object(), baixar_fn=_fake_baixar_ok, intervalo_s=0,
    )
    t = store.get("Torrent", res.name)
    assert t.status["fase"] == servico.CONCLUIDO
    assert t.status["integridade"] == "falha"
    assert any("integridade falhou" in m.lower() or "invalid pfs0" in m.lower() for m in avisos)


def test_executar_download_reprova_truncado_mesmo_com_magic_ok(store, tmp_path):
    """Caso real (ADR-0049): arquivo com header PFS0 correto (passa no magic) mas
    TRUNCADO — o move do qBittorrent foi morto no meio. O magic sozinho dava ✅ e o
    jogo chegava corrompido; a checagem de completude por tamanho reprova."""
    res, _ = _criar(store, tmp_path, chat=7)  # torrent declara 700 MB
    dest = tmp_path / "dl"
    (dest / res.spec["nome"]).mkdir(parents=True)
    # header válido, mas só 104 bytes (muito menor que os 700 MB do .torrent)
    (dest / res.spec["nome"] / "jogo.nsp").write_bytes(b"PFS0" + b"\x00" * 100)
    store.set_status(
        "Torrent", res.name,
        {**res.status, "fase": servico.BAIXANDO, "destino": str(dest)}, datetime.now(),
    )
    store.patch("Torrent", res.name, {"destino": str(dest)}, datetime.now())
    avisos = []
    servico.executar_download(
        store, res.name, notificar=lambda c, m: avisos.append(m),
        cliente=object(), baixar_fn=_fake_baixar_ok, intervalo_s=0,
    )
    t = store.get("Torrent", res.name)
    assert t.status["integridade"] == "falha"
    assert "incompleto" in (t.status.get("integridade_detalhe") or "").lower()
    assert any("incompleto" in m.lower() for m in avisos)
