"""Seed dos ``Binding`` e carimbo de participação por label (ADR-0050).

Os comportamentos da camada NL são recursos ``Binding`` semeados no boot (e
editáveis pela API). Os kinds "de conteúdo" ganham ``labels.interface=telegram``
para entrarem na busca/ações — retro-carimbo idempotente, no espírito do
``scoping.stamp_owner``.
"""

from __future__ import annotations

from datetime import datetime

from atlas.core.resource import Resource
from atlas.core.store import ResourceStore

KIND = "Binding"
LABEL_INTERFACE = "interface"
INTERFACE_TELEGRAM = "telegram"

# kinds que participam da conversa por default (ganham o label no boot).
KINDS_PARTICIPANTES = ("Torrent", "Traducao", "Repo", "Doc")


def _binding(name: str, gatilho: dict, acao: dict, selector: dict) -> Resource:
    return Resource(
        kind=KIND,
        name=name,
        labels={"scope": "system"},
        spec={"gatilho": gatilho, "acao": acao, "selector": selector},
        status={},
    )


def seed_bindings() -> list[Resource]:
    """Os ``Binding`` default da camada NL global."""
    sel = {LABEL_INTERFACE: INTERFACE_TELEGRAM}
    return [
        _binding(
            "progresso",
            {"tipo": "verbo", "valor": "progresso", "aliases": ["status", "progressos", "como ta"]},
            {"tipo": "builtin", "nome": "progresso-global"},
            sel,
        ),
        _binding(
            "enviar",
            {
                "tipo": "verbo",
                "valor": "manda",
                "aliases": ["me manda", "manda o", "envia", "me envia", "puxa", "puxa o"],
            },
            {"tipo": "builtin", "nome": "enviar"},
            {LABEL_INTERFACE: INTERFACE_TELEGRAM, "kind": "Traducao"},
        ),
        _binding(
            "sync",
            {"tipo": "verbo", "valor": "sync", "aliases": ["sincroniza", "sincroniza os repos"]},
            {"tipo": "builtin", "nome": "sync-repos"},
            {LABEL_INTERFACE: INTERFACE_TELEGRAM, "kind": "Repo"},
        ),
        _binding(
            "busca",
            {"tipo": "nome-solto", "valor": ""},
            {"tipo": "builtin", "nome": "buscar"},
            sel,
        ),
    ]


def aplicar_seeds(store: ResourceStore, agora: datetime) -> int:
    """Aplica os seeds ausentes (idempotente). Devolve quantos criou."""
    n = 0
    for b in seed_bindings():
        if store.get(KIND, b.name) is None:
            store.apply(b, agora)
            n += 1
    return n


def carimbar_participacao(store: ResourceStore, agora: datetime) -> int:
    """Carimba ``interface=telegram`` nos recursos dos kinds participantes que
    ainda não têm o label (idempotente). Devolve quantos carimbou."""
    n = 0
    for kind in KINDS_PARTICIPANTES:
        for r in store.list(kind):
            if (r.labels or {}).get(LABEL_INTERFACE) == INTERFACE_TELEGRAM:
                continue
            novo = Resource(
                kind=r.kind,
                name=r.name,
                api_version=r.api_version,
                labels={**(r.labels or {}), LABEL_INTERFACE: INTERFACE_TELEGRAM},
                spec=r.spec,
                status=r.status,
            )
            store.apply(novo, agora)
            n += 1
    return n
