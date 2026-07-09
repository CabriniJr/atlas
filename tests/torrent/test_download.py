"""Orquestração do download headless (ADR-0049) com cliente fake — sem binário."""

from __future__ import annotations

import os

from atlas.torrent import download
from atlas.torrent.download import ConfigDownload, Progresso


class ClienteFake:
    """Simula o qbittorrent-nox: uma sequência de progressos pré-programada."""

    def __init__(self, seq: list[Progresso], webui_ok: bool = True):
        self._seq = list(seq)
        self._webui_ok = webui_ok
        self.iniciou = False
        self.parou_p2p = False
        self.encerrou = False

    def iniciar(self, torrent_path, cfg, infohash):
        self.iniciou = True

    def esperar_webui(self, timeout_s):
        return self._webui_ok

    def progresso(self, infohash):
        return self._seq.pop(0) if self._seq else Progresso(pct=100, concluido=True)

    def parar_p2p(self):
        self.parou_p2p = True

    def encerrar(self):
        self.encerrou = True


def test_baixa_ate_concluir_para_p2p_e_encerra(tmp_path):
    seq = [
        Progresso(pct=10, estado="downloading"),
        Progresso(pct=60, estado="downloading"),
        Progresso(pct=100, estado="completed", concluido=True),
    ]
    cli = ClienteFake(seq)
    vistos: list[float] = []
    r = download.baixar(
        "x.torrent", "abc", ConfigDownload(destino=str(tmp_path)), cli,
        on_progress=lambda p: vistos.append(p.pct), intervalo_s=0,
    )
    assert r.ok and r.concluido
    assert cli.parou_p2p and cli.encerrou
    assert vistos[-1] == 100


def test_semear_nao_para_p2p(tmp_path):
    cli = ClienteFake([Progresso(pct=100, concluido=True)])
    download.baixar(
        "x.torrent", "abc", ConfigDownload(destino=str(tmp_path), semear=True), cli, intervalo_s=0
    )
    assert cli.parou_p2p is False


def test_cancelamento_aborta_e_encerra(tmp_path):
    cli = ClienteFake([Progresso(pct=10) for _ in range(5)])
    r = download.baixar(
        "x.torrent", "abc", ConfigDownload(destino=str(tmp_path)), cli,
        checar_cancel=lambda: True, intervalo_s=0,
    )
    assert r.ok is False and r.motivo == "cancelado"
    assert cli.encerrou


def test_webui_nao_sobe_falha(tmp_path):
    cli = ClienteFake([], webui_ok=False)
    cfg = ConfigDownload(destino=str(tmp_path))
    r = download.baixar("x.torrent", "abc", cfg, cli, intervalo_s=0)
    assert r.ok is False and "WebUI" in r.motivo
    assert cli.encerrou


def test_vpn_exigida_mas_inativa_nao_inicia(tmp_path):
    cli = ClienteFake([Progresso(pct=100, concluido=True)])
    r = download.baixar(
        "x.torrent", "abc", ConfigDownload(destino=str(tmp_path), vpn="wg0"), cli,
        iface_ativa_fn=lambda i: False, intervalo_s=0,
    )
    assert r.ok is False and "não está ativa" in r.motivo
    assert cli.iniciou is False


def test_kill_switch_vpn_cai_no_meio(tmp_path):
    estado = {"ativa": True}
    seq = [Progresso(pct=10), Progresso(pct=50), Progresso(pct=90)]
    cli = ClienteFake(seq)

    def iface(_):
        # ativa no gate inicial e no 1º tick; cai depois.
        v = estado["ativa"]
        estado["ativa"] = False
        return v

    r = download.baixar(
        "x.torrent", "abc", ConfigDownload(destino=str(tmp_path), vpn="wg0"), cli,
        iface_ativa_fn=iface, intervalo_s=0,
    )
    assert r.ok is False and "kill-switch" in r.motivo
    assert cli.encerrou


def test_sem_vpn_e_proibido_nao_inicia(tmp_path):
    cli = ClienteFake([Progresso(pct=100, concluido=True)])
    r = download.baixar(
        "x.torrent", "abc",
        ConfigDownload(destino=str(tmp_path), vpn="", permitir_sem_vpn=False), cli, intervalo_s=0,
    )
    assert r.ok is False
    assert cli.iniciou is False


def test_config_dir_usa_layout_do_profile(tmp_path):
    """Regressão: qbittorrent-nox v5 com --profile=<dir> lê a config em
    <dir>/qBittorrent/config/qBittorrent.conf. Escrever em <dir>/config/qBittorrent
    (o layout do Flatpak) faz o nox IGNORAR a config e subir a WebUI na porta
    padrão 8080 — que colide com a API do Atlas — quebrando o progresso."""
    cli = download.QBittorrentNox(profile=str(tmp_path / "prof"))
    assert cli._config_dir() == os.path.join(str(tmp_path / "prof"), "qBittorrent", "config")


def test_config_conf_reflete_seguranca(tmp_path):
    conf = download._config_conf(ConfigDownload(destino=str(tmp_path), semear=False))
    assert "AnonymousModeEnabled=true" in conf
    assert "Encryption=1" in conf
    assert "GlobalMaxSeedingMinutes=0" in conf  # não semeia
    assert "PortForwardingEnabled=false" in conf
