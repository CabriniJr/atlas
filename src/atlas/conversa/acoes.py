"""Registry de ações da camada NL global (ADR-0050).

Uma ação é ``fn(store, ctx, alvos, args) -> ResultadoAcao``. Só existem ações
**built-in** (aqui) e **collects** registradas (runner ``rodar_collect``) — nunca
shell arbitrário de mensagem (decisão do ADR-0050; script-primeiro, P2).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from atlas.conversa.descritores import descritor_de, normalizar
from atlas.core.resource import Resource

# limite prático do sendDocument do bot (~50 MB); abaixo disso enviamos o arquivo.
LIMITE_TELEGRAM_BYTES = 49 * 1024 * 1024


@dataclass
class ResultadoAcao:
    texto: str = ""
    arquivos: list[str] = field(default_factory=list)


# ── progresso-global ─────────────────────────────────────────────────────────
def progresso_global(store, ctx, alvos: list[Resource], args: dict) -> ResultadoAcao:
    """Uma linha por recurso ATIVO (baixando/traduzindo/sincronizando), de todos
    os kinds do selector. Ordena por kind e nome; header com a contagem."""
    linhas: list[str] = []
    for r in sorted(alvos, key=lambda x: (x.kind, x.name)):
        d = descritor_de(r.kind)
        if d is None:
            continue
        linha = d.linha_progresso(r)
        if linha:
            linhas.append(linha)
    if not linhas:
        return ResultadoAcao(texto="✅ nada em andamento agora.")
    cab = f"⏳ {len(linhas)} em andamento"
    return ResultadoAcao(texto=cab + "\n" + "\n".join(linhas))


# ── buscar (nome solto) ──────────────────────────────────────────────────────
def buscar(store, ctx, alvos: list[Resource], args: dict) -> ResultadoAcao:
    """Substring (sem acento/caixa) no nome de exibição de cada alvo; agrupa por
    kind e sugere a ação natural. ``args['termo']`` é o texto da mensagem."""
    termo = normalizar(args.get("termo", ""))
    if not termo:
        return ResultadoAcao(texto="")
    grupos: dict[str, list[tuple[str, str]]] = {}
    for r in alvos:
        d = descritor_de(r.kind)
        if d is None:
            continue
        nome = d.nome_exibicao(r)
        if termo in normalizar(nome):
            grupos.setdefault(r.kind, []).append((nome, d.acao_sugerida))
    if not grupos:
        return ResultadoAcao(texto="")  # nada casou → roteador cai no handler base
    _icone = {"Torrent": "📦", "Traducao": "📖", "Repo": "📁", "Doc": "📄"}
    partes = [f"🔎 resultados para “{args.get('termo', '').strip()}”:"]
    for kind in sorted(grupos):
        partes.append(f"{_icone.get(kind, '•')} {kind}:")
        for nome, acao in sorted(set(grupos[kind])):
            partes.append(f"  • {nome}  →  {acao}")
    return ResultadoAcao(texto="\n".join(partes))


# ── enviar (Traducao pronta) ─────────────────────────────────────────────────
def preparar_envio(saida: str) -> tuple[str, str]:
    """Decide como entregar um arquivo pronto pelo Telegram. Devolve
    ``(modo, detalhe)``: ``("arquivo", caminho)`` se cabe no limite;
    ``("grande", caminho)`` se excede (manda caminho local); ``("ausente", "")``
    se não existe em disco."""
    if not saida or not os.path.isfile(saida):
        return "ausente", ""
    if os.path.getsize(saida) > LIMITE_TELEGRAM_BYTES:
        return "grande", saida
    return "arquivo", saida


def enviar(store, ctx, alvos: list[Resource], args: dict) -> ResultadoAcao:
    """Envia o PDF traduzido de um match. ``args['termo']`` seleciona por nome; se
    ambíguo, lista os candidatos; se grande demais, devolve o caminho local."""
    termo = normalizar(args.get("termo", ""))
    candidatos = []
    for r in alvos:
        if r.kind != "Traducao":
            continue
        d = descritor_de("Traducao")
        if termo and termo not in normalizar(d.nome_exibicao(r)):
            continue
        candidatos.append(r)
    if not candidatos:
        return ResultadoAcao(texto="")
    prontos = [r for r in candidatos if (r.status or {}).get("saida")]
    if not prontos:
        r = candidatos[0]
        fase = (r.status or {}).get("fase", "?")
        d = descritor_de("Traducao")
        return ResultadoAcao(texto=f"⏳ {d.nome_exibicao(r)} ainda não está pronto (fase: {fase}).")
    if len(prontos) > 1:
        d = descritor_de("Traducao")
        nomes = "\n".join(f"  • {d.nome_exibicao(r)}" for r in prontos)
        return ResultadoAcao(texto=f"🤔 achei mais de um — seja específico:\n{nomes}")
    r = prontos[0]
    d = descritor_de("Traducao")
    saida = (r.status or {}).get("saida") or ""
    modo, detalhe = preparar_envio(saida)
    if modo == "arquivo":
        return ResultadoAcao(texto=f"📎 {d.nome_exibicao(r)}", arquivos=[detalhe])
    if modo == "grande":
        return ResultadoAcao(
            texto=f"📦 {d.nome_exibicao(r)} passou do limite do Telegram.\n📁 {detalhe}"
        )
    return ResultadoAcao(texto=f"⚠️ o arquivo de {d.nome_exibicao(r)} sumiu do disco.")


REGISTRY = {
    "progresso-global": progresso_global,
    "buscar": buscar,
    "enviar": enviar,
}


def acao_builtin(nome: str):
    return REGISTRY.get(nome)
