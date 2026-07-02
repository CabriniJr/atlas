"""TDD — TraducaoPool: teto de concorrência, fila FIFO e escalonamento (ADR-0038)."""

from __future__ import annotations

from atlas.traducao.pool import TraducaoPool


def test_roda_direto_enquanto_ha_slot():
    pool = TraducaoPool(max_concorrente=2)
    assert pool.tentar_iniciar("a") is True
    assert pool.tentar_iniciar("b") is True
    assert pool.estado() == {"max_concorrente": 2, "rodando": ["a", "b"], "fila": []}


def test_acima_do_teto_vai_pra_fila_fifo():
    pool = TraducaoPool(max_concorrente=1)
    assert pool.tentar_iniciar("a") is True
    assert pool.tentar_iniciar("b") is False
    assert pool.tentar_iniciar("c") is False
    assert pool.estado() == {"max_concorrente": 1, "rodando": ["a"], "fila": ["b", "c"]}


def test_liberar_despacha_o_proximo_da_fila():
    pool = TraducaoPool(max_concorrente=1)
    pool.tentar_iniciar("a")
    pool.tentar_iniciar("b")
    despachado = pool.liberar("a")
    assert despachado == "b"
    assert pool.estado() == {"max_concorrente": 1, "rodando": ["b"], "fila": []}


def test_liberar_sem_fila_devolve_none():
    pool = TraducaoPool(max_concorrente=2)
    pool.tentar_iniciar("a")
    assert pool.liberar("a") is None
    assert pool.estado()["rodando"] == []


def test_escalar_para_cima_drena_a_fila():
    pool = TraducaoPool(max_concorrente=1)
    pool.tentar_iniciar("a")
    pool.tentar_iniciar("b")
    pool.tentar_iniciar("c")
    despachados = pool.escalar(3)
    assert despachados == ["b", "c"]
    assert pool.estado() == {"max_concorrente": 3, "rodando": ["a", "b", "c"], "fila": []}


def test_escalar_para_baixo_nao_derruba_quem_ja_roda():
    pool = TraducaoPool(max_concorrente=3)
    pool.tentar_iniciar("a")
    pool.tentar_iniciar("b")
    pool.escalar(1)
    assert pool.estado()["rodando"] == ["a", "b"]  # não mata run em curso
    assert pool.max_concorrente == 1
    # próximo a liberar não dispara mais ninguém, porque já está acima do teto
    assert pool.liberar("a") is None


def test_escalar_teto_minimo_e_um():
    pool = TraducaoPool(max_concorrente=2)
    pool.escalar(0)
    assert pool.max_concorrente == 1
    pool.escalar(-5)
    assert pool.max_concorrente == 1


def test_cancelar_da_fila():
    pool = TraducaoPool(max_concorrente=1)
    pool.tentar_iniciar("a")
    pool.tentar_iniciar("b")
    assert pool.cancelar_da_fila("b") is True
    assert pool.estado()["fila"] == []
    assert pool.cancelar_da_fila("inexistente") is False


def test_tentar_iniciar_nao_duplica_na_fila():
    pool = TraducaoPool(max_concorrente=1)
    pool.tentar_iniciar("a")
    pool.tentar_iniciar("b")
    pool.tentar_iniciar("b")  # repetiu a mesma chamada (ex.: retry de rede)
    assert pool.estado()["fila"] == ["b"]
