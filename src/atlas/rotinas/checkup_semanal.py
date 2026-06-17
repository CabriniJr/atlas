"""Rotina de checkup semanal de metas (E3-04).

Roda toda segunda-feira; lê todos os Goals ativos, recalcula progresso
a partir do último valor do tracker vinculado e monta um relatório.
Nenhuma IA — modelo=none.
"""

from __future__ import annotations

from atlas.executor import CollectResult, ContextoExecucao
from atlas.rotinas import registrar


@registrar("checkup-semanal")
def collect(ctx: ContextoExecucao) -> CollectResult:
    store = getattr(ctx, "store", None)
    db = ctx.db

    if store is None:
        return CollectResult(data={"_saida": "⚠️ checkup-semanal: store não disponível"})

    metas_ativas = [r for r in store.list("Goal") if r.labels.get("state") != "done"]

    if not metas_ativas:
        return CollectResult(data={
            "_saida": (
                "🎯 Checkup semanal\n"
                "Nenhuma meta ativa. Crie uma com:\n"
                "  /goal set <nome> target=<val> unit=<u> [tracker=<t>]"
            )
        })

    linhas = ["🎯 Checkup semanal de metas", ""]
    algum_atualizado = False

    for meta in metas_ativas:
        nome = meta.name
        target = meta.spec.get("target", "?")
        unit = meta.spec.get("unit", "")
        tracker = meta.spec.get("tracker")

        # Tenta ler valor atual do tracker vinculado
        current_str = meta.status.get("current", "—")
        progress_str = meta.status.get("progress", "—")

        if tracker and db is not None:
            row = db.connection.execute(
                "SELECT json_extract(dados_json,'$.valor') AS v "
                "FROM activities WHERE rotina='tracking' "
                "  AND json_extract(dados_json,'$.tracker')=? "
                "ORDER BY id DESC LIMIT 1",
                (tracker,),
            ).fetchone()
            if row and row["v"] is not None:
                current = float(row["v"])
                current_str = str(current)
                progress_str = _progresso(
                    current, float(target),
                    meta.spec.get("start"),
                    meta.spec.get("direction", "down"),
                )
                store.set_status("Goal", nome, {
                    **meta.status,
                    "current": current_str,
                    "progress": progress_str,
                    "checked_at": ctx.agora.isoformat(),
                }, ctx.agora)
                algum_atualizado = True

        barra = _barra(progress_str)
        linhas.append(
            f"• {nome}\n"
            f"  {barra}  {progress_str}\n"
            f"  atual={current_str}{unit}  →  alvo={target}{unit}"
            + (f"  (tracker: {tracker})" if tracker else "  ⚠️ sem tracker")
        )

    if algum_atualizado:
        linhas.append("")
        linhas.append("Atualizado a partir dos trackers. /goals para ver tudo.")
    else:
        linhas.append("")
        linhas.append("Use /goal check <nome> para atualizar manualmente.")

    return CollectResult(data={"_saida": "\n".join(linhas)})


def _progresso(current: float, target: float, start: str | None, direction: str) -> str:
    if start is None:
        pct = 100.0 if current == target else 0.0
    else:
        try:
            start_f = float(start)
        except ValueError:
            return "?"
        total = abs(target - start_f)
        if total == 0:
            return "100%" if current == target else "0%"
        if direction == "down":
            done = max(0.0, start_f - current)
        else:
            done = max(0.0, current - start_f)
        pct = min(100.0, done / total * 100)
    return f"{pct:.0f}%"


def _barra(progress_str: str) -> str:
    """Barra ASCII de 10 chars para o progresso."""
    try:
        pct = float(progress_str.rstrip("%"))
    except ValueError:
        return "[??????????]"
    filled = round(pct / 10)
    return "[" + "█" * filled + "░" * (10 - filled) + "]"
