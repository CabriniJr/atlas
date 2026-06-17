"""Collect da rotina de estudos (E3-02).

Agrega registros /reg #estudo, timer entries de estudo e tracker entries
de domínio estudo do dia. Retorna resumo sem IA (modelo=none).
"""

from __future__ import annotations

from atlas.executor import CollectResult, ContextoExecucao
from atlas.rotinas import registrar


@registrar("estudos")
def collect(ctx: ContextoExecucao) -> CollectResult:
    db = ctx.db
    if db is None:
        return CollectResult(data={"_saida": "⚠️ estudos: db não disponível"})

    inicio = ctx.agora.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

    # Notas livres de estudo (/reg #estudo ...)
    regs = db.connection.execute(
        "SELECT texto_cru FROM activities WHERE dominio='estudo' AND ts >= ? ORDER BY ts ASC",
        (inicio,),
    ).fetchall()

    # Timers de estudo (nome contém 'estudo' ou 'aula' ou 'leitura')
    timers = db.connection.execute(
        "SELECT json_extract(dados_json,'$.timer') AS nome, "
        "       json_extract(dados_json,'$.duration_min') AS minutos "
        "FROM activities WHERE rotina='timer' AND ts >= ? "
        "  AND (json_extract(dados_json,'$.timer') LIKE '%estudo%' "
        "    OR json_extract(dados_json,'$.timer') LIKE '%aula%' "
        "    OR json_extract(dados_json,'$.timer') LIKE '%leitura%')"
        "ORDER BY ts ASC",
        (inicio,),
    ).fetchall()

    # Tracker entries de domínio estudo
    tracks = db.connection.execute(
        "SELECT json_extract(dados_json,'$.tracker') AS tracker, "
        "       json_extract(dados_json,'$.valor') AS valor, "
        "       json_extract(dados_json,'$.unidade') AS unidade "
        "FROM activities WHERE rotina='tracking' AND dominio='estudo' AND ts >= ? "
        "ORDER BY ts ASC",
        (inicio,),
    ).fetchall()

    total_min = sum((t["minutos"] or 0) for t in timers)

    if not regs and not timers and not tracks:
        return CollectResult(data={"_saida": "📚 Estudos · nenhum registro hoje."})

    linhas = [f"📚 Estudos · {ctx.agora.strftime('%d/%m/%Y')}"]

    if timers:
        linhas.append(f"\n⏱ Tempo de estudo: {total_min}min ({len(timers)} sessão/ões)")
        for t in timers:
            linhas.append(f"  • {t['nome']}: {t['minutos']}min")

    if regs:
        linhas.append(f"\n📝 Notas ({len(regs)}):")
        for r in regs:
            linhas.append(f"  • {r['texto_cru']}")

    if tracks:
        linhas.append(f"\n📊 Trackers ({len(tracks)}):")
        for t in tracks:
            unidade = t["unidade"] or ""
            linhas.append(f"  • {t['tracker']}: {t['valor']}{unidade}")

    return CollectResult(data={"_saida": "\n".join(linhas)})
