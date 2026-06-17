"""Collect da rotina resumo-diario (E2-01).

Coleta atividades, tracker entries, pool aberto e alarmes ativos do dia.
Formata um resumo estruturado sem nenhuma IA (Camada 0).
Registra no dispatcher via @registrar('resumo-diario').
"""

from __future__ import annotations

from datetime import datetime

from atlas.executor import CollectResult, ContextoExecucao
from atlas.rotinas import registrar


@registrar("resumo-diario")
def coletar(ctx: ContextoExecucao) -> CollectResult:
    db = ctx.db
    agora: datetime = ctx.agora

    if db is None:
        return CollectResult(data={"_saida": "⚠️ resumo-diario: db indisponível."})

    inicio_dia = agora.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

    # Atividades do dia
    atividades = db.connection.execute(
        "SELECT dominio, rotina, texto_cru FROM activities WHERE ts >= ? ORDER BY ts",
        (inicio_dia,),
    ).fetchall()

    # Entradas de tracker do dia
    tracker_entries = db.connection.execute(
        "SELECT t.nome, t.unidade, a.texto_cru FROM activities a"
        " JOIN trackers t ON a.rotina = 'tracking' AND a.dominio = t.dominio"
        " WHERE a.ts >= ? ORDER BY a.ts",
        (inicio_dia,),
    ).fetchall()

    # Pool aberto
    pool = db.connection.execute(
        "SELECT tipo, titulo FROM ideas"
        " WHERE estado NOT IN ('descartada','arquivada') ORDER BY prioridade ASC, id ASC"
        " LIMIT 5",
    ).fetchall()

    # Alarmes ativos
    alarmes = db.connection.execute(
        "SELECT horario, mensagem FROM alarms WHERE ativo = 1 ORDER BY horario"
    ).fetchall()

    linhas: list[str] = [f"📋 Resumo de {agora.strftime('%d/%m/%Y')}\n"]

    # Atividades
    acts_reais = [a for a in atividades if a["rotina"] != "tracking"]
    if acts_reais:
        linhas.append(f"📝 Registros ({len(acts_reais)}):")
        for a in acts_reais[:5]:
            linhas.append(f"  [{a['dominio']}] {a['texto_cru'][:60]}")
        if len(acts_reais) > 5:
            linhas.append(f"  ... e mais {len(acts_reais) - 5}")
    else:
        linhas.append("📝 Registros: nenhum hoje.")

    # Trackers
    if tracker_entries:
        linhas.append(f"\n📈 Trackers ({len(tracker_entries)}):")
        for e in tracker_entries[:5]:
            unidade = e["unidade"] or ""
            cru = e["texto_cru"]
            valor = cru.split(":")[-1].strip() if ":" in cru else cru
            linhas.append(f"  {e['nome']}: {valor} {unidade}".rstrip())
    else:
        linhas.append("\n📈 Trackers: sem entradas hoje.")

    # Pool
    if pool:
        linhas.append(f"\n🗂 Pool aberto (top {len(pool)}):")
        _rotulo = {"ideia": "💡", "tarefa": "📌", "rotina": "⚙️"}
        for p in pool:
            linhas.append(f"  {_rotulo.get(p['tipo'], '•')} {p['titulo'][:50]}")
    else:
        linhas.append("\n🗂 Pool: vazio.")

    # Alarmes
    if alarmes:
        linhas.append(f"\n⏰ Alarmes ativos ({len(alarmes)}):")
        for al in alarmes[:3]:
            linhas.append(f"  {al['horario']} → {al['mensagem']}")
    else:
        linhas.append("\n⏰ Alarmes: nenhum.")

    saida = "\n".join(linhas)
    return CollectResult(data={"_saida": saida})
