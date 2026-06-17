"""Pool de ideias e desenvolvimento (E6 / E0-04).

ResourceStore é a fonte de verdade para leitura (kinds Idea, Task, RoutineRequest).
A tabela ``ideas`` permanece para o CRUD indexado por id inteiro.
Toda escrita grava em ambos; toda leitura de lista usa o store quando disponível.
"""

from __future__ import annotations

from datetime import datetime

from atlas.core.resource import Resource
from atlas.core.store import ResourceStore
from atlas.db import Database

_CAPTURA_CMD = {
    "/idea": "ideia",
    "/task": "tarefa",
    "/queue": "rotina",
}

_ESTADOS_OCULTOS = ("descartada", "arquivada")

# tipo legado → Kind no ResourceStore (RoutineRequest evita conflito com Routine de TOML)
_TIPO_PARA_KIND = {
    "ideia": "Idea",
    "tarefa": "Task",
    "rotina": "RoutineRequest",
}
_ROTULO = {"ideia": "idea", "tarefa": "task", "rotina": "routine-request"}


# ---------------------------------------------------------------------------
# Operações de dados
# ---------------------------------------------------------------------------


def capturar_ideia(
    db: Database,
    *,
    tipo: str,
    texto: str,
    agora: datetime,
    store: ResourceStore | None = None,
) -> int:
    titulo = texto.strip().splitlines()[0].strip() if texto.strip() else ""
    ts = agora.isoformat()
    ideia_id = db.insert(
        "ideas",
        tipo=tipo,
        titulo=titulo,
        corpo=texto,
        prioridade=100,
        estado="capturada",
        criado_em=ts,
        atualizado_em=ts,
    )
    if store is not None:
        _store_upsert(store, ideia_id, tipo, titulo, texto, 100, "capturada", agora)
    return ideia_id


def obter_ideia(db: Database, ideia_id: int) -> dict | None:
    return db.get("ideas", ideia_id)


def listar_ideias(
    db: Database,
    estado: str | None = None,
    store: ResourceStore | None = None,
) -> list[dict]:
    """Lista itens. Lê do store quando disponível, fallback na tabela legada."""
    if store is not None and estado is None:
        return _listar_do_store(store, db)

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


def atualizar_prioridade(
    db: Database,
    ideia_id: int,
    prioridade: int,
    *,
    agora: datetime,
    store: ResourceStore | None = None,
) -> None:
    _set(db, ideia_id, agora, prioridade=prioridade)
    if store is not None:
        row = obter_ideia(db, ideia_id)
        if row:
            _store_upsert(
                store, ideia_id, row["tipo"], row["titulo"],
                row["corpo"], prioridade, row["estado"], agora
            )


def editar_corpo(
    db: Database,
    ideia_id: int,
    texto: str,
    *,
    agora: datetime,
    store: ResourceStore | None = None,
) -> None:
    titulo = texto.strip().splitlines()[0].strip() if texto.strip() else ""
    _set(db, ideia_id, agora, corpo=texto, titulo=titulo)
    if store is not None:
        row = obter_ideia(db, ideia_id)
        if row:
            _store_upsert(
                store, ideia_id, row["tipo"], titulo,
                texto, row["prioridade"], row["estado"], agora
            )


def concluir_ideia(
    db: Database,
    ideia_id: int,
    *,
    agora: datetime,
    store: ResourceStore | None = None,
) -> None:
    _set(db, ideia_id, agora, estado="ativada")
    _store_set_estado(store, db, ideia_id, "ativada", agora)


def arquivar_ideia(
    db: Database,
    ideia_id: int,
    *,
    agora: datetime,
    store: ResourceStore | None = None,
) -> None:
    _set(db, ideia_id, agora, estado="arquivada")
    _store_set_estado(store, db, ideia_id, "arquivada", agora)


def descartar_ideia(
    db: Database,
    ideia_id: int,
    *,
    agora: datetime,
    store: ResourceStore | None = None,
) -> None:
    _set(db, ideia_id, agora, estado="descartada")
    _store_set_estado(store, db, ideia_id, "descartada", agora)


def _set(db: Database, ideia_id: int, agora: datetime, **campos: object) -> None:
    campos["atualizado_em"] = agora.isoformat()
    cols = ", ".join(f"{c} = ?" for c in campos)
    valores = [*campos.values(), ideia_id]
    db.connection.execute(f"UPDATE ideas SET {cols} WHERE id = ?", valores)
    db.connection.commit()


# ---------------------------------------------------------------------------
# Roteador de comandos (consumido pelo handler)
# ---------------------------------------------------------------------------


