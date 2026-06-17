"""E0-04 — Idea kind no ResourceStore (TDD).

Quando /idea /task /queue capturam um item, ele também vive no ResourceStore
como Resource(kind="Idea"|"Task"|"Routine"). Isso permite /list Idea, /describe,
/delete via verbos kubectl. A tabela `ideas` continua — migração aditiva.
"""

from __future__ import annotations

from datetime import datetime

from atlas.core.store import ResourceStore
from atlas.db import Database
from atlas.handler import responder

T0 = datetime(2026, 6, 16, 10, 0)


def _env() -> tuple[Database, ResourceStore]:
    db = Database(":memory:")
    store = ResourceStore(":memory:")
    return db, store


# --- captura via /idea grava no ResourceStore --------------------------------


def test_ideia_capturada_vai_pro_store():
    db, store = _env()
    responder("/idea fazer UI web do Atlas", db, T0, store=store)
    recursos = store.list("Idea")
    assert len(recursos) == 1
    assert "fazer UI web do Atlas" in recursos[0].spec.get("body", "")


def test_task_capturada_vai_pro_store():
    db, store = _env()
    responder("/task refatorar handler", db, T0, store=store)
    recursos = store.list("Task")
    assert len(recursos) == 1


def test_idea_tem_id_no_name():
    db, store = _env()
    responder("/idea minha primeira ideia", db, T0, store=store)
    r = store.list("Idea")[0]
    assert r.name.startswith("idea-")


def test_idea_ainda_grava_na_tabela_legada():
    """A tabela ideas continua recebendo (não quebra o /pool)."""
    db, store = _env()
    responder("/idea comprar teclado", db, T0, store=store)
    n = db.connection.execute("SELECT COUNT(*) FROM ideas").fetchone()[0]
    assert n == 1


def test_list_idea_via_verbo():
    db, store = _env()
    responder("/idea ideia alpha", db, T0, store=store)
    responder("/idea ideia beta", db, T0, store=store)
    resposta = responder("/list Idea", db, T0, store=store)
    assert "ideia alpha" in resposta or "idea-" in resposta
    assert "Idea (2)" in resposta


def test_describe_idea_via_verbo():
    db, store = _env()
    responder("/idea design do dashboard", db, T0, store=store)
    nome = store.list("Idea")[0].name
    resposta = responder(f"/describe Idea {nome}", db, T0, store=store)
    assert "dashboard" in resposta
