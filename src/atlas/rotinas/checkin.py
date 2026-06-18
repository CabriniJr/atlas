"""Rotina de check-in periódico (E3-01 extensão).

Pergunta ao usuário para registrar os trackers ativos.
O usuário responde com a micro-sintaxe dos trackers (ex.: peso: 82.3).
Agenda configurável via /routine checkin set agenda <cron>.
"""

from __future__ import annotations

from atlas.core.store import ResourceStore
from atlas.executor import CollectResult, ContextoExecucao
from atlas.rotinas import registrar


@registrar("checkin")
def collect(ctx: ContextoExecucao) -> CollectResult:
    store: ResourceStore | None = getattr(ctx, "store", None)

    if store is None:
        return CollectResult(data={"_saida": "⏰ Check-in! Use a micro-sintaxe para registrar."})

    trackers = [r for r in store.list("Tracker") if r.spec.get("active", True)]

    if not trackers:
        return CollectResult(
            data={
                "_saida": (
                    "⏰ Check-in!\nNenhum tracker configurado. "
                    "Crie um com /track new <nome> [unidade]"
                )
            }
        )

    linhas = ["⏰ Check-in! Registre agora:"]
    for t in trackers:
        syntax = t.spec.get("syntax", f"{t.name}:")
        unit = t.spec.get("unit", "")
        exemplo = f"{syntax} 42{unit}" if unit else f"{syntax} 42"
        linhas.append(f"  • {t.name} → {exemplo}")

    linhas.append("\nResponda com a sintaxe acima ou /reg <nota>")
    return CollectResult(data={"_saida": "\n".join(linhas)})
