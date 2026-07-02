"""TDD — wiring do pool de execução na API (ADR-0038): fila, escalonamento e
visibilidade agregada em cima de `Traducao`."""

from __future__ import annotations

import time
from datetime import datetime

import pytest

from atlas.core.resource import Resource
from atlas.core.store import ResourceStore
from atlas.traducao.pool import TraducaoPool


def _store_com_traducoes(tmp_path, *labels):
    store = ResourceStore(str(tmp_path / "s.db"))
    for label in labels:
        pdf = tmp_path / f"{label}.pdf"
        pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
        store.apply(
            Resource(kind="Traducao", name=label, spec={"origem": str(pdf), "motor": "ollama"}),
            datetime(2026, 1, 1),
        )
    return store


@pytest.fixture(autouse=True)
def _pool_isolado(monkeypatch):
    """Cada teste começa com um pool fresco (teto 1, previsível) — evita
    vazamento de estado entre testes via o singleton do módulo."""
    import atlas.api as api

    pool = TraducaoPool(max_concorrente=1)
    monkeypatch.setattr(api, "_traducao_pool", pool)
    return pool


def _stub_collect_bloqueante(monkeypatch, liberar_evt, entrou_evt=None):
    """Registra um collect fake que trava até ``liberar_evt`` ser setado —
    simula uma tradução "em andamento" sem gastar IA/tempo real."""
    import atlas.rotinas as rotinas_mod

    def _collect(ctx):
        if entrou_evt is not None:
            entrou_evt.set()
        liberar_evt.wait(timeout=5)
        ctx.store.set_status(
            "Traducao", ctx.rotina.label, {"fase": "pronto"}, datetime(2026, 1, 1)
        )

    monkeypatch.setattr(rotinas_mod, "obter", lambda nome: _collect)


def test_segunda_traducao_acima_do_teto_vai_pra_fila(tmp_path, monkeypatch):
    import threading

    import atlas.api as api

    store = _store_com_traducoes(tmp_path, "a", "b")
    api._store = store
    entrou = threading.Event()
    liberar = threading.Event()
    _stub_collect_bloqueante(monkeypatch, liberar, entrou)

    code_a, body_a = api._iniciar_traducao("a")
    assert entrou.wait(timeout=2)  # garante que "a" já reservou o slot antes de "b"
    code_b, body_b = api._iniciar_traducao("b")

    assert (code_a, body_a["fase"]) == (200, "traduzindo")
    assert (code_b, body_b["fase"]) == (200, "fila")
    assert store.get("Traducao", "b").status["fase"] == "fila"
    assert api._traducao_pool.estado() == {
        "max_concorrente": 1,
        "rodando": ["a"],
        "fila": ["b"],
    }

    liberar.set()  # destrava "a"; deixa a thread terminar antes do teste sair


def test_iniciar_traducao_ja_na_fila_devolve_409(tmp_path, monkeypatch):
    import threading

    import atlas.api as api

    store = _store_com_traducoes(tmp_path, "a", "b")
    api._store = store
    entrou = threading.Event()
    liberar = threading.Event()
    _stub_collect_bloqueante(monkeypatch, liberar, entrou)

    api._iniciar_traducao("a")
    entrou.wait(timeout=2)
    api._iniciar_traducao("b")  # vai pra fila

    code, body = api._iniciar_traducao("b")
    assert code == 409

    liberar.set()


def test_liberar_slot_despacha_a_fila_automaticamente(tmp_path, monkeypatch):
    import threading

    import atlas.api as api

    store = _store_com_traducoes(tmp_path, "a", "b")
    api._store = store
    entrou_a = threading.Event()
    liberar_a = threading.Event()
    _stub_collect_bloqueante(monkeypatch, liberar_a, entrou_a)

    api._iniciar_traducao("a")
    entrou_a.wait(timeout=2)
    api._iniciar_traducao("b")
    assert api._traducao_pool.estado()["fila"] == ["b"]

    liberar_a.set()  # "a" termina (e libera "b", que usa o mesmo stub) → ambas concluem

    for _ in range(100):
        if store.get("Traducao", "b").status.get("fase") == "pronto":
            break
        time.sleep(0.02)
    assert store.get("Traducao", "b").status["fase"] == "pronto"
    assert api._traducao_pool.estado() == {"max_concorrente": 1, "rodando": [], "fila": []}


def test_pool_escalar_drena_a_fila_e_dispara_thread(tmp_path, monkeypatch):
    import threading

    import atlas.api as api

    store = _store_com_traducoes(tmp_path, "a", "b")
    api._store = store
    entrou = threading.Event()
    liberar = threading.Event()
    _stub_collect_bloqueante(monkeypatch, liberar, entrou)

    api._iniciar_traducao("a")
    entrou.wait(timeout=2)
    api._iniciar_traducao("b")

    code, body = api._traducao_pool_escalar({"max_concorrente": 2})
    assert code == 200
    assert body == {"max_concorrente": 2, "rodando": ["a", "b"], "fila": []}

    liberar.set()  # "a" e "b" usam o mesmo stub — destrava as duas
    for _ in range(100):
        if store.get("Traducao", "b").status.get("fase") == "pronto":
            break
        time.sleep(0.02)
    assert store.get("Traducao", "b").status["fase"] == "pronto"


def test_pool_escalar_valida_entrada():
    import atlas.api as api

    assert api._traducao_pool_escalar({"max_concorrente": "abc"})[0] == 400
    assert api._traducao_pool_escalar({"max_concorrente": 0})[0] == 400
    assert api._traducao_pool_escalar({})[0] == 400


def test_cancelar_da_fila(tmp_path, monkeypatch):
    import threading

    import atlas.api as api

    store = _store_com_traducoes(tmp_path, "a", "b")
    api._store = store
    entrou = threading.Event()
    liberar = threading.Event()
    _stub_collect_bloqueante(monkeypatch, liberar, entrou)

    api._iniciar_traducao("a")
    entrou.wait(timeout=2)
    api._iniciar_traducao("b")

    code, body = api._traducao_pool_cancelar_fila("b")
    assert code == 200
    assert store.get("Traducao", "b").status["fase"] == "cancelado"
    assert api._traducao_pool.estado()["fila"] == []

    assert api._traducao_pool_cancelar_fila("inexistente")[0] == 404

    liberar.set()


def test_traducao_pool_estado_endpoint_vazio():
    import atlas.api as api

    assert api._traducao_pool_estado() == (
        200,
        {"max_concorrente": 1, "rodando": [], "fila": []},
    )
