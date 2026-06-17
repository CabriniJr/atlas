"""Handler do bot — o "cérebro" da Camada 0 (zero IA).

Recebe o texto de uma mensagem e devolve a resposta. Comandos explícitos e
registro com intenção explícita são resolvidos sem IA (P1/P2). É a fatia
funcional mínima do roteador (§roteamento; ADR-0008 detalha a versão completa).

Barreira de entrada (E1-11 / ADR-0013): texto livre sem trigger, micro-sintaxe
ou /reg NÃO grava nada — devolve ajuda. Só a intenção explícita do usuário gera
registro.
"""

from __future__ import annotations

from datetime import datetime

from atlas.alarmes import responder_alarmes
from atlas.comandos import texto_ajuda, texto_boas_vindas
from atlas.controle import responder_controle
from atlas.core.store import ResourceStore
from atlas.db import Database
from atlas.debug import responder_debug
from atlas.docs_cmd import responder_docs
from atlas.metas import responder_metas
from atlas.pool import responder_pool
from atlas.timer import responder_timer
from atlas.trackers import registrar_por_sintaxe, responder_trackers
from atlas.verbos import responder_verbos

_AJUDA_BARREIRA = (
    "Não entendi o que registrar.\n"
    "• Use a sintaxe de um tracker (ex.: weight: 82.3).\n"
    "• Ou /reg <texto> para uma nota livre.\n"
    "• /trackers lista o que dá pra registrar · /help mostra os comandos."
)

# Domínios aceitos em /reg #<domínio>. Extensível conforme trackers crescem.
_DOMINIOS_VALIDOS = {"sono", "saude", "fisico", "estudo", "leitura", "trabalho", "geral"}


def responder(texto: str, db: Database, agora: datetime, store: ResourceStore | None = None) -> str:
    """Resolve uma mensagem e devolve a resposta (sempre Camada 0)."""
    texto = texto.strip()
    if not texto:
        return _AJUDA_BARREIRA

    if texto in ("/start", "/ajuda", "/help"):
        if texto == "/start":
            return texto_boas_vindas()
        return texto_ajuda()

    # Documentação inline: /docs [topic]
    resposta_docs = responder_docs(texto, agora, store=store)
    if resposta_docs is not None:
        return resposta_docs

    if texto == "/status":
        return _status(db, agora)

    if texto == "/note" or texto.startswith("/note "):
        return _nota_livre(texto, db, agora)

    if texto == "/reg" or texto.startswith("/reg "):
        return _reg(texto, db, agora)

    # Verbos kubectl-like (E0-03): /get /list /describe /apply /delete.
    if store is not None:
        resposta_verbos = responder_verbos(texto, store, agora)
        if resposta_verbos is not None:
            return resposta_verbos

    # Debug session (diagnostics CLI over Telegram).
    resposta_debug = responder_debug(texto, db, agora)
    if resposta_debug is not None:
        return resposta_debug

    # Routine control (E5-02): /routines, /routine, /run, /activate, /deactivate.
    resposta_ctrl = responder_controle(texto, db, agora, store=store)
    if resposta_ctrl is not None:
        return resposta_ctrl

    # Alarms (E5-07): /alarm, /alarms.
    resposta_alarme = responder_alarmes(texto, db, agora, store=store)
    if resposta_alarme is not None:
        return resposta_alarme

    # Timer kind: /timer start|finish|status <name> / /timers
    resposta_timer = responder_timer(texto, db, agora, store=store)
    if resposta_timer is not None:
        return resposta_timer

    # Goals (E3-04): /goal set|status|check|done / /goals
    resposta_meta = responder_metas(texto, db, agora, store=store)
    if resposta_meta is not None:
        return resposta_meta

    # Pool commands (E6): /idea, /task, /queue, /pool.
    resposta_pool = responder_pool(texto, db, agora, store=store)
    if resposta_pool is not None:
        return resposta_pool

    # Trackers (E5-04/05): /track ...
    resposta_track = responder_trackers(texto, db, agora, store=store)
    if resposta_track is not None:
        return resposta_track

    if texto.startswith("/"):
        return "❓ unknown command. See /help"

    # Texto livre: só registra se casa micro-sintaxe de tracker declarado.
    # Sem match → barreira: devolve ajuda, nada grava (E1-11 / ADR-0013).
    resposta_sintaxe = registrar_por_sintaxe(texto, db, agora, store=store)
    if resposta_sintaxe is not None:
        return resposta_sintaxe

    return _AJUDA_BARREIRA


def _reg(texto: str, db: Database, agora: datetime) -> str:
    """Nota livre com intenção explícita. /reg <texto> ou /reg #<domínio> <texto>."""
    corpo = texto[len("/reg") :].strip()
    if not corpo:
        return "Usage: /reg <texto>   ou   /reg #<domínio> <texto>"

    dominio = "geral"
    if corpo.startswith("#"):
        partes = corpo.split(None, 1)
        candidato = partes[0][1:].strip().lower()
        if candidato and candidato in _DOMINIOS_VALIDOS:
            dominio = candidato
            corpo = partes[1].strip() if len(partes) > 1 else ""
        else:
            corpo = corpo  # domínio inválido → mantém tudo como texto, usa "geral"

    if not corpo.strip():
        return "Usage: /reg <texto>   ou   /reg #<domínio> <texto>"

    db.insert(
        "activities",
        ts=agora.isoformat(),
        dominio=dominio,
        rotina="reg",
        texto_cru=corpo,
    )
    return f"📝 logged ({dominio})"


def _nota_livre(texto: str, db: Database, agora: datetime) -> str:
    corpo = texto[len("/note") :].strip()
    if not corpo:
        return "Usage: /note <text>"
    db.insert(
        "activities",
        ts=agora.isoformat(),
        dominio="geral",
        rotina="note",
        texto_cru=corpo,
    )
    return "📝 note logged"


def _status(db: Database, agora: datetime) -> str:
    inicio_do_dia = agora.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    total = db.connection.execute(
        "SELECT COUNT(*) AS n FROM activities WHERE ts >= ?", (inicio_do_dia,)
    ).fetchone()["n"]
    abertas = db.connection.execute(
        "SELECT COUNT(*) AS n FROM ideas WHERE estado NOT IN ('descartada','arquivada')"
    ).fetchone()["n"]
    return f"📊 Today: {total} activity record(s) · pool: {abertas} open\nSee /pool or /debug."
