"""Client de torrent em container/podman (ADR-0051) — sem podman nem imagem."""

from __future__ import annotations

from atlas.torrent import container
from atlas.torrent.container import ClienteContainer


class RunnerFake:
    """Grava as chamadas ao ``podman`` e devolve stdout programável."""

    def __init__(self, ps_stdout: str = ""):
        self.chamadas: list[list[str]] = []
        self._ps_stdout = ps_stdout

    def __call__(self, args, **kw):
        self.chamadas.append(list(args))

        class _R:
            stdout = self._ps_stdout if args[:2] == [container._RUNTIME, "ps"] else ""

        return _R()


class HttpFake:
    def __init__(self, versao="v5.0", info="[]"):
        self.gets: list[str] = []
        self.posts: list[tuple[str, bytes, dict]] = []
        self._versao = versao
        self._info = info

    def get(self, url):
        self.gets.append(url)
        if url.endswith("/app/version"):
            return self._versao
        if url.endswith("/torrents/info"):
            return self._info
        return None

    def post(self, url, corpo, headers):
        self.posts.append((url, corpo, headers))
        return ""


def _cliente(tmp_path, runner, http):
    return ClienteContainer(
        dir_downloads=str(tmp_path / "dl"),
        dir_config=str(tmp_path / "cfg"),
        runner=runner,
        http_get=http.get,
        http_post=http.post,
        max_ativos=2,
    )


def test_conf_tem_fila_nativa_seguranca_e_auth_local():
    conf = container.montar_conf(porta=8099, max_ativos=3, semear=False)
    assert "Session\\QueueingSystemEnabled=true" in conf
    assert "Session\\MaxActiveDownloads=3" in conf
    # 0 = preferir encriptação (não exigir): não corta peers sem suporte
    assert "Session\\Encryption=0" in conf
    assert "Session\\AnonymousModeEnabled=true" in conf
    assert "Session\\PortForwardingEnabled=false" in conf
    # sem semear: para de semear assim que conclui
    assert "Session\\GlobalMaxSeedingMinutes=0" in conf
    # WebUI passwordless só porque o bind é local
    assert "WebUI\\AuthSubnetWhitelist=0.0.0.0/0" in conf
    assert "WebUI\\LocalHostAuth=false" in conf


def test_run_args_mapeia_volumes_e_publica_local(tmp_path):
    args = container.montar_run_args(
        imagem="img", nome="atlas-qbt", porta=8099,
        dir_downloads="/dl", dir_config="/cfg",
    )
    assert args[0] == container._RUNTIME
    assert "-p" in args and "127.0.0.1:8099:8099" in args
    # rootless + SELinux: label :Z nos volumes e abc(911)→uid do host
    assert "/cfg:/config:Z" in args
    assert f"/dl:{container.DESTINO_CONTAINER}:Z" in args
    assert "--userns=keep-id:uid=911,gid=911" in args
    assert args[-1] == "img"


def test_garantir_no_ar_sobe_quando_nao_roda(tmp_path):
    runner = RunnerFake(ps_stdout="")  # nada rodando
    http = HttpFake()
    cli = _cliente(tmp_path, runner, http)
    assert cli.garantir_no_ar() is True
    # gravou a conf no volume
    assert (tmp_path / "cfg" / "qBittorrent" / "qBittorrent.conf").exists()
    # rodou um 'podman run'
    assert any(c[:2] == [container._RUNTIME, "run"] for c in runner.chamadas)


def test_garantir_no_ar_idempotente_nao_sobe_duas_vezes(tmp_path):
    runner = RunnerFake(ps_stdout="atlas-qbt\n")  # já rodando
    http = HttpFake()
    cli = _cliente(tmp_path, runner, http)
    assert cli.garantir_no_ar() is True
    assert not any(c[:2] == [container._RUNTIME, "run"] for c in runner.chamadas)


def test_adicionar_faz_post_multipart_com_o_torrent(tmp_path):
    runner = RunnerFake()
    http = HttpFake()
    cli = _cliente(tmp_path, runner, http)
    assert cli.adicionar(b"d1:xe", "meu.torrent") is True
    url, corpo, headers = http.posts[-1]
    assert url.endswith("/torrents/add")
    assert b"d1:xe" in corpo
    assert b'name="torrents"' in corpo
    assert b"savepath" in corpo
    assert "multipart/form-data" in headers["Content-Type"]


def test_adicionar_url_manda_magnet_no_campo_urls(tmp_path):
    http = HttpFake()
    cli = _cliente(tmp_path, RunnerFake(), http)
    assert cli.adicionar_url("magnet:?xt=urn:btih:ABC") is True
    url, corpo, headers = http.posts[-1]
    assert url.endswith("/torrents/add")
    assert b"urls=magnet" in corpo
    assert "x-www-form-urlencoded" in headers["Content-Type"]


def test_progresso_de_casa_por_infohash_e_usa_esta_completo(tmp_path):
    info = (
        '[{"hash":"ABC","progress":1.0,"state":"moving","dlspeed":0,"num_seeds":1},'
        '{"hash":"DEF","progress":0.5,"state":"downloading","dlspeed":1024,"num_seeds":3}]'
    )
    cli = _cliente(tmp_path, RunnerFake(), HttpFake(info=info))
    # moving @100% NÃO é concluído (espera o move — fix ADR-0049)
    p_abc = cli.progresso_de("abc")
    assert p_abc is not None and p_abc.concluido is False
    p_def = cli.progresso_de("def")
    assert p_def.pct == 50.0 and p_def.seeds == 3 and p_def.concluido is False
    # infohash desconhecido → None
    assert cli.progresso_de("999") is None


def test_progresso_de_concluido_quando_sai_de_moving(tmp_path):
    info = '[{"hash":"ABC","progress":1.0,"state":"pausedUP","dlspeed":0,"num_seeds":0}]'
    cli = _cliente(tmp_path, RunnerFake(), HttpFake(info=info))
    p = cli.progresso_de("abc")
    assert p is not None and p.concluido is True


def test_remover_manda_delete_sem_apagar_dados(tmp_path):
    http = HttpFake()
    cli = _cliente(tmp_path, RunnerFake(), http)
    cli.remover("abc")
    url, corpo, _ = http.posts[-1]
    assert url.endswith("/torrents/delete")
    assert b"deleteFiles=false" in corpo
    assert b"hashes=abc" in corpo
