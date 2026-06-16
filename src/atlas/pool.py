"""Pool de ideias e desenvolvimento (E6 — ADR-0014, spec pool-de-ideias).

Captura de ideias/tarefas/lições pelo chat, com CRUD e priorização — tudo
**0 IA** (determinístico). O laço de desenvolvimento (E6-04) que dispara o
meta-loop NÃO faz parte deste módulo; aqui só vive a entrada e o CRUD.

Funções de dados (puras, recebem :class:`~atlas.db.Database`) e um roteador de
comandos ``responder_pool`` consumido pelo handler.
"""

from __future__ import annotations

from datetime import datetime

from atlas.db import Database

# Tipos válidos de item do pool e o comando que captura cada um.
_CAPTURA_CMD = {
    "/ideia": "ideia",
    "/tarefa": "tarefa",
    "/licao": "tarefa",
    "/rotina_nova": "rotina",
}

# Estados ocultos da listagem default.
_ESTADOS_OCULTOS = ("descartada", "arquivada")


# ---------------------------------------------------------------------------
# Operações de dados
# ---------------------------------------------------------------------------


def capturar_ideia(db: Database, *, tipo: str, texto: str, agora: datetime) -> int:
    """Captura um item no pool. ``titulo`` = 1ª linha; ``corpo`` = texto completo."""
    titulo = texto.strip().splitlines()[0].strip() if texto.strip() else ""
    ts = agora.isoformat()
    return db.insert(
        "ideas",
        tipo=tipo,
        titulo=titulo,
        corpo=texto,
        prioridade=100,
        estado="capturada",
        criado_em=ts,
        atualizado_em=ts,
    )


def obter_ideia(db: Database, ideia_id: int) -> dict | None:
    """Busca um item por id (ou ``None``)."""
    return db.get("ideas", ideia_id)


def listar_ideias(db: Database, estado: str | None = None) -> list[dict]:
    """Lista itens por prioridade ascendente (menor = mais urgente).

    Sem ``estado``: oculta itens ``descartada``/``arquivada``. Com ``estado``:
    filtra exatamente por ele.
    """
    if estado is None:
        placeholders = ", ".join("?" for _ in _ESTADOS_OCULTOS)
        sql = (
            f"SELECT * FROM ideas WHERE estado NOT IN ({placeholders}) "
            "ORDER BY prioridade ASC, id ASC"
        )
        rows = db.connection.execute(sql, _ESTADOS_OCULTOS).fetchall()
    else:
        sql = "SELECT * FROM ideas WHERE estado = ? ORDER BY prioridade ASC, id ASC"
        rows = db.connection.execute(sql, (estado,)).fetchall()
    return [db._row_to_dict(r) for r in rows]


def atualizar_prioridade(db: Database, ideia_id: int, prioridade: int, *, agora: datetime) -> None:
    _set(db, ideia_id, agora, prioridade=prioridade)


def editar_corpo(db: Database, ideia_id: int, texto: str, *, agora: datetime) -> None:
    """Edita o corpo; ``titulo`` volta a ser a 1ª linha do novo texto."""
    titulo = texto.strip().splitlines()[0].strip() if texto.strip() else ""
    _set(db, ideia_id, agora, corpo=texto, titulo=titulo)


def concluir_ideia(db: Database, ideia_id: int, *, agora: datetime) -> None:
    _set(db, ideia_id, agora, estado="ativada")


def arquivar_ideia(db: Database, ideia_id: int, *, agora: datetime) -> None:
    _set(db, ideia_id, agora, estado="arquivada")


def descartar_ideia(db: Database, ideia_id: int, *, agora: datetime) -> None:
    """Soft delete: marca ``descartada`` (some da listagem default)."""
    _set(db, ideia_id, agora, estado="descartada")


def _set(db: Database, ideia_id: int, agora: datetime, **campos: object) -> None:
    """Atualiza colunas de um item e carimba ``atualizado_em``."""
    campos["atualizado_em"] = agora.isoformat()
    cols = ", ".join(f"{c} = ?" for c in campos)
    valores = [*campos.values(), ideia_id]
    db.connection.execute(f"UPDATE ideas SET {cols} WHERE id = ?", valores)
    db.connection.commit()


