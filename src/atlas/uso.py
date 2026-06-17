"""Observabilidade de execuções de rotinas — comando /uso (E1-08)."""

from __future__ import annotations

from datetime import datetime, timedelta

from atlas.db import Database


def responder_uso(texto: str, db: Database, agora: datetime) -> str | None:
    partes = texto.strip().split()
    if not partes or partes[0] != "/uso":
        return None

    # /uso [<n>] → últimas n execuções; default: 30 dias
    limite = int(partes[1]) if len(partes) >= 2 and partes[1].isdigit() else None
    janela_dias = 30

    inicio = (agora - timedelta(days=janela_dias)).isoformat()

    if limite:
        rows = db.connection.execute(
            "SELECT rotina, iniciado_em, status, tokens_in, tokens_out, custo_usd "
            "FROM runs ORDER BY id DESC LIMIT ?",
            (limite,),
        ).fetchall()
    else:
        rows = db.connection.execute(
            "SELECT rotina, iniciado_em, status, tokens_in, tokens_out, custo_usd "
            "FROM runs WHERE iniciado_em >= ? ORDER BY id DESC",
            (inicio,),
        ).fetchall()

    if not rows:
        label = f"últimas {limite}" if limite else f"últimos {janela_dias} dias"
        return f"📊 /uso — {label}\nNenhuma execução registrada ainda."

    # Agrega por rotina
    por_rotina: dict[str, dict] = {}
    total_tok_in = total_tok_out = 0
    total_custo = 0.0
    for r in rows:
        nome = r["rotina"]
        if nome not in por_rotina:
            por_rotina[nome] = {"n": 0, "ok": 0, "tok_in": 0, "tok_out": 0, "custo": 0.0}
        d = por_rotina[nome]
        d["n"] += 1
        if r["status"] == "ok":
            d["ok"] += 1
        tok_in = r["tokens_in"] or 0
        tok_out = r["tokens_out"] or 0
        custo = r["custo_usd"] or 0.0
        d["tok_in"] += tok_in
        d["tok_out"] += tok_out
        d["custo"] += custo
        total_tok_in += tok_in
        total_tok_out += tok_out
        total_custo += custo

    label = f"últimas {limite} runs" if limite else f"últimos {janela_dias} dias"
    linhas = [f"📊 Uso de rotinas — {label} ({len(rows)} execuções)\n"]

    for nome, d in sorted(por_rotina.items(), key=lambda x: -x[1]["n"]):
        taxa = f"{d['ok']}/{d['n']}"
        tok = f"  {d['tok_in']}↑{d['tok_out']}↓ tok" if d["tok_in"] or d["tok_out"] else ""
        custo_str = f"  ${d['custo']:.4f}" if d["custo"] else ""
        linhas.append(f"• {nome}  [{taxa} ok]{tok}{custo_str}")

    if total_custo:
        linhas.append(f"\nTotal: {total_tok_in}↑ {total_tok_out}↓ tok  ${total_custo:.4f}")
    elif total_tok_in:
        linhas.append(f"\nTotal: {total_tok_in}↑ {total_tok_out}↓ tok")

    return "\n".join(linhas)
