"""Testes dos comandos do pool de ideias no handler (E6-02, E6-03 — TDD).

Cobre o roteamento de /ideia, /tarefa, /licao, /rotina_nova, /ideias
via handler.responder().
"""

from __future__ import annotations

from datetime import datetime

from atlas.db import Database
from atlas.handler import responder


def _db() -> Database:
    return Database(":memory:")


_AGORA = datetime(2026, 6, 16, 10, 0, 0)


# ---------------------------------------------------------------------------
# E6-02 — captura via comandos Telegram
# ---------------------------------------------------------------------------


def test_comando_ideia_captura_e_confirma():
    db = _db()
    resposta = responder("/ideia comprar webcam", db, _AGORA)
    assert "capturada" in resposta.lower() or "#" in resposta
    n = db.connection.execute("SELECT COUNT(*) FROM ideas").fetchone()[0]
    assert n == 1


def test_comando_tarefa_captura_tipo_tarefa():
    db = _db()
    responder("/tarefa implementar login", db, _AGORA)
    row = db.connection.execute("SELECT tipo FROM ideas").fetchone()
    assert row[0] == "tarefa"


def test_comando_licao_captura_tipo_tarefa():
    db = _db()
    responder("/licao estudar ADRs", db, _AGORA)
    row = db.connection.execute("SELECT tipo FROM ideas").fetchone()
    assert row[0] == "tarefa"


def test_comando_rotina_nova_captura_tipo_rotina():
    db = _db()
    responder("/rotina_nova backup diario", db, _AGORA)
    row = db.connection.execute("SELECT tipo FROM ideas").fetchone()
    assert row[0] == "rotina"


def test_comando_ideia_sem_texto_retorna_ajuda():
    """/ideia sem texto -> ajuda; nao grava."""
    db = _db()
    resposta = responder("/ideia", db, _AGORA)
    assert "uso" in resposta.lower() or "ajuda" in resposta.lower() or "/ideia" in resposta
    n = db.connection.execute("SELECT COUNT(*) FROM ideas").fetchone()[0]
    assert n == 0


def test_comando_tarefa_sem_texto_retorna_ajuda():
    db = _db()
    resposta = responder("/tarefa", db, _AGORA)
    assert "uso" in resposta.lower() or "/tarefa" in resposta
    n = db.connection.execute("SELECT COUNT(*) FROM ideas").fetchone()[0]
    assert n == 0


# ---------------------------------------------------------------------------
# E6-03 — CRUD / priorizacao via handler
# ---------------------------------------------------------------------------


def test_comando_ideias_lista_itens():
    db = _db()
    responder("/ideia comprar webcam", db, _AGORA)
    responder("/tarefa implementar login", db, _AGORA)
    resposta = responder("/ideias", db, _AGORA)
    assert "webcam" in resposta
    assert "login" in resposta


def test_comando_ideias_vazio_informa():
    db = _db()
    resposta = responder("/ideias", db, _AGORA)
    assert "vazio" in resposta.lower() or "nenhum" in resposta.lower() or "0" in resposta


def test_comando_ideia_id_mostra_detalhe():
    db = _db()
    responder("/ideia comprar webcam", db, _AGORA)
    id_row = db.connection.execute("SELECT id FROM ideas").fetchone()[0]
    resposta = responder(f"/ideia {id_row}", db, _AGORA)
    assert "webcam" in resposta


def test_comando_ideia_id_inexistente_retorna_erro():
    db = _db()
    resposta = responder("/ideia 9999", db, _AGORA)
    assert "9999" in resposta
    assert (
        "encontrado" in resposta.lower() or "nao" in resposta.lower() or "não" in resposta.lower()
    )


def test_comando_ideia_prio_atualiza():
    db = _db()
    responder("/ideia comprar webcam", db, _AGORA)
    id_row = db.connection.execute("SELECT id FROM ideas").fetchone()[0]
    resposta = responder(f"/ideia {id_row} prio 5", db, _AGORA)
    assert "5" in resposta or "prioridade" in resposta.lower()
    prio = db.connection.execute("SELECT prioridade FROM ideas WHERE id=?", (id_row,)).fetchone()[0]
    assert prio == 5


