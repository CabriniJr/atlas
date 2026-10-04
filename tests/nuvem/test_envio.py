"""Subir o jogo baixado pro OneDrive e liberar disco (ADR-0056, fase 2)."""

from __future__ import annotations

from atlas.nuvem import envio


def test_usa_move_para_verificar_antes_de_apagar():
    """`rclone move` confere cada arquivo no destino ANTES de remover a origem.

    É o que torna o "sobe e apaga o local" seguro: um `copy` + `rm` cego poderia
    apagar o jogo depois de um upload truncado.
    """
    args = envio.montar_args_subir(
        alvo="/home/u/Documents/torrent/Jogo X",
        nome="Jogo X",
        remoto="onedrive:Jogos/Switch",
        rclone_bin="/home/u/bin/rclone",
    )
    assert args[0] == "/home/u/bin/rclone"
    assert args[1] == "move"
    assert "/home/u/Documents/torrent/Jogo X" in args
    assert "onedrive:Jogos/Switch/Jogo X" in args
    # nunca um `delete` solto
    assert "delete" not in args and "purge" not in args


def test_passa_config_absoluto_e_remove_dir_vazio():
    args = envio.montar_args_subir(
        alvo="/a/Jogo", nome="Jogo", remoto="onedrive:Jogos/Switch",
        rclone_bin="/bin/rclone", config="/c/rclone.conf",
    )
    assert "--config" in args and "/c/rclone.conf" in args
    assert "--delete-empty-src-dirs" in args


def test_subir_ok_devolve_destino_remoto(tmp_path):
    alvo = tmp_path / "Jogo Y"
    alvo.mkdir()
    (alvo / "a.nsp").write_text("x")

    def runner(args, **kw):
        class R:
            returncode = 0
            stdout = "Transferred: 1 / 1"
            stderr = ""
        return R()

    r = envio.subir(str(alvo), "Jogo Y", runner=runner)
    assert r.ok is True
    assert r.destino_remoto == "onedrive:Jogos/Switch/Jogo Y"
    assert "Jogo Y" in r.mensagem


def test_subir_falha_nao_mente_sucesso(tmp_path):
    alvo = tmp_path / "Jogo Z"
    alvo.mkdir()

    def runner(args, **kw):
        class R:
            returncode = 1
            stdout = ""
            stderr = "quota exceeded"
        return R()

    r = envio.subir(str(alvo), "Jogo Z", runner=runner)
    assert r.ok is False
    assert "quota exceeded" in r.mensagem


def test_subir_recusa_alvo_inexistente(tmp_path):
    def runner(args, **kw):
        raise AssertionError("não deveria chamar o rclone")

    r = envio.subir(str(tmp_path / "nao-existe"), "X", runner=runner)
    assert r.ok is False
    assert "não encontrei" in r.mensagem


def test_subir_remove_a_pasta_vazia_que_sobra(tmp_path):
    """`--delete-empty-src-dirs` NÃO remove a raiz da origem (medido).

    A sobra importa: `arquivar_ausentes` usa `os.path.exists`, então uma pasta
    vazia faria o jogo parecer ainda local depois de ir pra nuvem.
    """
    alvo = tmp_path / "Jogo"
    alvo.mkdir()
    (alvo / "a.nsp").write_text("x")

    def runner(args, **kw):
        # simula o rclone move: leva os arquivos, deixa a raiz vazia
        for f in alvo.iterdir():
            f.unlink()
        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        return R()

    r = envio.subir(str(alvo), "Jogo", runner=runner)
    assert r.ok is True
    assert not alvo.exists(), "a pasta vazia deveria ter sido removida"


def test_subir_nunca_remove_pasta_com_conteudo(tmp_path):
    """Trava: se sobrou arquivo (upload parcial), a origem FICA."""
    alvo = tmp_path / "Jogo"
    alvo.mkdir()
    (alvo / "ficou.nsp").write_text("sobrou")

    def runner(args, **kw):
        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        return R()

    r = envio.subir(str(alvo), "Jogo", runner=runner)
    assert alvo.exists() and (alvo / "ficou.nsp").exists()
    assert "sobrou" in r.mensagem or r.ok
