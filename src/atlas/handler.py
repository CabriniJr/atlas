"""Handler do bot — o "cérebro" da Camada 0 (zero IA).

Recebe o texto de uma mensagem e devolve a resposta. Comandos explícitos e
registro rápido de atividades são resolvidos sem IA (P1/P2). É a fatia funcional
mínima do roteador (§roteamento; ADR-0008 detalha a versão completa).
"""

from __future__ import annotations

from datetime import datetime

from atlas.comandos import texto_ajuda, texto_boas_vindas
from atlas.db import Database
from atlas.debug import responder_debug
from atlas.pool import responder_pool

# Palavras-chave → domínio (inferência barata, 0 IA). Versão completa: ADR-0008.
_DOMINIOS = {
    "fisico": ("treino", "academia", "perna", "peito", "costas", "agachamento", "corrida"),
    "estudo": ("estudei", "estudo", "leetcode", "álgebra", "algebra", "curso", "aula"),
    "leitura": ("li ", "página", "pagina", "livro", "capítulo", "capitulo"),
}


def responder(texto: str, db: Database, agora: datetime) -> str:
    """Resolve uma mensagem e devolve a resposta (sempre Camada 0)."""
    texto = texto.strip()

    if texto in ("/start", "/ajuda", "/help"):
        if texto == "/start":
            return texto_boas_vindas()
        return texto_ajuda()

    if texto == "/status":
        return _status(db, agora)

    if texto == "/note" or texto.startswith("/note "):
        return _nota_livre(texto, db, agora)

    # Debug session (diagnostics CLI over Telegram).
    resposta_debug = responder_debug(texto, db, agora)
    if resposta_debug is not None:
        return resposta_debug

    # Pool commands (E6): /idea, /task, /routine, /pool.
    resposta_pool = responder_pool(texto, db, agora)
    if resposta_pool is not None:
        return resposta_pool

    if texto.startswith("/"):
        return "❓ unknown command. See /help"

    return _registrar(texto, db, agora)


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


def _registrar(texto: str, db: Database, agora: datetime) -> str:
    dominio = _inferir_dominio(texto)
    db.insert(
        "activities",
        ts=agora.isoformat(),
        dominio=dominio,
        rotina="log",
        texto_cru=texto,
    )
    return f"✓ logged ({dominio})"


def _status(db: Database, agora: datetime) -> str:
    inicio_do_dia = agora.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    total = db.connection.execute(
        "SELECT COUNT(*) AS n FROM activities WHERE ts >= ?", (inicio_do_dia,)
    ).fetchone()["n"]
    abertas = db.connection.execute(
        "SELECT COUNT(*) AS n FROM ideas WHERE estado NOT IN ('descartada','arquivada')"
    ).fetchone()["n"]
    return f"📊 Today: {total} activity record(s) · pool: {abertas} open\nSee /pool or /debug."


def _inferir_dominio(texto: str) -> str:
    minusculo = texto.lower()
    for dominio, palavras in _DOMINIOS.items():
        if any(p in minusculo for p in palavras):
            return dominio
    return "geral"