def test_comando_ideia_prio_nao_numerica_retorna_erro():
    """/ideia <id> prio abc -> erro + exemplo; nada muda."""
    db = _db()
    responder("/ideia comprar webcam", db, _AGORA)
    id_row = db.connection.execute("SELECT id FROM ideas").fetchone()[0]
    prio_antes = db.connection.execute(
        "SELECT prioridade FROM ideas WHERE id=?", (id_row,)
    ).fetchone()[0]
    resposta = responder(f"/ideia {id_row} prio abc", db, _AGORA)
    assert (
        "numero" in resposta.lower()
        or "numerico" in resposta.lower()
        or "inteiro" in resposta.lower()
        or "invalido" in resposta.lower()
    )
    prio_depois = db.connection.execute(
        "SELECT prioridade FROM ideas WHERE id=?", (id_row,)
    ).fetchone()[0]
    assert prio_antes == prio_depois


def test_comando_ideia_editar():
    db = _db()
    responder("/ideia titulo antigo", db, _AGORA)
    id_row = db.connection.execute("SELECT id FROM ideas").fetchone()[0]
    responder(f"/ideia {id_row} editar novo titulo", db, _AGORA)
    titulo = db.connection.execute("SELECT titulo FROM ideas WHERE id=?", (id_row,)).fetchone()[0]
    assert titulo == "novo titulo"


def test_comando_ideia_feito():
    db = _db()
    responder("/ideia algo", db, _AGORA)
    id_row = db.connection.execute("SELECT id FROM ideas").fetchone()[0]
    responder(f"/ideia {id_row} feito", db, _AGORA)
    estado = db.connection.execute("SELECT estado FROM ideas WHERE id=?", (id_row,)).fetchone()[0]
    assert estado == "ativada"


def test_comando_ideia_arquivar():
    db = _db()
    responder("/ideia algo", db, _AGORA)
    id_row = db.connection.execute("SELECT id FROM ideas").fetchone()[0]
    responder(f"/ideia {id_row} arquivar", db, _AGORA)
    estado = db.connection.execute("SELECT estado FROM ideas WHERE id=?", (id_row,)).fetchone()[0]
    assert estado == "arquivada"


def test_comando_ideia_remover_soft_delete():
    db = _db()
    responder("/ideia algo", db, _AGORA)
    id_row = db.connection.execute("SELECT id FROM ideas").fetchone()[0]
    responder(f"/ideia {id_row} remover", db, _AGORA)
    estado = db.connection.execute("SELECT estado FROM ideas WHERE id=?", (id_row,)).fetchone()[0]
    assert estado == "descartada"
    # some da lista default
    responder("/ideias", db, _AGORA)
    # nao deve aparecer na listagem normal
    n_ativos = db.connection.execute(
        "SELECT COUNT(*) FROM ideas WHERE estado NOT IN ('descartada','arquivada')"
    ).fetchone()[0]
    assert n_ativos == 0


def test_comando_ideias_com_filtro_estado():
    db = _db()
    responder("/ideia algo", db, _AGORA)
    id_row = db.connection.execute("SELECT id FROM ideas").fetchone()[0]
    responder(f"/ideia {id_row} arquivar", db, _AGORA)
    resposta = responder("/ideias arquivada", db, _AGORA)
    assert "algo" in resposta


def test_comandos_pool_nao_interferem_com_registro_livre():
    """Mensagens livres ainda geram activities; comandos pool nao."""
    db = _db()
    responder("treino de perna", db, _AGORA)
    responder("/ideia comprar webcam", db, _AGORA)
    n_act = db.connection.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
    n_ideas = db.connection.execute("SELECT COUNT(*) FROM ideas").fetchone()[0]
    assert n_act == 1
    assert n_ideas == 1