def responder_pool(
    texto: str,
    db: Database,
    agora: datetime,
    store: ResourceStore | None = None,
) -> str | None:
    partes = texto.split()
    if not partes:
        return None
    cmd = partes[0]

    if cmd in _CAPTURA_CMD:
        tipo = _CAPTURA_CMD[cmd]
        corpo = texto[len(cmd):].strip()
        if not corpo:
            return f"Usage: {cmd} <text>"
        ideia_id = capturar_ideia(db, tipo=tipo, texto=corpo, agora=agora, store=store)
        rotulo = _ROTULO.get(tipo, tipo)
        return f"✅ {rotulo} #{ideia_id} saved · priority 100\n   inspect: /pool {ideia_id}"

    if cmd == "/pool":
        return _cmd_pool(db, partes, texto, agora, store=store)

    return None


def _cmd_pool(
    db: Database,
    partes: list[str],
    texto: str,
    agora: datetime,
    store: ResourceStore | None = None,
) -> str:
    if len(partes) == 1:
        return _fmt_lista(listar_ideias(db, store=store), titulo="open items")

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
        atualizar_prioridade(db, ideia_id, int(valor), agora=agora, store=store)
        return f"✅ #{ideia_id} priority → {int(valor)}"
    if op == "edit":
        partido = texto.split(None, 3)
        novo = partido[3] if len(partido) > 3 else ""
        if not novo.strip():
            return "Usage: /pool <id> edit <text>"
        editar_corpo(db, ideia_id, novo, agora=agora, store=store)
        return f"✅ #{ideia_id} updated"
    if op == "done":
        concluir_ideia(db, ideia_id, agora=agora, store=store)
        return f"✅ #{ideia_id} marked done (activated)"
    if op == "archive":
        arquivar_ideia(db, ideia_id, agora=agora, store=store)
        return f"📦 #{ideia_id} archived"
    if op == "drop":
        descartar_ideia(db, ideia_id, agora=agora, store=store)
        return f"🗑 #{ideia_id} dropped"
    return (
        f"❓ unknown op '{op}'.\n"
        f"   /pool {ideia_id} prio <n> | edit <text> | done | archive | drop"
    )


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _store_upsert(
    store: ResourceStore,
    ideia_id: int,
    tipo: str,
    titulo: str,
    corpo: str,
    prioridade: int,
    estado: str,
    agora: datetime,
) -> None:
    kind = _TIPO_PARA_KIND.get(tipo, tipo.capitalize())
    name = f"idea-{ideia_id}"
    r = Resource(
        kind=kind,
        name=name,
        labels={"tipo": tipo, "estado": estado},
        spec={"body": corpo, "title": titulo, "priority": prioridade},
        status={"state": estado},
    )
    store.apply(r, agora)


def _store_set_estado(
    store: ResourceStore | None,
    db: Database,
    ideia_id: int,
    estado: str,
    agora: datetime,
) -> None:
    if store is None:
        return
    name = f"idea-{ideia_id}"
    row = obter_ideia(db, ideia_id)
    if row is None:
        return
    kind = _TIPO_PARA_KIND.get(row["tipo"], row["tipo"].capitalize())
    r = store.get(kind, name)
    if r is not None:
        store.patch(r.kind, name, {}, agora)
        store.set_status(r.kind, name, {"state": estado}, agora)


def _listar_do_store(store: ResourceStore, db: Database) -> list[dict]:
    """Lê pool do ResourceStore e converte para o formato dict legado."""
    resultado = []
    _ESTADOS_OK = {"capturada", "priorizada", "gerada", "ativada"}
    for kind in ("Idea", "Task", "RoutineRequest"):
        for r in store.list(kind):
            estado = r.status.get("state", "capturada")
            if estado in _ESTADOS_OK:
                id_num = int(r.name.replace("idea-", "") or 0)
                resultado.append({
                    "id": id_num,
                    "tipo": r.labels.get("tipo", kind.lower()),
                    "titulo": r.spec.get("title", r.name),
                    "corpo": r.spec.get("body", ""),
                    "prioridade": r.spec.get("priority", 100),
                    "estado": estado,
                    "criado_em": r.criado_em,
                    "rotina_alvo": None,
                })
    resultado.sort(key=lambda x: (x["prioridade"], x["id"]))
    return resultado


def _eh_inteiro(valor: str) -> bool:
    try:
        int(valor)
        return True
    except ValueError:
        return False


def _fmt_lista(itens: list[dict], *, titulo: str = "open items") -> str:
    if not itens:
        return "📭 Pool is empty. Capture with /idea, /task or /queue."
    linhas = [
        f"#{i['id']} [p{i['prioridade']}] {_ROTULO.get(i['tipo'], i['tipo'])}: {i['titulo']}"
        for i in itens
    ]
    cab = f"🗂 Pool · {titulo} ({len(itens)})"
    return cab + "\n" + "\n".join(linhas) + "\n→ /pool <id> for detail/actions"


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
