"""Container Ownfoil (loja Tinfoil) via podman rootless (ADR-0052) — sem podman."""

from __future__ import annotations

from atlas.ownfoil import container
from atlas.ownfoil.container import ClienteOwnfoil


class RunnerFake:
    """Grava as chamadas ao ``podman`` e devolve stdout programável (para ``ps``)."""

    def __init__(self, ps_stdout: str = ""):
        self.chamadas: list[list[str]] = []
        self._ps_stdout = ps_stdout

    def __call__(self, args, **kw):
        self.chamadas.append(list(args))

        class _R:
            stdout = self._ps_stdout if args[:2] == [container._RUNTIME, "ps"] else ""

        return _R()


class HttpFake:
    def __init__(self, home="<html>ownfoil</html>"):
        self.gets: list[str] = []
        self._home = home

    def get(self, url):
        self.gets.append(url)
        return self._home


def _cliente(tmp_path, runner, http, env_file=None):
    return ClienteOwnfoil(
        dir_games=str(tmp_path / "games"),
        dir_config=str(tmp_path / "cfg"),
        dir_data=str(tmp_path / "data"),
        env_file=env_file,
        runner=runner,
        http_get=http.get,
        # nunca escrever no ~/.config/systemd/user real a partir de teste
        unit_dir=str(tmp_path / "units"),
        tem_systemd=False,
    )


def test_run_args_monta_volumes_userns_e_publica_local(tmp_path):
    args = container.montar_run_args(
        imagem="img", nome="atlas-ownfoil", porta=8465,
        dir_games="/g", dir_config="/cfg", dir_data="/data", env_file="/s/o.env",
    )
    assert args[0] == container._RUNTIME
    # publica só no loopback (o Funnel expõe publicamente, não o container)
    assert "-p" in args and "127.0.0.1:8465:8465" in args
    # jogos montados read-only (a loja só serve, nunca escreve no acervo)
    # SEM `:Z` no acervo: o relabel recursivo do podman quebra quando há um
    # rclone mount read-only dentro (ADR-0056). O acervo é rotulado à mão.
    assert "/g:/games:ro" in args
    assert "/g:/games:ro,Z" not in args
    # config/data com relabel SELinux
    assert "/cfg:/app/config:Z" in args
    assert "/data:/app/data:Z" in args
    # Ownfoil roda como root dentro do container (faz chown /app): SEM keep-id, senão
    # o entrypoint cai pra sudo e o container sai com erro (ao contrário do torrent).
    assert not any(str(a).startswith("--userns") for a in args)
    # segredos (admin) vêm de env-file, nunca inline no argv (não vazam no ps)
    assert "--env-file" in args and "/s/o.env" in args
    assert not any(str(a).startswith("USER_ADMIN_PASSWORD=") for a in args)
    assert args[-1] == "img"


def test_run_args_sem_env_file_nao_passa_flag(tmp_path):
    args = container.montar_run_args(
        imagem="img", nome="n", porta=8465,
        dir_games="/g", dir_config="/cfg", dir_data="/data", env_file=None,
    )
    assert "--env-file" not in args


def test_garantir_no_ar_sobe_quando_nao_roda(tmp_path):
    runner = RunnerFake(ps_stdout="")  # nada rodando
    cli = _cliente(tmp_path, runner, HttpFake())
    assert cli.garantir_no_ar() is True
    # criou os diretórios de estado
    assert (tmp_path / "cfg").exists() and (tmp_path / "data").exists()
    assert any(c[:2] == [container._RUNTIME, "run"] for c in runner.chamadas)


def test_garantir_no_ar_idempotente_nao_sobe_duas_vezes(tmp_path):
    runner = RunnerFake(ps_stdout="atlas-ownfoil\n")  # já rodando
    cli = _cliente(tmp_path, runner, HttpFake())
    assert cli.garantir_no_ar() is True
    assert not any(c[:2] == [container._RUNTIME, "run"] for c in runner.chamadas)


def test_esperar_http_falha_quando_nao_responde(tmp_path):
    class HttpMorto:
        def get(self, url):
            return None

    cli = _cliente(tmp_path, RunnerFake(), HttpMorto())
    assert cli.esperar_http(timeout_s=1) is False


