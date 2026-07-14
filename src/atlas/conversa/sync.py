"""Ação ``sync-repos`` da camada NL global (ADR-0050).

"sincroniza os repos" → roda o collect ``repo-sync`` de TODOS os Repo do selector e
devolve um resumo agregado com header = nº total de commits novos. O sync é lento
(rede), então roda em background e manda o agregado por notificação; a resposta
imediata é um ack.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import datetime

from atlas.conversa.acoes import ResultadoAcao
from atlas.core.resource import Resource
from atlas.core.store import ResourceStore

_log = logging.getLogger("atlas.conversa")


def _commits_total(store: ResourceStore, label: str) -> int:
    r = store.get("Repo", label)
    return int(((r.status or {}).get("commits_total") if r else 0) or 0)


def _sincronizar_repo(store: ResourceStore, label: str, agora: datetime) -> tuple[int, str]:
    """Roda o collect ``repo-sync`` de um Repo. Devolve ``(commits_novos, linha)``.

    ``commits_novos`` = delta de ``status.commits_total`` (antes/depois do sync) —
    robusto e sem parsear o texto do collect."""
    from atlas.executor import ContextoExecucao
    from atlas.rotinas import obter
    from atlas.routines import Rotina

    antes = _commits_total(store, label)
    try:
        collect = obter("repo-sync")
        rot = Rotina(nome=label, descricao="", label=label, coletar="repo-sync")
        ctx = ContextoExecucao(agora=agora, rotina=rot, origem="telegram", store=store)
        collect(ctx)
    except Exception as exc:  # noqa: BLE001 — degrada por repo (ADR-0006)
        _log.warning("sync-repos/%s falhou: %s", label, exc)
        return 0, f"  • {label}: ⚠️ {exc}"
    novos = max(0, _commits_total(store, label) - antes)
    linha = f"  • {label}: {novos} commit(s) novos" if novos else f"  • {label}: sem novidades"
    return novos, linha


def agregar_sync(
    store: ResourceStore,
    repos: list[Resource],
    agora: datetime,
    sincronizar_fn: Callable[[ResourceStore, str, datetime], tuple[int, str]] = _sincronizar_repo,
) -> str:
    """Sincroniza cada repo e monta o resumo agregado com header de commits."""
    total = 0
    linhas: list[str] = []
    for r in sorted(repos, key=lambda x: x.name):
        novos, linha = sincronizar_fn(store, r.name, agora)
        total += novos
        linhas.append(linha)
    header = f"🔄 sync de {len(repos)} repo(s) — {total} commit(s) novos"
    return header + "\n" + "\n".join(linhas)


def sync_repos(store, ctx, alvos: list[Resource], args: dict) -> ResultadoAcao:
    """Ação built-in ``sync-repos``: dispara o sync de todos os repos em background
    e devolve um ack; o resumo agregado chega por ``ctx.notificar``."""
    repos = [r for r in alvos if r.kind == "Repo"]
    if not repos:
        return ResultadoAcao(texto="nenhum repositório configurado para sincronizar.")

    def _run() -> None:
        try:
            resumo = agregar_sync(store, repos, ctx.agora)
        except Exception:  # noqa: BLE001
            _log.exception("sync-repos agregado falhou")
            resumo = "⚠️ falha ao sincronizar os repos."
        if ctx.notificar and ctx.chat_id is not None:
            ctx.notificar(ctx.chat_id, resumo)

    threading.Thread(target=_run, daemon=True, name="sync-repos").start()
    return ResultadoAcao(texto=f"🔄 sincronizando {len(repos)} repo(s)… te aviso ao terminar.")


# auto-registro no registry de ações (evita ciclo: acoes não importa sync)
from atlas.conversa import acoes as _acoes  # noqa: E402

_acoes.registrar("sync-repos", sync_repos)
