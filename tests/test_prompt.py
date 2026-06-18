"""TDD — collect genérico 'prompt': chamada de IA configurável por Kind=Prompt.

Qualquer rotina pode chamar IA configurando um recurso Prompt/<label> e
apontando para ele via `coletar = "prompt"` + `label`. Sem hard-code por rotina.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest

import atlas.rotinas.prompt  # noqa: F401 — registra o collect
from atlas.core.resource import Resource
from atlas.core.store import ResourceStore
from atlas.db import Database
from atlas.executor import ContextoExecucao
from atlas.ia import InvocarErro
from atlas.rotinas import obter
from atlas.routines import Rotina

_AGORA = datetime(2026, 6, 17, 9, 0)


@pytest.fixture
def store(tmp_path):
    return ResourceStore(str(tmp_path / "t.db"))


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "t.db"))


def _ctx(store, db, label="resumo-ia"):
    rot = Rotina(nome="r-ia", descricao="d", label=label, coletar="prompt", modelo="none")
    return ContextoExecucao(agora=_AGORA, rotina=rot, origem="agenda", db=db, store=store)


def test_prompt_registrado():
    assert obter("prompt") is not None


def test_prompt_sem_resource_avisa(store, db):
    out = obter("prompt")(_ctx(store, db)).data["_saida"]
    assert "Prompt" in out and ("configur" in out.lower() or "crie" in out.lower())


def test_prompt_invoca_ia_com_template(store, db):
    store.apply(
        Resource(
            kind="Prompt",
            name="resumo-ia",
            labels={},
            spec={"template": "Resuma: {dados}", "model": "claude-haiku-4-5-20251001"},
            status={},
        ),
        _AGORA,
    )
    with patch("atlas.rotinas.prompt.invocar", return_value="resumo gerado") as m:
        out = obter("prompt")(_ctx(store, db)).data["_saida"]
    assert "resumo gerado" in out
    assert m.called
    # usou o modelo configurado
    assert m.call_args.kwargs.get("modelo") == "claude-haiku-4-5-20251001"


def test_prompt_monta_contexto_grupo(store, db):
    store.apply(
        Resource(
            kind="Tracker", name="peso", labels={"grupo": "saude"}, spec={"unit": "kg"}, status={}
        ),
        _AGORA,
    )
    store.apply(
        Resource(
            kind="Prompt",
            name="p",
            labels={},
            spec={"template": "Dados: {dados}", "fonte": "grupo:saude"},
            status={},
        ),
        _AGORA,
    )
    enviado = {}
    with patch(
        "atlas.rotinas.prompt.invocar",
        side_effect=lambda prompt, **kw: enviado.update(p=prompt) or "ok",
    ):
        obter("prompt")(_ctx(store, db, label="p"))
    assert "peso" in enviado["p"]


def test_prompt_persiste_status(store, db):
    store.apply(
        Resource(kind="Prompt", name="p", labels={}, spec={"template": "x"}, status={}), _AGORA
    )
    with patch("atlas.rotinas.prompt.invocar", return_value="saida ia"):
        obter("prompt")(_ctx(store, db, label="p"))
    p = store.get("Prompt", "p")
    assert p.status.get("last_output") == "saida ia"
    assert p.status.get("last_run")


def test_prompt_ia_indisponivel_nao_quebra(store, db):
    store.apply(
        Resource(kind="Prompt", name="p", labels={}, spec={"template": "x"}, status={}), _AGORA
    )
    with patch("atlas.rotinas.prompt.invocar", side_effect=InvocarErro("claude off")):
        out = obter("prompt")(_ctx(store, db, label="p")).data["_saida"]
    assert "indispon" in out.lower() or "claude off" in out
