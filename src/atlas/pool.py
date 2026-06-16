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

# Comando de captura → tipo do item. Termos em inglês (E5-01).
_CAPTURA_CMD = {
    "/idea": "ideia",
    "/task": "tarefa",
    "/routine": "rotina",
}

# Operações de item e a função correspondente (preenchidas após defini-las).

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
    """Route pool commands. Returns the reply, or ``None`` if not a pool command."""
    partes = texto.split()
    if not partes:
        return None
    cmd = partes[0]

    if cmd in _CAPTURA_CMD:
        tipo = _CAPTURA_CMD[cmd]
        corpo = texto[len(cmd) :].strip()
        if not corpo:
            return f"Usage: {cmd} <text>"
        ideia_id = capturar_ideia(db, tipo=tipo, texto=corpo, agora=agora)
        rotulo = _ROTULO.get(tipo, tipo)
        return f"✅ {rotulo} #{ideia_id} saved · priority 100\n   inspect: /pool {ideia_id}"

    if cmd == "/pool":
        return _cmd_pool(db, partes, texto, agora)

    return None


def _cmd_pool(db: Database, partes: list[str], texto: str, agora: datetime) -> str:
    # /pool                 → list open items
    # /pool <state>         → filter by state
    # /pool <id>            → detail
    # /pool <id> prio <n>|edit <text>|done|archive|drop
    if len(partes) == 1:
        return _fmt_lista(listar_ideias(db), titulo="open items")

    segundo = partes[1]
    if not segundo.isdigit():
        return _fmt_lista(listar_ideias(db, estado=segundo), titulo=f"state={segundo}")

    ideia_id = int(segundo)
    row = obter_ideia(db, ideia_id)
    if row is None:
        return f"❓ item #{ideia_id} not found. Try /pool"

    if len(partes) == 2:
        return _fmt_detalhe(row)

    op = partes[2]
    if op == "prio":
        valor = partes[3] if len(partes) > 3 else ""
        if not _eh_inteiro(valor):
            return "⚠️ priority must be an integer. e.g. /pool 1 prio 5"
        atualizar_prioridade(db, ideia_id, int(valor), agora=agora)
        return f"✅ #{ideia_id} priority → {int(valor)}"
    if op == "edit":
        partido = texto.split(None, 3)
        novo = partido[3] if len(partido) > 3 else ""
        if not novo.strip():
            return "Usage: /pool <id> edit <text>"
        editar_corpo(db, ideia_id, novo, agora=agora)
        return f"✅ #{ideia_id} updated"
    if op == "done":
        concluir_ideia(db, ideia_id, agora=agora)
        return f"✅ #{ideia_id} marked done (activated)"
    if op == "archive":
        arquivar_ideia(db, ideia_id, agora=agora)
        return f"📦 #{ideia_id} archived"
    if op == "drop":
        descartar_ideia(db, ideia_id, agora=agora)
        return f"🗑 #{ideia_id} dropped"
    return (
        f"❓ unknown op '{op}'.\n   /pool {ideia_id} prio <n> | edit <text> | done | archive | drop"
    )


# Rótulo amigável por tipo (saída).
_ROTULO = {"ideia": "idea", "tarefa": "task", "rotina": "routine"}


def _eh_inteiro(valor: str) -> bool:
    try:
        int(valor)
        return True
    except ValueError:
        return False


def _fmt_lista(itens: list[dict], *, titulo: str = "open items") -> str:
    if not itens:
        return "📭 Pool is empty. Capture with /idea, /task or /routine."
    linhas = [
        f"#{i['id']} [p{i['prioridade']}] {_ROTULO.get(i['tipo'], i['tipo'])}: {i['titulo']}"
        for i in itens
    ]
    cab = f"🗂 Pool · {titulo} ({len(itens)})"
    rodape = "→ /pool <id> for detail/actions"
    return cab + "\n" + "\n".join(linhas) + "\n" + rodape


def _fmt_detalhe(row: dict) -> str:
    tipo = _ROTULO.get(row["tipo"], row["tipo"])
    linhas = [
        f"#{row['id']} · {tipo} · {row['estado']} · priority {row['prioridade']}",
        f"created: {row['criado_em']}",
        "",
        row["corpo"] or row["titulo"],
        "",
        "actions: prio <n> | edit <text> | done | archive | drop",
    ]
    if row.get("rotina_alvo"):
        linhas.insert(1, f"routine: {row['rotina_alvo']}")
    return "\n".join(linhas)
