"""Testes do ResourceStore — verbos uniformes sobre SQLite (E0-01, ADR-0015)."""

from __future__ import annotations

from datetime import datetime

import pytest

from atlas.core.resource import Resource
from atlas.core.store import ResourceJaExiste, ResourceNaoEncontrado, ResourceStore

T0 = datetime(2026, 6, 16, 10, 0, 0)
T1 = datetime(2026, 6, 16, 11, 0, 0)


def _store() -> ResourceStore:
    return ResourceStore(":memory:")


def test_create_insere_e_carimba_timestamps():
    s = _store()
    r = s.create(Resource(kind="Tracker", name="peso", spec={"unidade": "kg"}), agora=T0)
    assert r.criado_em == T0.isoformat()
    assert r.atualizado_em == T0.isoformat()
    lido = s.get("Tracker", "peso")
    assert lido is not None
    assert lido.spec == {"unidade": "kg"}


def test_create_duplicado_levanta():
    s = _store()
    s.create(Resource(kind="Tracker", name="peso"), agora=T0)
    with pytest.raises(ResourceJaExiste):
        s.create(Resource(kind="Tracker", name="peso"), agora=T0)


def test_get_inexistente_devolve_none():
    assert _store().get("Tracker", "nao-existe") is None


def test_list_por_kind_isola_kinds():
    s = _store()
    s.create(Resource(kind="Tracker", name="peso"), agora=T0)
    s.create(Resource(kind="Tracker", name="sono"), agora=T0)
    s.create(Resource(kind="Idea", name="ui-web"), agora=T0)
    trackers = s.list("Tracker")
    assert {r.name for r in trackers} == {"peso", "sono"}
    assert [r.name for r in s.list("Idea")] == ["ui-web"]


def test_list_filtra_por_selector():
    s = _store()
    s.create(Resource(kind="Idea", name="a", labels={"prio": "alta"}), agora=T0)
    s.create(Resource(kind="Idea", name="b", labels={"prio": "baixa"}), agora=T0)
    altas = s.list("Idea", selector={"prio": "alta"})
    assert [r.name for r in altas] == ["a"]


def test_apply_cria_quando_ausente():
    s = _store()
    r = s.apply(Resource(kind="Tracker", name="peso", spec={"unidade": "kg"}), agora=T0)
    assert r.criado_em == T0.isoformat()
    assert s.get("Tracker", "peso") is not None


def test_apply_atualiza_preservando_criado_em():
    s = _store()
    s.create(Resource(kind="Tracker", name="peso", spec={"unidade": "kg"}), agora=T0)
    r = s.apply(Resource(kind="Tracker", name="peso", spec={"unidade": "lb"}), agora=T1)
    assert r.spec == {"unidade": "lb"}
    assert r.criado_em == T0.isoformat()  # preservado
    assert r.atualizado_em == T1.isoformat()  # atualizado


def test_patch_faz_merge_raso():
    s = _store()
    s.create(Resource(kind="Tracker", name="peso", spec={"unidade": "kg", "meta": 80}), agora=T0)
    r = s.patch("Tracker", "peso", {"meta": 78}, agora=T1)
    assert r.spec == {"unidade": "kg", "meta": 78}
    assert r.atualizado_em == T1.isoformat()


def test_patch_inexistente_levanta():
    with pytest.raises(ResourceNaoEncontrado):
        _store().patch("Tracker", "x", {"a": 1}, agora=T0)


def test_set_status_escreve_status():
    s = _store()
    s.create(Resource(kind="Tracker", name="peso"), agora=T0)
    s.set_status("Tracker", "peso", {"ultimo": 82.3}, agora=T1)
    assert s.get("Tracker", "peso").status == {"ultimo": 82.3}


def test_set_status_inexistente_levanta():
    with pytest.raises(ResourceNaoEncontrado):
        _store().set_status("Tracker", "x", {"a": 1}, agora=T0)


def test_delete_remove_e_idempotente():
    s = _store()
    s.create(Resource(kind="Tracker", name="peso"), agora=T0)
    assert s.delete("Tracker", "peso") is True
    assert s.delete("Tracker", "peso") is False
    assert s.get("Tracker", "peso") is None


def test_kinds_lista_tipos_presentes():
    s = _store()
    s.create(Resource(kind="Tracker", name="peso"), agora=T0)
    s.create(Resource(kind="Idea", name="x"), agora=T0)
    assert set(s.kinds()) == {"Tracker", "Idea"}


def test_resiliencia_objeto_corrompido_nao_quebra_list():
    s = _store()
    s.create(Resource(kind="Idea", name="boa", spec={"ok": True}), agora=T0)
    # injeta JSON inválido direto no banco (simula corrupção)
    s.connection.execute(
        "INSERT INTO resources (kind, name, api_version, labels_json, spec_json,"
        " status_json, criado_em, atualizado_em) VALUES"
        " ('Idea','ruim','atlas/v1','{}','{quebrado','{}',?,?)",
        (T0.isoformat(), T0.isoformat()),
    )
    s.connection.commit()
    nomes = {r.name for r in s.list("Idea")}
    assert "boa" in nomes  # a boa sobrevive
    assert "ruim" not in nomes  # a corrompida é pulada, não derruba o list
