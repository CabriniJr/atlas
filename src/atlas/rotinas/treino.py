"""Collect da rotina de treino físico (E3-01).

Agrega atividades do domínio 'fisico' e tracker entries de fitness do dia.
Retorna um resumo sem IA (modelo=none).
"""

from __future__ import annotations

from atlas.executor import CollectResult, ContextoExecucao
from atlas.rotinas import registrar


@registrar("treino")
def collect(ctx: ContextoExecucao) -> CollectResult:
    db = ctx.db
    if db is None:
        return CollectResult(data={"_saida": "⚠️ treino: db não disponível"})

    inicio = ctx.agora.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

    # Atividades manuais do domínio físico (/reg #fisico ...)
    regs = db.connection.execute(
        "SELECT texto_cru FROM activities WHERE dominio='fisico' AND ts >= ? ORDER BY ts ASC",
        (inicio,),
    ).fetchall()

    # Tracker entries de fitness (qualquer tracker logado com dominio=fisico ou tracker conhecido)
    tracks = db.connection.execute(
        "SELECT json_extract(dados_json,'$.tracker') AS tracker, "
        "       json_extract(dados_json,'$.valor') AS valor, "
        "       json_extract(dados_json,'$.unidade') AS unidade "
        "FROM activities "
        "WHERE rotina='tracking' AND ts >= ? "
        "  AND (dominio='fisico' OR json_extract(dados_json,'$.tracker') IN "
        "       ('treino','peso','corrida','pedalada','natacao'))"
        "ORDER BY ts ASC",
        (inicio,),
    ).fetchall()

    if not regs and not tracks:
        return CollectResult(data={"_saida": "🏋️ Treino · nenhum registro hoje."})

    linhas = [f"🏋️ Treino · {ctx.agora.strftime('%d/%m/%Y')}"]

    if regs:
        linhas.append(f"\n📝 Registros ({len(regs)}):")
        for r in regs:
            linhas.append(f"  • {r['texto_cru']}")

    if tracks:
        linhas.append(f"\n📊 Trackers ({len(tracks)}):")
        for t in tracks:
            unidade = t["unidade"] or ""
            linhas.append(f"  • {t['tracker']}: {t['valor']}{unidade}")

    return CollectResult(data={"_saida": "\n".join(linhas)})
