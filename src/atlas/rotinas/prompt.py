"""Collect genérico ``prompt`` — chamada de IA configurável por qualquer rotina.

Em vez de embutir a IA dentro do código de uma rotina específica, a chamada é
**plugável**: a configuração vive num recurso ``Kind=Prompt`` e qualquer rotina
aponta para ele com ``coletar = "prompt"`` + ``label``. Assim, criar uma nova
análise por IA não exige código — só um Prompt e uma rotina.

``Prompt/<label>``::

    spec:
      template : texto do prompt. Placeholders: ``{dados}`` e ``{agora}``.
      model    : modelo (default haiku).
      timeout  : segundos (default 90).
      fonte    : como montar ``{dados}``:
                   ``grupo:<g>``  recursos com ``labels.grupo=<g>`` (qualquer kind)
                   ``kind:<K>``   todos os recursos de um Kind
                   ``repo:<r>``   o diff mais recente do repositório ``<r>``
                   ``texto:<t>``  texto fixo
                   (vazio)        sem contexto extra
    status:
      last_run, last_ok, last_output (truncado)

Routine TOML mínimo::

    nome     = "resumo-ia"
    label    = "resumo-ia"     # = nome do Prompt/<label>
    coletar  = "prompt"
    agenda   = "@daily 21:00"
    modelo   = "none"          # a IA roda DENTRO do collect, não pelo executor
    saida    = "telegram"
"""

from __future__ import annotations

import logging

from atlas.core.resource import Resource
from atlas.core.store import ResourceStore
from atlas.executor import CollectResult, ContextoExecucao
from atlas.ia import InvocarErro, invocar
from atlas.rotinas import registrar

_log = logging.getLogger(__name__)

_MODELO_PADRAO = "claude-haiku-4-5-20251001"
_TIMEOUT_PADRAO = 90
_MAX_OUTPUT_STORE = 2000  # chars do output gravados no status
_MAX_CONTEXTO = 6000  # chars de {dados} enviados à IA


@registrar("prompt")
def collect(ctx: ContextoExecucao) -> CollectResult:
    label: str = getattr(ctx.rotina, "label", None) or ctx.rotina.nome
    store: ResourceStore | None = getattr(ctx, "store", None)

    if store is None:
        return CollectResult(data={"_saida": f"⚠️ prompt/{label}: store indisponível."})

    p = store.get("Prompt", label)
    if p is None:
        return CollectResult(
            data={
                "_saida": (
                    f"❓ prompt/{label}: Prompt não configurado.\n"
                    f"Crie com: /apply Prompt {label} "
                    'spec.template="Analise: {dados}" spec.fonte=grupo:saude'
                )
            }
        )

    template = (p.spec.get("template") or "").strip()
    if not template:
        return CollectResult(
            data={"_saida": f"❓ prompt/{label}: spec.template ausente no Prompt/{label}."}
        )

    modelo = p.spec.get("model") or _MODELO_PADRAO
    try:
        timeout = int(p.spec.get("timeout", _TIMEOUT_PADRAO) or _TIMEOUT_PADRAO)
    except (TypeError, ValueError):
        timeout = _TIMEOUT_PADRAO

    dados = _montar_contexto(p.spec.get("fonte", "") or "", store)[:_MAX_CONTEXTO]
    prompt_final = template.replace("{dados}", dados).replace(
        "{agora}", ctx.agora.strftime("%d/%m/%Y %H:%M")
    )

    try:
        resposta = invocar(prompt_final, modelo=modelo, timeout=timeout)
        ok = True
    except InvocarErro as exc:
        _log.warning("prompt/%s — IA indisponível: %s", label, exc)
        resposta = f"_(IA indisponível: {exc})_"
        ok = False
    except Exception as exc:  # noqa: BLE001 — IA é best-effort; nunca derruba o loop
        _log.warning("prompt/%s — erro: %s", label, exc)
        resposta = f"_(erro ao invocar IA: {exc})_"
        ok = False

    _persistir(p, resposta, ok, store, ctx)

    cabecalho = f"🧠 {label} ({ctx.agora.strftime('%d/%m %H:%M')})"
    return CollectResult(data={"_saida": f"{cabecalho}\n\n{resposta}"})


def _montar_contexto(fonte: str, store: ResourceStore) -> str:
    """Monta o texto de ``{dados}`` a partir da ``spec.fonte``."""
    fonte = fonte.strip()
    if not fonte:
        return "(sem dados adicionais)"

    tipo, _, arg = fonte.partition(":")
    tipo = tipo.strip().lower()
    arg = arg.strip()

    if tipo == "texto":
        return arg

    if tipo == "grupo":
        linhas: list[str] = []
        for kind in store.kinds():
            for r in store.list(kind, labels={"grupo": arg}):
                linhas.append(f"- {kind}/{r.name}: spec={r.spec} status={r.status}")
        return "\n".join(linhas) or f"(nenhum recurso com grupo={arg})"

    if tipo == "kind":
        linhas = [f"- {r.name}: spec={r.spec} status={r.status}" for r in store.list(arg)]
        return "\n".join(linhas) or f"(nenhum recurso do kind {arg})"

    if tipo == "repo":
        diffs = store.list("Diff", labels={"repo": arg})
        if not diffs:
            return f"(sem diffs registrados do repo {arg})"
        d = sorted(diffs, key=lambda x: (x.status or {}).get("synced_at", ""))[-1]
        return (
            f"commit {d.spec.get('commit')}: {d.spec.get('subject', '')}\n"
            f"autor: {d.spec.get('author', '')}\n"
            f"{d.spec.get('diff_raw', '')[:3500]}"
        )

    return f"(fonte desconhecida: {fonte})"


def _persistir(
    p: Resource, resposta: str, ok: bool, store: ResourceStore, ctx: ContextoExecucao
) -> None:
    updated = Resource(
        kind="Prompt",
        name=p.name,
        labels=p.labels,
        spec=p.spec,
        status={
            **(p.status or {}),
            "last_run": ctx.agora.isoformat(),
            "last_ok": ok,
            "last_output": resposta[:_MAX_OUTPUT_STORE],
        },
    )
    store.apply(updated, ctx.agora)
