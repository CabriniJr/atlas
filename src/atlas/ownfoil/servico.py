"""Supervisor do Kind ``Ownfoil`` (ADR-0052): garante o container e reflete o
estado da loja **no recurso** (não em memória de processo), como o Kind Torrent.

Singleton: existe **um** recurso ``Ownfoil/loja`` cujo ``status`` (rodando, nº de
jogos, último check) alimenta o ``atlas_status`` e o Telegram. Estado no repo (P4):
sobrevive a restart e aparece no dashboard. Zero IA.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Protocol

from atlas.core.resource import Resource
from atlas.core.store import ResourceStore

_log = logging.getLogger("atlas.ownfoil")

KIND = "Ownfoil"
NOME = "loja"


class _Cliente(Protocol):
    def garantir_no_ar(self) -> bool: ...
    def status(self) -> dict[str, Any]: ...


def _aplicar(store: ResourceStore, status: dict[str, Any], agora: datetime) -> Resource:
    res = Resource(
        kind=KIND,
        name=NOME,
        labels={"area": "jogos", "servico": "tinfoil"},
        spec={
            "acervo": status.get("acervo"),
            "porta": status.get("porta"),
            "imagem": status.get("imagem"),
        },
        status=status,
    )
    return store.apply(res, agora)


def sincronizar(store: ResourceStore, cliente: _Cliente, agora: datetime) -> Resource:
    """Lê o estado observável do container e persiste no recurso ``Ownfoil/loja``."""
    status = dict(cliente.status())
    status["ultimo_check"] = agora.isoformat()
    return _aplicar(store, status, agora)


def garantir(store: ResourceStore, cliente: _Cliente, agora: datetime) -> Resource:
    """Sobe o container (idempotente) e sincroniza o recurso. Se não subir, marca
    ``erro`` no status (mas não levanta — o supervisor tenta de novo no próximo tick)."""
    no_ar = False
    try:
        no_ar = cliente.garantir_no_ar()
    except Exception as e:  # noqa: BLE001
        _log.warning("Ownfoil: falha ao garantir container: %s", e)
    status = dict(cliente.status())
    status["ultimo_check"] = agora.isoformat()
    if not no_ar:
        status["erro"] = "container não respondeu (WebUI fora do ar)"
    return _aplicar(store, status, agora)


def status_atual(store: ResourceStore) -> dict[str, Any] | None:
    """Status persistido da loja (para o MCP/dashboard). ``None`` se nunca subiu."""
    res = store.get(KIND, NOME)
    return dict(res.status) if res is not None else None


def resumo(store: ResourceStore) -> str:
    """Linha humana do estado da loja, para Telegram/``atlas_status``."""
    st = status_atual(store)
    if st is None:
        return "🎮 Ownfoil: ainda não iniciado."
    icone = "🟢 no ar" if st.get("rodando") else "🔴 parado"
    jogos = st.get("jogos", 0)
    linha = f"🎮 Ownfoil {icone} — {jogos} jogo(s) na loja (porta {st.get('porta')})"
    if st.get("erro"):
        linha += f"\n   ⚠️ {st['erro']}"
    return linha
