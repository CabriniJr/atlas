"""Executor do ciclo de vida da rotina (E1-10).

Orquestra as fases ``trigger → collect → gate → analyze → deliver`` de uma
rotina, grava cada execução em ``runs`` (observabilidade) e entrega o resultado
pelo callback ``notificar`` (no bot, o adapter Telegram). Decisões de base:
[ciclo-de-vida-rotina], [ADR-0001] (modos 2a/2b), [ADR-0006] (resiliência).

As fases são **injetadas** (cada uma testável isoladamente). Rotina log-puro
(sem ``collect``/``prompt``) só persiste o ``store`` e entrega uma confirmação;
nenhuma IA é chamada. O invocador de IA (modo 2a) é injetado — o executor não
conhece o `claude -p` (isso é E1-05).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from atlas.db import Database
from atlas.routines import Rotina

_log = logging.getLogger(__name__)


@dataclass
class StoreOp:
    """Uma operação de persistência explícita ([ADR-0004])."""

    entity: str
    fields: dict[str, Any]


@dataclass
class CollectResult:
    """Resultado tipado da fase ``collect`` ([ADR-0004])."""

    data: dict[str, Any] = field(default_factory=dict)
    store: list[StoreOp] = field(default_factory=list)


@dataclass
class ContextoExecucao:
    """Contexto passado às fases da rotina."""

    agora: Any  # datetime
    rotina: Rotina
    origem: str = "manual"  # manual | agenda | mensagem
    payload: str | None = None
    ultimo_run: dict | None = None
    db: Any = None  # Database — disponível para fases collect que precisam de dados
    store: Any = None  # ResourceStore — opcional, para collects que leem do store


@dataclass
class RunResult:
    """Resultado de uma execução; espelha a linha gravada em ``runs``."""

    rotina: str
    status: str  # ok | skipped | failed
    camada: str  # 0 | 2a
    gate_passou: bool | None = None
    ref_saida: str | None = None
    erro: str | None = None


# Tipos das fases injetáveis.
Notificar = Callable[[str], None]
ColetarFn = Callable[[ContextoExecucao], CollectResult]
GateFn = Callable[[dict[str, Any]], bool]
RenderPromptFn = Callable[[dict[str, Any]], str]
InvocarIAFn = Callable[..., str]


def executar(
    ctx: ContextoExecucao,
    db: Database,
    notificar: Notificar,
    *,
    collect: ColetarFn | None = None,
    gate: GateFn | None = None,
    render_prompt: RenderPromptFn | None = None,
    invocar_ia: InvocarIAFn | None = None,
) -> RunResult:
    """Executa uma rotina pelas fases e grava o run. Nunca propaga exceção."""
    rotina = ctx.rotina
    iniciado_em = ctx.agora.isoformat()
    camada = "0"
    gate_passou: bool | None = None
    status = "ok"
    saida: str | None = None
    erro: str | None = None

    try:
        resultado = collect(ctx) if collect is not None else CollectResult()

        # Persistência explícita do que a rotina declarou (o motor não adivinha).
        for op in resultado.store:
            db.insert(op.entity, **op.fields)

        usa_ia = rotina.modelo != "none" and render_prompt is not None and invocar_ia is not None
        if usa_ia:
            gate_passou = gate(resultado.data) if gate is not None else True
            if gate_passou:
                prompt = render_prompt(resultado.data)  # type: ignore[misc]
                saida = invocar_ia(prompt, modelo=rotina.modelo)  # type: ignore[misc]
                camada = "2a"
            else:
                status = "skipped"  # gate não passou: encerra sem IA
        else:
            # Camada 0: usa _saida do collect se disponível, senão confirmação simples.
            saida = resultado.data.get("_saida") or f"✓ rotina '{rotina.nome}' executada."

        # deliver: entrega o resultado (silencioso quando skipped).
        if status != "skipped" and saida is not None:
            notificar(saida)

    except Exception as exc:  # noqa: BLE001 — resiliência: nada derruba o motor (ADR-0006)
        _log.exception("Rotina %s falhou", rotina.nome)
        status = "failed"
        erro = str(exc)
        notificar(f"⚠️ rotina '{rotina.nome}' falhou: {erro}")

    ref_saida = saida if status == "ok" else None
    db.insert(
        "runs",
        rotina=rotina.nome,
        iniciado_em=iniciado_em,
        terminado_em=ctx.agora.isoformat(),
        status=status,
        camada=camada,
        gate_passou=None if gate_passou is None else int(gate_passou),
        ref_saida=ref_saida,
    )
    return RunResult(
        rotina=rotina.nome,
        status=status,
        camada=camada,
        gate_passou=gate_passou,
        ref_saida=ref_saida,
        erro=erro,
    )
