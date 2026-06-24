"""E0-04 — sincronizar_store: popula ResourceStore a partir de dados existentes."""

from __future__ import annotations

from datetime import datetime

from atlas.core.store import ResourceStore
from atlas.db import Database
from atlas.routines import Rotina
from atlas.sync import sincronizar_store

T0 = datetime(2026, 6, 16, 10, 0)


def _env() -> tuple[Database, ResourceStore]:
    return Database(":memory:"), ResourceStore(":memory:")


def test_sync_trackers_existentes():
    db, store = _env()
    db.insert(
        "trackers",
        nome="weight",
        dominio="saude",
        tipo="numero",
        unidade="kg",
        sintaxe="weight:",
        agregacao="ultimo",
        ativo=1,
        criado_em=T0.isoformat(),
    )
    sincronizar_store(db, store, [], agora=T0)
    r = store.get("Tracker", "weight")
    assert r is not None
    assert r.spec["unit"] == "kg"


def test_sync_alarms_existentes():
    db, store = _env()
    db.insert(
        "alarms",
        horario="08:00",
        mensagem="acordar",
        recorrencia="diario",
        proximo_disparo=T0.isoformat(),
        ativo=1,
        criado_em=T0.isoformat(),
    )
    sincronizar_store(db, store, [], agora=T0)
    alarmes = store.list("Alarm")
    assert len(alarmes) == 1
    assert alarmes[0].spec["time"] == "08:00"
    assert alarmes[0].spec["message"] == "acordar"


def test_sync_routines_do_toml():
    db, store = _env()
    rotinas = [
        Rotina(nome="treino", descricao="Treino físico", agenda="@every 1d", ativa=True),
        Rotina(nome="ping", descricao="Ping", agenda="@every 1m", ativa=False),
    ]
    sincronizar_store(db, store, rotinas, agora=T0)
    assert store.get("Job", "treino") is not None
    assert store.get("Job", "ping") is not None
    r = store.get("Job", "treino")
    assert r.spec["active"] is True


def test_sync_idempotente():
    db, store = _env()
    db.insert(
        "trackers",
        nome="weight",
        dominio="saude",
        tipo="numero",
        unidade="kg",
        sintaxe="weight:",
        agregacao="ultimo",
        ativo=1,
        criado_em=T0.isoformat(),
    )
    sincronizar_store(db, store, [], agora=T0)
    sincronizar_store(db, store, [], agora=T0)  # segunda vez
    assert len(store.list("Tracker")) == 1


def test_resources_mostra_tudo_pos_sync():
    from atlas.handler import responder

    db, store = _env()
    db.insert(
        "trackers",
        nome="sleep",
        dominio="saude",
        tipo="numero",
        unidade="h",
        sintaxe="sleep:",
        agregacao="ultimo",
        ativo=1,
        criado_em=T0.isoformat(),
    )
    db.insert(
        "alarms",
        horario="22:00",
        mensagem="dormir",
        recorrencia="diario",
        proximo_disparo=T0.isoformat(),
        ativo=1,
        criado_em=T0.isoformat(),
    )
    rotinas = [Rotina(nome="treino", descricao="Treino", ativa=True)]
    sincronizar_store(db, store, rotinas, agora=T0)

    resposta = responder("/resources", db, T0, store=store)
    assert "Tracker" in resposta
    assert "Alarm" in resposta
    assert "Job" in resposta
