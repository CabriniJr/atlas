"""Testes dos comandos do pool + debug no handler (E6 / E5-01, batch).

Comandos em inglês: /idea, /task, /routine, /note, /pool [<state>|<id> <op>],
/debug. Roteamento via handler.responder().
"""

from __future__ import annotations

from datetime import datetime

from atlas.db import Database
from atlas.handler import responder

_AGORA = datetime(2026, 6, 16, 10, 0, 0)


def _db() -> Database:
    return Database(":memory:")


def _id(db: Database) -> int:
    return db.connection.execute("SELECT id FROM ideas").fetchone()[0]


# --- captura -----------------------------------------------------------------


def test_idea_captura_e_confirma():
    db = _db()
    resp = responder("/idea comprar webcam", db, _AGORA)
    assert "#" in resp and "/pool" in resp
    assert db.connection.execute("SELECT COUNT(*) FROM ideas").fetchone()[0] == 1


def test_task_e_routine_setam_tipo():
    db = _db()
    responder("/task implementar login", db, _AGORA)
    responder("/queue backup diario", db, _AGORA)
    tipos = [r[0] for r in db.connection.execute("SELECT tipo FROM ideas ORDER BY id").fetchall()]
    assert tipos == ["tarefa", "rotina"]


def test_idea_sem_texto_retorna_usage():
    db = _db()
    resp = responder("/idea", db, _AGORA)
    assert "usage" in resp.lower()
    assert db.connection.execute("SELECT COUNT(*) FROM ideas").fetchone()[0] == 0


def test_note_loga_activity_sem_poluir_pool():
    db = _db()
    responder("/note dormi 23h", db, _AGORA)
    assert db.connection.execute("SELECT COUNT(*) FROM activities").fetchone()[0] == 1
    assert db.connection.execute("SELECT COUNT(*) FROM ideas").fetchone()[0] == 0


# --- pool list / detail / manage --------------------------------------------


def test_pool_lista_e_vazio():
    db = _db()
    assert "empty" in responder("/pool", db, _AGORA).lower()
    responder("/idea comprar webcam", db, _AGORA)
    responder("/task revisar relatório", db, _AGORA)
    resp = responder("/pool", db, _AGORA)
    assert "webcam" in resp and "relatório" in resp


def test_pool_detalhe_e_inexistente():
    db = _db()
    responder("/idea comprar webcam", db, _AGORA)
    i = _id(db)
    assert "webcam" in responder(f"/pool {i}", db, _AGORA)
    assert "not found" in responder("/pool 9999", db, _AGORA).lower()


def test_pool_prio_edit_done_archive_drop():
    db = _db()
    responder("/idea titulo antigo", db, _AGORA)
    i = _id(db)

    responder(f"/pool {i} prio 5", db, _AGORA)
    assert db.connection.execute("SELECT prioridade FROM ideas WHERE id=?", (i,)).fetchone()[0] == 5

    # prio inválida não muda
    responder(f"/pool {i} prio abc", db, _AGORA)
    assert db.connection.execute("SELECT prioridade FROM ideas WHERE id=?", (i,)).fetchone()[0] == 5

    responder(f"/pool {i} edit novo titulo", db, _AGORA)
    assert (
        db.connection.execute("SELECT titulo FROM ideas WHERE id=?", (i,)).fetchone()[0]
        == "novo titulo"
    )

    responder(f"/pool {i} done", db, _AGORA)
    assert (
        db.connection.execute("SELECT estado FROM ideas WHERE id=?", (i,)).fetchone()[0]
        == "ativada"
    )

    responder(f"/pool {i} drop", db, _AGORA)
    assert (
        db.connection.execute("SELECT estado FROM ideas WHERE id=?", (i,)).fetchone()[0]
        == "descartada"
    )


def test_pool_filtra_por_estado():
    db = _db()
    responder("/idea a", db, _AGORA)
    responder(f"/pool {_id(db)} archive", db, _AGORA)
    assert "a" in responder("/pool arquivada", db, _AGORA)


# --- debug -------------------------------------------------------------------


def test_debug_status_e_help():
    db = _db()
    assert "status" in responder("/debug", db, _AGORA).lower()
    assert "/debug" in responder("/debug help", db, _AGORA)
    assert "rows" in responder("/debug db", db, _AGORA).lower()
