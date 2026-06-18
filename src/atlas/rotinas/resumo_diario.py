"""Collect da rotina resumo-diario (E2-01).

Coleta atividades, tracker entries, goals com progresso, timers do dia e
pool aberto. Usa o store quando disponível para dados mais ricos; fallback
para as tabelas legadas. Camada 0 — zero IA.
"""

from __future__ import annotations

from datetime import datetime

from atlas.executor import CollectResult, ContextoExecucao
from atlas.rotinas import registrar


@registrar("resumo-diario")
def coletar(ctx: ContextoExecucao) -> CollectResult:
    db = ctx.db
    store = getattr(ctx, "store", None)
    agora: datetime = ctx.agora

    if db is None:
        return CollectResult(data={"_saida": "⚠️ resumo-diario: db indisponível."})

    inicio_dia = agora.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    linhas: list[str] = [f"📋 Resumo de {agora.strftime('%d/%m/%Y')}\n"]

    # ── Atividades do dia ────────────────────────────────────────────────────
    atividades = db.connection.execute(
        "SELECT dominio, rotina, texto_cru, ts FROM activities WHERE ts >= ? ORDER BY ts",
        (inicio_dia,),
    ).fetchall()
    acts_reais = [a for a in atividades if a["rotina"] not in ("tracking", "timer")]
    if acts_reais:
        linhas.append(f"📝 Registros ({len(acts_reais)}):")
        for a in acts_reais[:6]:
            linhas.append(f"  [{a['dominio']}] {a['texto_cru'][:60]}")
        if len(acts_reais) > 6:
            linhas.append(f"  … e mais {len(acts_reais) - 6}")
    else:
        linhas.append("📝 Nenhum registro textual hoje.")

    # ── Trackers: lê do store (último valor + histórico do dia) ─────────────
    linhas.append("")
    tracker_rows = db.connection.execute(
        "SELECT dominio, texto_cru FROM activities"
        " WHERE ts >= ? AND rotina = 'tracking' ORDER BY ts",
        (inicio_dia,),
    ).fetchall()
    if store is not None:
        trackers_ativos = store.list("Tracker", labels={"active": "true"})
        if trackers_ativos:
            linhas.append(f"📈 Trackers ativos ({len(trackers_ativos)}):")
            for t in trackers_ativos:
                last = t.status.get("last_value", "—")
                unit = t.spec.get("unit", "")
                count = t.status.get("count_today", 0)
                tag = f"  {count}× hoje" if count else ""
                linhas.append(f"  {t.name}: {last} {unit}{tag}".rstrip())
        elif tracker_rows:
            _append_tracker_rows(linhas, tracker_rows)
        else:
            linhas.append("📈 Nenhum tracker ativo.")
    elif tracker_rows:
        _append_tracker_rows(linhas, tracker_rows)
    else:
        linhas.append("📈 Sem entradas de tracker hoje.")

    # ── Goals ativos: progresso ──────────────────────────────────────────────
    linhas.append("")
    if store is not None:
        goals_ativos = store.list("Goal", labels={"state": "active"})
        if goals_ativos:
            linhas.append(f"🎯 Metas ({len(goals_ativos)}):")
            for g in goals_ativos:
                target = g.spec.get("target", "?")
                unit = g.spec.get("unit", "")
                current = g.status.get("current", "—")
                progress = g.status.get("progress", "—")
                linhas.append(f"  {g.name}: {current}/{target} {unit}  [{progress}]".rstrip())
        else:
            linhas.append("🎯 Nenhuma meta ativa.")
    else:
        linhas.append("🎯 Metas: store não disponível.")

    # ── Timers concluídos hoje ───────────────────────────────────────────────
    linhas.append("")
    timer_acts = [a for a in atividades if a["rotina"] == "timer"]
    if store is not None:
        timers_done = store.list("Timer", labels={"state": "done"})
        timers_hoje = []
        for t in timers_done:
            fin = t.status.get("finished_at", "")
            if fin and fin >= inicio_dia:
                timers_hoje.append(t)
        if timers_hoje:
            total_min = sum(float(t.status.get("duration_min", 0)) for t in timers_hoje)
            linhas.append(f"⏱ Timers hoje ({len(timers_hoje)}) — {_fmt_min(total_min)} total:")
            for t in timers_hoje:
                dur = t.status.get("duration_min", 0)
                linhas.append(f"  {t.name}: {_fmt_min(float(dur))}")
        elif timer_acts:
            linhas.append(f"⏱ {len(timer_acts)} timer(s) registrado(s) hoje.")
        else:
            linhas.append("⏱ Nenhum timer hoje.")
    elif timer_acts:
        linhas.append(f"⏱ {len(timer_acts)} timer(s) registrado(s) hoje.")
    else:
        linhas.append("⏱ Nenhum timer hoje.")

    # ── Pool aberto ──────────────────────────────────────────────────────────
    linhas.append("")
    if store is not None:
        pool_store = (
            store.list("Idea", labels={"estado": "capturada"})
            + store.list("Idea", labels={"estado": "priorizada"})
            + store.list("Task", labels={"estado": "capturada"})
            + store.list("Task", labels={"estado": "priorizada"})
        )
        pool_store.sort(key=lambda r: r.spec.get("priority", 100))
        if pool_store:
            linhas.append(f"🗂 Pool aberto ({len(pool_store)} itens — top 5):")
            _rotulo = {"Idea": "💡", "Task": "📌", "RoutineRequest": "⚙️"}
            for p in pool_store[:5]:
                title = p.spec.get("title", p.name)[:50]
                linhas.append(f"  {_rotulo.get(p.kind, '•')} {title}")
        else:
            linhas.append("🗂 Pool: vazio.")
    else:
        pool = db.connection.execute(
            "SELECT tipo, titulo FROM ideas"
            " WHERE estado NOT IN ('descartada','arquivada') ORDER BY prioridade ASC, id ASC"
            " LIMIT 5",
        ).fetchall()
        if pool:
            linhas.append(f"🗂 Pool aberto (top {len(pool)}):")
            _rotulo_db = {"ideia": "💡", "tarefa": "📌", "rotina": "⚙️"}
            for p in pool:
                linhas.append(f"  {_rotulo_db.get(p['tipo'], '•')} {p['titulo'][:50]}")
        else:
            linhas.append("🗂 Pool: vazio.")

    # ── Alarmes ativos ───────────────────────────────────────────────────────
    linhas.append("")
    alarmes = db.connection.execute(
        "SELECT horario, mensagem FROM alarms WHERE ativo = 1 ORDER BY horario"
    ).fetchall()
    if alarmes:
        linhas.append(f"⏰ Alarmes ativos ({len(alarmes)}):")
        for al in alarmes[:3]:
            linhas.append(f"  {al['horario']} → {al['mensagem']}")
    else:
        linhas.append("⏰ Nenhum alarme ativo.")

    saida = "\n".join(linhas)
    return CollectResult(data={"_saida": saida})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _append_tracker_rows(linhas: list[str], rows: list) -> None:
    linhas.append(f"📈 Tracker entries hoje ({len(rows)}):")
    for e in rows[:6]:
        cru = e["texto_cru"]
        valor = cru.split(":")[-1].strip() if ":" in cru else cru
        linhas.append(f"  [{e['dominio']}] {valor[:50]}")


def _fmt_min(minutos: float) -> str:
    m = int(minutos)
    if m < 60:
        return f"{m}min"
    return f"{m // 60}h{m % 60:02d}min"
