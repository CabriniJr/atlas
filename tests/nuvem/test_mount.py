"""Mount do OneDrive que a loja Ownfoil serve (ADR-0056)."""

from __future__ import annotations

from atlas.nuvem import mount


def _unit(**kw):
    base = dict(
        remoto="onedrive:Jogos/Switch",
        ponto="/home/u/Games/Switch/Nuvem",
        rclone_bin="/home/u/bin/rclone",
        config="/home/u/.config/rclone/rclone.conf",
        cache_dir="/home/u/.cache/rclone",
    )
    base.update(kw)
    return mount.montar_unit_mount(**base)


def test_unit_usa_type_notify():
    """`Type=notify` é o que faz o systemd só considerar o serviço pronto DEPOIS
    do mount — é a garantia de que o container do Ownfoil enxerga os arquivos."""
    assert "Type=notify" in _unit()


def test_unit_nao_finge_rotular_o_mount():
    """Regressão de mentira silenciosa: eu tinha posto `-o context=` na unit e um
    teste afirmando isso. Medido em 2026-10-03, o rclone **descarta** o flag — ele
    não aparece em `mount`. O mount fica `fusefs_t` e funciona pela política do
    Fedora. Afirmar o flag era afirmar um efeito que não existe."""
    assert "-o context=" not in _unit()


def test_rotular_acervo_zera_mcs_e_poe_container_file_t(tmp_path):
    """Essa é a garantia que vale: sem o `:Z`, é o Atlas que rotula o acervo local.

    `-l s0` é essencial — categorias MCS sobrando de um `:Z` antigo
    (ex. `s0:c30,c41`) fazem o container ser negado.
    """
    chamadas = []

    def runner(args, **kw):
        chamadas.append(list(args))
        class R:
            returncode = 0
            stderr = ""
        return R()

    assert mount.rotular_acervo(str(tmp_path), runner=runner) is True
    assert chamadas == [["chcon", "-R", "-l", "s0", "-t", "container_file_t", str(tmp_path)]]


def test_rotular_acervo_ignora_diretorio_inexistente(tmp_path):
    def runner(args, **kw):
        raise AssertionError("não deveria chamar chcon")

    assert mount.rotular_acervo(str(tmp_path / "nao-existe"), runner=runner) is False


def test_unit_tem_caminhos_absolutos_pois_systemd_nao_expande_til():
    """systemd roda sem HOME/PATH: `~` não expande e o binário precisa ser absoluto."""
    u = _unit()
    assert "~" not in u
    for linha in u.splitlines():
        if linha.startswith(("ExecStart=", "ExecStop=", "ExecStartPre=")):
            assert linha.split("=", 1)[1].split()[0].startswith("/"), linha
    # config e cache explícitos (a doc do rclone exige com systemd)
    assert "--config /home/u/.config/rclone/rclone.conf" in u
    assert "--cache-dir /home/u/.cache/rclone" in u


def test_unit_monta_read_only_com_cache_para_o_scan_do_ownfoil():
    """O Ownfoil lê header de cada NSP/NSZ; sem cache VFS ele rebaixaria da nuvem
    a cada scan. E read-only: a loja nunca escreve no acervo."""
    u = _unit()
    assert "--read-only" in u
    assert "--vfs-cache-mode full" in u
    assert "--dir-cache-time" in u


def test_unit_desmonta_com_fusermount_no_stop():
    u = _unit()
    assert "ExecStop=/usr/bin/fusermount3 -u /home/u/Games/Switch/Nuvem" in u


def test_unit_e_pura():
    assert _unit() == _unit()