# ---------------------------------------------------------------------------
# Roteador de comandos (consumido pelo handler)
# ---------------------------------------------------------------------------


def responder_pool(texto: str, db: Database, agora: datetime) -> str | None:
    """Trata comandos do pool. Devolve a resposta, ou ``None`` se não for do pool."""
    partes = texto.split()
    if not partes:
        return None
    cmd = partes[0]

    if cmd == "/ideias":
        estado = partes[1] if len(partes) > 1 else None
        return _fmt_lista(listar_ideias(db, estado=estado))

    if cmd == "/ideia":
        return _cmd_ideia(db, partes, texto, agora)

    if cmd in ("/tarefa", "/licao", "/rotina_nova"):
        tipo = _CAPTURA_CMD[cmd]
        corpo = texto[len(cmd) :].strip()
        if not corpo:
            return f"Uso: {cmd} <texto>"
        ideia_id = capturar_ideia(db, tipo=tipo, texto=corpo, agora=agora)
        return f"✓ capturada #{ideia_id} ({tipo})"

    return None


def _cmd_ideia(db: Database, partes: list[str], texto: str, agora: datetime) -> str:
    uso = (
        "Uso: /ideia <texto>  ·  /ideia <id>  ·  "
        "/ideia <id> prio <n>|editar <txt>|feito|arquivar|remover"
    )
    if len(partes) == 1:
        return uso

    segundo = partes[1]
    if not segundo.isdigit():
        # Captura de ideia nova (texto não começa por id).
        corpo = texto[len("/ideia") :].strip()
        ideia_id = capturar_ideia(db, tipo="ideia", texto=corpo, agora=agora)
        return f"✓ capturada #{ideia_id} (ideia)"

    ideia_id = int(segundo)
    row = obter_ideia(db, ideia_id)
    if row is None:
        return f"Item #{ideia_id} não encontrado. Veja /ideias."

    if len(partes) == 2:
        return _fmt_detalhe(row)

    sub = partes[2]
    if sub == "prio":
        valor = partes[3] if len(partes) > 3 else ""
        if not _eh_inteiro(valor):
            return "Prioridade inválida: informe um número inteiro. Ex.: /ideia 1 prio 5"
        atualizar_prioridade(db, ideia_id, int(valor), agora=agora)
        return f"✓ prioridade de #{ideia_id} = {int(valor)}"
    if sub == "editar":
        partido = texto.split(None, 3)
        novo = partido[3] if len(partido) > 3 else ""
        if not novo.strip():
            return "Uso: /ideia <id> editar <texto>"
        editar_corpo(db, ideia_id, novo, agora=agora)
        return f"✓ #{ideia_id} editada"
    if sub == "feito":
        concluir_ideia(db, ideia_id, agora=agora)
        return f"✓ #{ideia_id} concluída"
    if sub == "arquivar":
        arquivar_ideia(db, ideia_id, agora=agora)
        return f"✓ #{ideia_id} arquivada"
    if sub == "remover":
        descartar_ideia(db, ideia_id, agora=agora)
        return f"✓ #{ideia_id} removida"
    return f"Subcomando '{sub}' desconhecido.\n{uso}"


def _eh_inteiro(valor: str) -> bool:
    try:
        int(valor)
        return True
    except ValueError:
        return False


def _fmt_lista(itens: list[dict]) -> str:
    if not itens:
        return "📭 Pool vazio. Capture com /ideia, /tarefa ou /rotina_nova."
    linhas = [f"#{i['id']} [p{i['prioridade']}] {i['tipo']}: {i['titulo']}" for i in itens]
    return "🗂 Pool de ideias\n" + "\n".join(linhas)


def _fmt_detalhe(row: dict) -> str:
    return (
        f"#{row['id']} ({row['tipo']} · {row['estado']} · prio {row['prioridade']})\n{row['corpo']}"
    )
