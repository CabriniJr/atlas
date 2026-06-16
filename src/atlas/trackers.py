"""Trackers (E5-04/05).

Modelo híbrido: o tracker é **dado** (tabela ``trackers``), mas cada entrada é um
registro genérico em ``activities`` (``rotina='tracking'``) — preserva "tudo é
rotina" (P3/P4). A micro-sintaxe declarada (ex.: ``weight:``) dispara o registro
de texto livre, sem IA.

Comandos (inglês/técnicos):
  /track                  list trackers + last value
  /track new <name> [unit]  create a numeric tracker (syntax '<name>:')
  /track <name>           detail + recent history
  /track <name> rm        deactivate

Logging: ``weight: 82.3`` → grava no tracker ``weight``.
"""

from __future__ import annotations

from datetime import datetime

from atlas.db import Database


def responder_trackers(texto: str, db: Database, agora: datetime) -> str | None:
    """Route ``/track`` commands, or ``None`` if not a track command."""
    partes = texto.split()
    if not partes or partes[0] != "/track":
        return None

    if len(partes) == 1:
        return _listar(db)

    if partes[1] == "new":
        return _criar(db, partes, agora)

    nome = partes[1].lower()
    if len(partes) >= 3 and partes[2] == "rm":
        return _remover(db, nome)
    return _detalhe(db, nome)


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------


def _criar(db: Database, partes: list[str], agora: datetime) -> str:
    if len(partes) < 3:
        return "Usage: /track new <name> [unit]   e.g. /track new weight kg"
    nome = partes[2].lower()
    unidade = partes[3] if len(partes) > 3 else ""
    if _obter(db, nome) is not None:
        return f"⚠️ tracker '{nome}' already exists. See /track {nome}"
    sintaxe = f"{nome}:"
    db.insert(
        "trackers",
        nome=nome,
        dominio="geral",
        tipo="numero",
        unidade=unidade,
        sintaxe=sintaxe,
        agregacao="ultimo",
        ativo=1,
        criado_em=agora.isoformat(),
    )
    exemplo = f"{nome}: 42" + (f"   (logs in {unidade})" if unidade else "")
    return f"📈 tracker '{nome}' created. Log with:\n   {exemplo}"


def _listar(db: Database) -> str:
    rows = db.connection.execute(
        "SELECT nome, unidade, sintaxe FROM trackers WHERE ativo = 1 ORDER BY nome"
    ).fetchall()
    if not rows:
        return "📈 No trackers yet. Create one: /track new weight kg"
    linhas = []
    for r in rows:
        ult = _ultimo_valor(db, r["nome"])
        ultimo = f"last {ult}{r['unidade']}" if ult is not None else "no data"
        linhas.append(f"• {r['nome']} ({r['sintaxe']} …) — {ultimo}")
    return "📈 Trackers\n" + "\n".join(linhas) + "\n→ /track <name> for history"


def _detalhe(db: Database, nome: str) -> str:
    t = _obter(db, nome)
    if t is None:
        return f"❓ tracker '{nome}' not found. See /track"
    rows = db.connection.execute(
        "SELECT ts, json_extract(dados_json,'$.valor') AS valor "
        "FROM activities WHERE rotina='tracking' AND json_extract(dados_json,'$.tracker')=? "
        "ORDER BY id DESC LIMIT 10",
        (nome,),
    ).fetchall()
    if not rows:
        return f"📈 {nome} ({t['unidade']}) — no entries yet. Log: {t['sintaxe']} <value>"
    valores = [r["valor"] for r in rows if r["valor"] is not None]
    stats = ""
    if valores:
        media = sum(valores) / len(valores)
        stats = f"\nlast {len(valores)}: avg {media:.2f} · min {min(valores)} · max {max(valores)}"
    hist = "\n".join(f"  {r['ts'][:16]}  {r['valor']}{t['unidade']}" for r in rows)
    return f"📈 {nome} ({t['unidade'] or '-'}){stats}\n{hist}"


def _remover(db: Database, nome: str) -> str:
    cur = db.connection.execute("UPDATE trackers SET ativo = 0 WHERE nome = ?", (nome,))
    db.connection.commit()
    if cur.rowcount == 0:
        return f"❓ tracker '{nome}' not found. See /track"
    return f"🗑 tracker '{nome}' deactivated (history kept)"


# ---------------------------------------------------------------------------
# Registro por micro-sintaxe (texto livre)
# ---------------------------------------------------------------------------


def registrar_por_sintaxe(texto: str, db: Database, agora: datetime) -> str | None:
    """Se *texto* casa a sintaxe de um tracker ativo, registra e confirma.

    Devolve ``None`` se nenhum tracker casa (o handler segue o fluxo normal).
    """
    rows = db.connection.execute(
        "SELECT nome, tipo, unidade, sintaxe, dominio FROM trackers WHERE ativo = 1"
    ).fetchall()
    low = texto.lower()
    for t in rows:
        sintaxe = t["sintaxe"].lower()
        if low.startswith(sintaxe):
            bruto = texto[len(t["sintaxe"]) :].strip()
            return _registrar(db, t, bruto, texto, agora)
    return None


def _registrar(db: Database, t, bruto: str, texto: str, agora: datetime) -> str:
    valor: object = bruto
    if t["tipo"] == "numero":
        try:
            valor = float(bruto.replace(",", "."))
        except ValueError:
            return f"⚠️ couldn't read a number for '{t['nome']}'. e.g. {t['sintaxe']} 42"
    db.insert(
        "activities",
        ts=agora.isoformat(),
        dominio=t["dominio"],
        rotina="tracking",
        texto_cru=texto,
        dados_json={"tracker": t["nome"], "valor": valor, "unidade": t["unidade"]},
    )
    return f"✅ {t['nome']} {valor}{t['unidade'] or ''} logged"


# ---------------------------------------------------------------------------


def _obter(db: Database, nome: str):
    return db.connection.execute("SELECT * FROM trackers WHERE nome = ?", (nome,)).fetchone()


def _ultimo_valor(db: Database, nome: str):
    row = db.connection.execute(
        "SELECT json_extract(dados_json,'$.valor') AS v "
        "FROM activities WHERE rotina='tracking' AND json_extract(dados_json,'$.tracker')=? "
        "ORDER BY id DESC LIMIT 1",
        (nome,),
    ).fetchone()
    return row["v"] if row else None
