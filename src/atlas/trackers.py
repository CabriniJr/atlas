"""Trackers (E5-04/05 / E0-04).

ResourceStore é a fonte de verdade para leitura (kind="Tracker").
A tabela ``trackers`` permanece para: (a) micro-sintaxe lookup, (b) join
com ``activities``. Toda criação grava em ambos; rm desativa em ambos.
"""

from __future__ import annotations

from datetime import datetime

from atlas.core.resource import Resource
from atlas.core.store import ResourceStore
from atlas.db import Database


def responder_trackers(
    texto: str,
    db: Database,
    agora: datetime,
    store: ResourceStore | None = None,
) -> str | None:
    """Route ``/track`` commands, or ``None`` if not a track command."""
    partes = texto.split()
    if not partes or partes[0] != "/track":
        return None

    if len(partes) == 1:
        return _listar(db, store)

    if partes[1] == "new":
        return _criar(db, partes, agora, store=store)

    nome = partes[1].lower()
    if len(partes) >= 3 and partes[2] == "rm":
        return _remover(db, nome, store=store, agora=agora)
    return _detalhe(db, nome, store=store)


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------


def _criar(
    db: Database,
    partes: list[str],
    agora: datetime,
    store: ResourceStore | None = None,
) -> str:
    if len(partes) < 3:
        return "Usage: /track new <name> [unit]   e.g. /track new weight kg"
    nome = partes[2].lower()
    unidade = partes[3] if len(partes) > 3 else ""
    if _obter_legado(db, nome) is not None:
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
    if store is not None:
        r = Resource(
            kind="Tracker",
            name=nome,
            labels={"domain": "geral", "active": "true"},
            spec={
                "unit": unidade,
                "type": "number",
                "syntax": sintaxe,
                "aggregation": "last",
                "active": True,
            },
            status={"last_value": None, "count_today": 0},
        )
        store.apply(r, agora)
    exemplo = f"{nome}: 42" + (f"   (logs in {unidade})" if unidade else "")
    return f"📈 tracker '{nome}' created. Log with:\n   {exemplo}"


def _listar(db: Database, store: ResourceStore | None) -> str:
    if store is not None:
        recursos = [r for r in store.list("Tracker") if r.spec.get("active", True)]
        if not recursos:
            return "📈 No trackers yet. Create one: /track new weight kg"
        linhas = []
        for r in recursos:
            ult = _ultimo_valor(db, r.name)
            unit = r.spec.get("unit", "")
            syntax = r.spec.get("syntax", f"{r.name}:")
            ultimo = f"last {ult}{unit}" if ult is not None else "no data"
            linhas.append(f"• {r.name} ({syntax} …) — {ultimo}")
        return "📈 Trackers\n" + "\n".join(linhas) + "\n→ /track <name> for history"

    # fallback quando store não disponível
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


def _detalhe(db: Database, nome: str, store: ResourceStore | None = None) -> str:
    if store is not None:
        r = store.get("Tracker", nome)
        if r is None:
            return f"❓ tracker '{nome}' not found. See /track"
        unit = r.spec.get("unit", "")
        syntax = r.spec.get("syntax", f"{nome}:")
    else:
        t = _obter_legado(db, nome)
        if t is None:
            return f"❓ tracker '{nome}' not found. See /track"
        unit, syntax = t["unidade"], t["sintaxe"]

    rows = db.connection.execute(
        "SELECT ts, json_extract(dados_json,'$.valor') AS valor "
        "FROM activities WHERE rotina='tracking' AND json_extract(dados_json,'$.tracker')=? "
        "ORDER BY id DESC LIMIT 10",
        (nome,),
    ).fetchall()
    if not rows:
        return f"📈 {nome} ({unit}) — no entries yet. Log: {syntax} <value>"
    valores = [r["valor"] for r in rows if r["valor"] is not None]
    stats = ""
    if valores:
        media = sum(valores) / len(valores)
        stats = f"\nlast {len(valores)}: avg {media:.2f} · min {min(valores)} · max {max(valores)}"
    hist = "\n".join(f"  {r['ts'][:16]}  {r['valor']}{unit}" for r in rows)
    return f"📈 {nome} ({unit or '-'}){stats}\n{hist}"


def _remover(
    db: Database,
    nome: str,
    store: ResourceStore | None = None,
    agora: datetime | None = None,
) -> str:
    cur = db.connection.execute("UPDATE trackers SET ativo = 0 WHERE nome = ?", (nome,))
    db.connection.commit()
    if cur.rowcount == 0:
        return f"❓ tracker '{nome}' not found. See /track"
    if store is not None and agora is not None:
        r = store.get("Tracker", nome)
        if r is not None:
            store.patch("Tracker", nome, {"active": False}, agora)
            store.set_status("Tracker", nome, {**r.status, "active": False}, agora)
    return f"🗑 tracker '{nome}' deactivated (history kept)"


# ---------------------------------------------------------------------------
# Registro por micro-sintaxe (texto livre)
# ---------------------------------------------------------------------------


def registrar_por_sintaxe(
    texto: str,
    db: Database,
    agora: datetime,
    store: ResourceStore | None = None,
) -> str | None:
    """Se *texto* casa a sintaxe de um tracker ativo, registra e confirma."""
    if store is not None:
        trackers = [r for r in store.list("Tracker") if r.spec.get("active", True)]
        low = texto.lower()
        for r in trackers:
            sintaxe = r.spec.get("syntax", f"{r.name}:").lower()
            if low.startswith(sintaxe):
                bruto = texto[len(r.spec.get("syntax", f"{r.name}:")) :].strip()
                return _registrar_resource(db, r, bruto, texto, agora)
        return None

    # fallback: lê da tabela legada
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


def _registrar_resource(db: Database, r: Resource, bruto: str, texto: str, agora: datetime) -> str:
    valor: object = bruto
    if r.spec.get("type") == "number":
        try:
            valor = float(bruto.replace(",", "."))
        except ValueError:
            return f"⚠️ couldn't read a number for '{r.name}'. e.g. {r.spec.get('syntax')} 42"
    dominio = r.labels.get("domain", "geral")
    db.insert(
        "activities",
        ts=agora.isoformat(),
        dominio=dominio,
        rotina="tracking",
        texto_cru=texto,
        dados_json={"tracker": r.name, "valor": valor, "unidade": r.spec.get("unit", "")},
    )
    return f"✅ {r.name} {valor}{r.spec.get('unit', '') or ''} logged"


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


def _obter_legado(db: Database, nome: str):
    return db.connection.execute("SELECT * FROM trackers WHERE nome = ?", (nome,)).fetchone()


def _ultimo_valor(db: Database, nome: str):
    row = db.connection.execute(
        "SELECT json_extract(dados_json,'$.valor') AS v "
        "FROM activities WHERE rotina='tracking' AND json_extract(dados_json,'$.tracker')=? "
        "ORDER BY id DESC LIMIT 1",
        (nome,),
    ).fetchone()
    return row["v"] if row else None
