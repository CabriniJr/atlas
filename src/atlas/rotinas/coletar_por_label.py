"""Rotina genérica de coleta por label (feature label-driven collect).

Quando disparada, lê o campo ``rotina.label`` e busca no store todos os
Resources (Tracker, Goal) com ``labels.grupo == label``, montando um prompt
que pede ao usuário para registrar cada item.

Configuração mínima no routine.toml:
    nome = "check-treino"
    label = "treino"          # grupo de recursos a coletar
    agenda = "0 20 * * 1,2,4"
    modelo = "none"
    saida = "telegram"
    ativa = true
"""

from __future__ import annotations

from atlas.core.store import ResourceStore
from atlas.executor import CollectResult, ContextoExecucao
from atlas.rotinas import registrar


@registrar("coletar-por-label")
def collect(ctx: ContextoExecucao) -> CollectResult:
    rotina = ctx.rotina
    label: str = getattr(rotina, "label", None) or rotina.nome
    store: ResourceStore | None = getattr(ctx, "store", None)

    if store is None:
        return CollectResult(data={"_saida": f"⏰ {rotina.nome} · store não disponível."})

    seletor = {"grupo": label}
    trackers = [r for r in store.list("Tracker", labels=seletor) if r.spec.get("active", True)]
    goals = store.list("Goal", labels=seletor)

    if not trackers and not goals:
        return CollectResult(
            data={
                "_saida": (
                    f"⏰ {label.capitalize()} · nenhum recurso configurado com grupo={label}.\n"
                    f"Adicione com: /apply Tracker <nome> labels.grupo={label}"
                )
            }
        )

    dia_semana = ctx.agora.strftime("%A").lower()
    _DIAS = {
        "monday": "segunda",
        "tuesday": "terça",
        "wednesday": "quarta",
        "thursday": "quinta",
        "friday": "sexta",
        "saturday": "sábado",
        "sunday": "domingo",
    }
    dia_pt = _DIAS.get(dia_semana, dia_semana)
    linhas = [f"⏰ {label.capitalize()} — {dia_pt}"]

    if trackers:
        linhas.append("\n📊 Registre agora:")
        for t in trackers:
            syntax = t.spec.get("syntax", f"{t.name}:")
            unit = t.spec.get("unit", "")
            ultimo = t.status.get("ultimo_valor") if t.status else None
            dica = f"  • {syntax} ___  ({unit})" if unit else f"  • {syntax} ___"
            if ultimo is not None:
                dica += f"  ← último: {ultimo}"
            linhas.append(dica)

    if goals:
        linhas.append("\n🎯 Metas do grupo:")
        for g in goals:
            progresso = g.status.get("progresso", "?") if g.status else "?"
            atual = g.status.get("atual", "") if g.status else ""
            target = g.spec.get("target", "")
            unit = g.spec.get("unit", "")
            atual_str = f"{atual}{unit}" if atual != "" else "?"
            target_str = f"{target}{unit}" if target != "" else "?"
            linhas.append(f"  • {g.name}: {atual_str} → {target_str}  [{progresso}]")
            linhas.append(f"    atualizar: /goal check {g.name}")

    linhas.append("\nResponda com a sintaxe acima ou /reg #fisico <nota>")
    return CollectResult(data={"_saida": "\n".join(linhas)})
