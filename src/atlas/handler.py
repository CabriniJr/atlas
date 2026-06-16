"""Handler do bot — o "cérebro" da Camada 0 (zero IA).

Recebe o texto de uma mensagem e devolve a resposta. Comandos explícitos e
registro rápido de atividades são resolvidos sem IA (P1/P2). É a fatia funcional
mínima do roteador (§roteamento; ADR-0008 detalha a versão completa).
"""

from __future__ import annotations

from datetime import datetime

from atlas.db import Database

# Palavras-chave → domínio (inferência barata, 0 IA). Versão completa: ADR-0008.
_DOMINIOS = {
    "fisico": ("treino", "academia", "perna", "peito", "costas", "agachamento", "corrida"),
    "estudo": ("estudei", "estudo", "leetcode", "álgebra", "algebra", "curso", "aula"),
    "leitura": ("li ", "página", "pagina", "livro", "capítulo", "capitulo"),
}

_AJUDA = (
    "🧭 *Atlas*\n"
    "Mande uma mensagem curta para registrar (ex.: `treino de perna`).\n\n"
    "Comandos:\n"
    "• /status — registros de hoje\n"
    "• /ajuda — esta mensagem"
)


def responder(texto: str, db: Database, agora: datetime) -> str:
    """Resolve uma mensagem e devolve a resposta (sempre Camada 0)."""
    texto = texto.strip()

    if texto in ("/start", "/ajuda", "/help"):
        if texto == "/start":
            return "👋 Bem-vindo ao *Atlas*.\n\n" + _AJUDA
        return _AJUDA

    if texto == "/status":
        return _status(db, agora)

    if texto.startswith("/"):
        return "Comando desconhecido. Veja /ajuda."

    return _registrar(texto, db, agora)


def _registrar(texto: str, db: Database, agora: datetime) -> str:
    dominio = _inferir_dominio(texto)
    db.insert(
        "activities",
        ts=agora.isoformat(),
        dominio=dominio,
        rotina="log",
        texto_cru=texto,
    )
    return f"✓ registrado ({dominio})"


def _status(db: Database, agora: datetime) -> str:
    inicio_do_dia = agora.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    total = db.connection.execute(
        "SELECT COUNT(*) AS n FROM activities WHERE ts >= ?", (inicio_do_dia,)
    ).fetchone()["n"]
    return f"📊 Hoje: {total} registro(s)."


def _inferir_dominio(texto: str) -> str:
    minusculo = texto.lower()
    for dominio, palavras in _DOMINIOS.items():
        if any(p in minusculo for p in palavras):
            return dominio
    return "geral"