def test_contar_jogos_reconhece_extensoes_switch(tmp_path):
    g = tmp_path / "games"
    (g / "Sub").mkdir(parents=True)
    (g / "Jogo A [0100].nsp").write_bytes(b"x")
    (g / "Jogo B.nsz").write_bytes(b"x")
    (g / "Sub" / "Jogo C.xci").write_bytes(b"x")
    (g / "leiame.txt").write_bytes(b"x")  # não conta
    assert container.contar_jogos(str(g)) == 3


def test_status_reflete_container_e_acervo(tmp_path):
    g = tmp_path / "games"
    g.mkdir()
    (g / "Jogo.nsp").write_bytes(b"x")
    runner = RunnerFake(ps_stdout="atlas-ownfoil\n")
    cli = ClienteOwnfoil(
        dir_games=str(g), dir_config=str(tmp_path / "c"), dir_data=str(tmp_path / "d"),
        runner=runner, http_get=HttpFake().get,
        unit_dir=str(tmp_path / "units"), tem_systemd=False,
    )
    st = cli.status()
    assert st["rodando"] is True
    assert st["jogos"] == 1
    assert st["porta"] == container.PORT


# ── ciclo de vida: systemd dono do container (2026-10-03) ───────────────────
def test_garantir_no_ar_sobe_pela_unit_quando_ha_systemd(tmp_path):
    """O Ownfoil também morria junto com o restart do atlas.service."""
    chamadas = []

    def runner(args, **kw):
        chamadas.append(list(args))
        class R:
            stdout = ""
            returncode = 0
        return R()

    c = container.ClienteOwnfoil(
        dir_games=str(tmp_path / "games"),
        dir_config=str(tmp_path / "cfg"),
        dir_data=str(tmp_path / "data"),
        env_file=None,
        runner=runner,
        http_get=lambda url: "ok",
        unit_dir=str(tmp_path / "units"),
        tem_systemd=True,
    )
    assert c.garantir_no_ar() is True
    planas = [" ".join(a) for a in chamadas]
    assert any("systemctl" in p and "start" in p for p in planas), planas
    assert not any(p.startswith("podman run") for p in planas), planas
    assert (tmp_path / "units" / "atlas-ownfoil.service").is_file()


def test_garantir_no_ar_ownfoil_cai_pro_podman_sem_systemd(tmp_path):
    chamadas = []

    def runner(args, **kw):
        chamadas.append(list(args))
        class R:
            stdout = ""
            returncode = 0
        return R()

    c = container.ClienteOwnfoil(
        dir_games=str(tmp_path / "games"),
        dir_config=str(tmp_path / "cfg"),
        dir_data=str(tmp_path / "data"),
        env_file=None,
        runner=runner,
        http_get=lambda url: "ok",
        unit_dir=str(tmp_path / "units"),
        tem_systemd=False,
    )
    assert c.garantir_no_ar() is True
    assert any(" ".join(a).startswith("podman run") for a in chamadas)


def test_unit_do_ownfoil_vem_depois_do_mount_da_nuvem():
    """`rprivate`: o mount tem de existir ANTES do container, senão ele vê a pasta
    vazia. `Wants=` (não `Requires=`) para a loja continuar servindo o acervo
    local se o OneDrive estiver fora do ar."""
    unit = container.montar_unit_ownfoil(
        nome="atlas-ownfoil", run_args=["podman", "run", "-d", "x"]
    )
    assert "After=atlas-nuvem.service" in unit
    assert "Wants=atlas-nuvem.service" in unit
    assert "Requires=atlas-nuvem.service" not in unit


def test_garantir_no_ar_rotula_acervo_e_monta_nuvem_antes_do_container(tmp_path, monkeypatch):
    """Ordem obrigatória (`rprivate`): rótulo + mount ANTES de subir o container."""
    ordem = []

    def runner(args, **kw):
        if args and args[0] == "chcon":
            ordem.append("chcon")
        elif "systemctl" in args[0] and "start" in args:
            ordem.append("start-container")
        class R:
            stdout = ""
            returncode = 0
            stderr = ""
        return R()

    monkeypatch.setattr(
        container, "_garantir_nuvem", lambda acervo, runner=None: ordem.append("mount")
    )
    games = tmp_path / "games"
    games.mkdir()
    c = container.ClienteOwnfoil(
        dir_games=str(games), dir_config=str(tmp_path / "cfg"), dir_data=str(tmp_path / "d"),
        env_file=None, runner=runner, http_get=lambda u: "ok",
        unit_dir=str(tmp_path / "units"), tem_systemd=True,
    )
    assert c.garantir_no_ar() is True
    assert ordem.index("mount") < ordem.index("start-container"), ordem
