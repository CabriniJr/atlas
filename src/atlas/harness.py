"""Harness de teste de rotina (E1-07 / ADR-0007).

Permite testar as fases de uma rotina com contexto injetado — sem IA real,
sem Telegram, sem banco em disco. Design:

  resultado = harness.testar_collect("treino", db=db_fixture, agora=agora)
  assert "📊" in resultado.data["_saida"]

Também expõe ``testar_gate`` para o predicado booleano e ``inspecionar``
para /run <nome> --test via chat.

Fases testáveis de forma isolada (ADR-0007):
  - collect → puro dado ContextoExecucao injetado
  - gate    → predicado puro (trivialmente isolável)
  - analyze → testa renderização do prompt; IA é mockável via injeção
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from atlas.executor import CollectResult, ContextoExecucao
from atlas.rotinas import obter
from atlas.routines import Rotina

_ROTINA_STUB = Rotina(
    nome="_harness",
    descricao="harness stub",
    agenda="",
    modelo="none",
    ativa=True,
)


@dataclass
class HarnessResult:
    """Resultado completo de uma execução de harness."""

    rotina: str
    collect: CollectResult | None = None
    gate: bool | None = None
    erro: str | None = None
    saida: str = field(default="", init=False)

    def __post_init__(self) -> None:
        if self.collect is not None:
            self.saida = self.collect.data.get("_saida", "")


def testar_collect(
    nome: str,
    *,
    db: Any = None,
    store: Any = None,
    agora: datetime | None = None,
    origem: str = "test",
    payload: str | None = None,
    ultimo_run: dict | None = None,
    rotina: Rotina | None = None,
) -> HarnessResult:
    """Roda apenas a fase *collect* de uma rotina com contexto injetado.

    Parâmetros
    ----------
    nome:      nome registrado com ``@registrar("nome")``
    db:        instância de Database (ou None — rotina deve suportar)
    store:     ResourceStore opcional
    agora:     datetime de referência (default: now)
    """
    fn = obter(nome)
    if fn is None:
        return HarnessResult(rotina=nome, erro=f"rotina '{nome}' não encontrada no registro")

    rot = rotina or Rotina(
        nome=nome,
        descricao=f"harness test for {nome}",
        agenda="",
        modelo="none",
        ativa=True,
    )
    ctx = ContextoExecucao(
        agora=agora or datetime.now(),
        rotina=rot,
        origem=origem,
        payload=payload,
        ultimo_run=ultimo_run,
        db=db,
        store=store,
    )
    try:
        result = fn(ctx)
        return HarnessResult(rotina=nome, collect=result)
    except Exception as exc:  # noqa: BLE001
        return HarnessResult(rotina=nome, erro=f"{type(exc).__name__}: {exc}")


def testar_gate(
    gate_fn: Any,
    collect_data: dict[str, Any],
) -> bool:
    """Avalia um predicado de gate com dados coletados injetados."""
    return bool(gate_fn(collect_data))


def inspecionar(
    nome: str,
    *,
    db: Any = None,
    store: Any = None,
    agora: datetime | None = None,
) -> str:
    """Formata saída do harness para exibição no Telegram (/run <nome> --test)."""
    res = testar_collect(nome, db=db, store=store, agora=agora)
    if res.erro:
        return f"⚠️ harness '{nome}': {res.erro}"
    linhas = [
        f"🧪 Harness: {nome}",
        f"{'─' * 28}",
    ]
    if res.saida:
        linhas.append(res.saida)
    else:
        raw = res.collect.data if res.collect else {}
        for k, v in raw.items():
            linhas.append(f"  {k}: {str(v)[:80]}")
        if not raw:
            linhas.append("  (sem saída)")
    return "\n".join(linhas)
