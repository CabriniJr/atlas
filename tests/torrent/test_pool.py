"""Pool de torrents: concorrência + fila FIFO (ADR-0049)."""

from __future__ import annotations

from atlas.torrent.pool import TorrentPool


def test_ate_o_teto_baixa_junto():
    p = TorrentPool(max_concorrente=3)
    assert p.tentar_iniciar("a") is True
    assert p.tentar_iniciar("b") is True
    assert p.tentar_iniciar("c") is True
    # 4º estoura o teto → fila
    assert p.tentar_iniciar("d") is False
    assert p.estado()["rodando"] == ["a", "b", "c"]
    assert p.estado()["fila"] == ["d"]


def test_liberar_despacha_proximo_fifo():
    p = TorrentPool(max_concorrente=2)
    p.tentar_iniciar("a")
    p.tentar_iniciar("b")
    p.tentar_iniciar("c")
    p.tentar_iniciar("d")  # c, d na fila
    assert p.estado()["fila"] == ["c", "d"]
    prox = p.liberar("a")
    assert prox == "c"  # FIFO
    assert p.estado()["fila"] == ["d"]


def test_posicao_na_fila():
    p = TorrentPool(max_concorrente=1)
    p.tentar_iniciar("a")
    p.tentar_iniciar("b")
    p.tentar_iniciar("c")
    assert p.posicao_na_fila("b") == 1
    assert p.posicao_na_fila("c") == 2
    assert p.posicao_na_fila("a") is None  # está rodando


def test_cancelar_da_fila():
    p = TorrentPool(max_concorrente=1)
    p.tentar_iniciar("a")
    p.tentar_iniciar("b")
    assert p.cancelar_da_fila("b") is True
    assert p.estado()["fila"] == []
    assert p.cancelar_da_fila("x") is False


def test_escalar_drena_fila():
    p = TorrentPool(max_concorrente=1)
    p.tentar_iniciar("a")
    p.tentar_iniciar("b")
    p.tentar_iniciar("c")
    despachados = p.escalar(3)
    assert set(despachados) == {"b", "c"}
    assert p.estado()["fila"] == []


def test_idempotente_reiniciar_o_que_ja_roda():
    p = TorrentPool(max_concorrente=1)
    p.tentar_iniciar("a")
    assert p.tentar_iniciar("a") is True  # já rodando não vai pra fila
    assert p.estado()["fila"] == []
