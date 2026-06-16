"""Testes do módulo pool de ideias (E6-01, E6-02, E6-03 — TDD).

Cobre os casos de teste listados em docs/specs/pool-de-ideias.md.
"""

from __future__ import annotations

from datetime import datetime

from atlas.db import Database
from atlas.pool import (
    arquivar_ideia,
    atualizar_prioridade,
    capturar_ideia,
    concluir_ideia,
    descartar_ideia,
    editar_corpo,
    listar_ideias,
    obter_ideia,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _db() -> Database:
    return Database(":memory:")


_AGORA = datetime(2026, 6, 16, 10, 0, 0)


# ---------------------------------------------------------------------------
# E6-01 — tabela ideas existe e tem os campos corretos
# ---------------------------------------------------------------------------


def test_tabela_ideas_criada_no_schema():
    db = _db()
    tabelas = {
        r[0]
        for r in db.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "ideas" in tabelas


def test_tabela_ideas_tem_todos_os_campos():
    db = _db()
    colunas = {r[1] for r in db.connection.execute("PRAGMA table_info(ideas)").fetchall()}
    esperadas = {
        "id",
        "tipo",
        "titulo",
        "corpo",
        "prioridade",
        "estado",
        "rotina_alvo",
        "erro",
        "criado_em",
        "atualizado_em",
    }
    assert esperadas <= colunas


def test_banco_existente_ganha_tabela_ideas_sem_perder_dados():
    """Garante idempotencia: banco com dados na tabela activities ganha ideas."""
    db = _db()
    # insere dado nas tabelas existentes
    db.insert(
        "activities",
        ts=_AGORA.isoformat(),
        dominio="geral",
        rotina="log",
        texto_cru="teste",
    )
    # "recria" o schema (simula banco existente)
    db._init_schema()
    # dado original preservado
    n = db.connection.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
    assert n == 1
    # tabela ideas presente
    tabelas = {
        r[0]
        for r in db.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "ideas" in tabelas


# ---------------------------------------------------------------------------
# E6-02 — captura via /ideia, /tarefa, /licao, /rotina_nova
# ---------------------------------------------------------------------------


def test_captura_ideia_simples():
    """/ideia comprar webcam -> 1 linha tipo=ideia, estado=capturada."""
    db = _db()
    ideia_id = capturar_ideia(db, tipo="ideia", texto="comprar webcam", agora=_AGORA)
    row = obter_ideia(db, ideia_id)
    assert row is not None
    assert row["tipo"] == "ideia"
    assert row["titulo"] == "comprar webcam"
    assert row["estado"] == "capturada"
    assert row["prioridade"] == 100


def test_captura_tarefa_via_tipo():
    db = _db()
    ideia_id = capturar_ideia(db, tipo="tarefa", texto="implementar login", agora=_AGORA)
    row = obter_ideia(db, ideia_id)
    assert row["tipo"] == "tarefa"
    assert row["estado"] == "capturada"


def test_captura_rotina_nova():
    db = _db()
    ideia_id = capturar_ideia(db, tipo="rotina", texto="rotina de backup diario", agora=_AGORA)
    row = obter_ideia(db, ideia_id)
    assert row["tipo"] == "rotina"
    assert row["titulo"] == "rotina de backup diario"


def test_titulo_e_primeira_linha_corpo_e_texto_completo():
    """Titulo = 1a linha; corpo = texto completo (conforme spec)."""
    db = _db()
    texto = "Implementar autenticacao\nDetalhe: OAuth2 com Google"
    ideia_id = capturar_ideia(db, tipo="tarefa", texto=texto, agora=_AGORA)
    row = obter_ideia(db, ideia_id)
    assert row["titulo"] == "Implementar autenticacao"
    assert row["corpo"] == texto


def test_captura_prioridade_default_100():
    db = _db()
    ideia_id = capturar_ideia(db, tipo="ideia", texto="algo", agora=_AGORA)
    row = obter_ideia(db, ideia_id)
    assert row["prioridade"] == 100


# ---------------------------------------------------------------------------
# E6-03 — CRUD / priorizacao
# ---------------------------------------------------------------------------


def test_listar_ideias_por_prioridade_ascendente():
    """/ideias lista por prioridade ascendente."""
    db = _db()
    capturar_ideia(db, tipo="ideia", texto="baixa prio", agora=_AGORA)
    id_alta = capturar_ideia(db, tipo="ideia", texto="alta prio", agora=_AGORA)
    atualizar_prioridade(db, id_alta, 5, agora=_AGORA)

    lista = listar_ideias(db)
    assert lista[0]["id"] == id_alta  # menor numero = mais urgente = primeiro
    assert lista[1]["prioridade"] == 100


def test_listar_ideias_default_exclui_descartadas_e_arquivadas():
    db = _db()
    id_ativa = capturar_ideia(db, tipo="ideia", texto="ativa", agora=_AGORA)
    id_desc = capturar_ideia(db, tipo="ideia", texto="descartada", agora=_AGORA)
    id_arq = capturar_ideia(db, tipo="ideia", texto="arquivada", agora=_AGORA)

    descartar_ideia(db, id_desc, agora=_AGORA)
    arquivar_ideia(db, id_arq, agora=_AGORA)

    lista = listar_ideias(db)
    ids_listados = [r["id"] for r in lista]
    assert id_ativa in ids_listados
    assert id_desc not in ids_listados
    assert id_arq not in ids_listados


def test_listar_ideias_por_estado_filtrado():
    db = _db()
    id_arq = capturar_ideia(db, tipo="ideia", texto="arquivada", agora=_AGORA)
    arquivar_ideia(db, id_arq, agora=_AGORA)
    capturar_ideia(db, tipo="ideia", texto="ativa", agora=_AGORA)

    lista = listar_ideias(db, estado="arquivada")
    assert len(lista) == 1
    assert lista[0]["id"] == id_arq


def test_obter_ideia_inexistente_retorna_none():
    db = _db()
    assert obter_ideia(db, 9999) is None


def test_atualizar_prioridade():
    """/ideia 1 prio 5 -> prioridade atualizada."""
    db = _db()
    ideia_id = capturar_ideia(db, tipo="ideia", texto="teste", agora=_AGORA)
    atualizar_prioridade(db, ideia_id, 5, agora=_AGORA)
    row = obter_ideia(db, ideia_id)
    assert row["prioridade"] == 5


def test_editar_corpo():
    """/ideia 1 editar <texto> -> corpo atualizado; titulo = 1a linha."""
    db = _db()
    ideia_id = capturar_ideia(db, tipo="ideia", texto="titulo original", agora=_AGORA)
    editar_corpo(db, ideia_id, "novo titulo\ndetalhes adicionais", agora=_AGORA)
    row = obter_ideia(db, ideia_id)
    assert row["titulo"] == "novo titulo"
    assert row["corpo"] == "novo titulo\ndetalhes adicionais"


def test_concluir_ideia():
    """/ideia 1 feito -> estado=ativada."""
    db = _db()
    ideia_id = capturar_ideia(db, tipo="ideia", texto="concluir", agora=_AGORA)
    concluir_ideia(db, ideia_id, agora=_AGORA)
    row = obter_ideia(db, ideia_id)
    assert row["estado"] == "ativada"


def test_arquivar_ideia():
    """/ideia 1 arquivar -> estado=arquivada."""
    db = _db()
    ideia_id = capturar_ideia(db, tipo="ideia", texto="arquivar", agora=_AGORA)
    arquivar_ideia(db, ideia_id, agora=_AGORA)
    row = obter_ideia(db, ideia_id)
    assert row["estado"] == "arquivada"


def test_descartar_ideia():
    """/ideia 1 remover -> estado=descartada (soft delete); some da lista default."""
    db = _db()
    ideia_id = capturar_ideia(db, tipo="ideia", texto="descartar", agora=_AGORA)
    descartar_ideia(db, ideia_id, agora=_AGORA)
    row = obter_ideia(db, ideia_id)
    assert row["estado"] == "descartada"

    lista = listar_ideias(db)
    ids = [r["id"] for r in lista]
    assert ideia_id not in ids


def test_multiplas_ideias_reordenam_por_prioridade():
    """Apos mudar prioridade, a lista reordena corretamente."""
    db = _db()
    id1 = capturar_ideia(db, tipo="ideia", texto="ideia 1", agora=_AGORA)
    id2 = capturar_ideia(db, tipo="ideia", texto="ideia 2", agora=_AGORA)
    id3 = capturar_ideia(db, tipo="ideia", texto="ideia 3", agora=_AGORA)

    atualizar_prioridade(db, id1, 50, agora=_AGORA)
    atualizar_prioridade(db, id2, 10, agora=_AGORA)
    atualizar_prioridade(db, id3, 200, agora=_AGORA)

    lista = listar_ideias(db)
    ids_ordem = [r["id"] for r in lista]
    assert ids_ordem == [id2, id1, id3]
