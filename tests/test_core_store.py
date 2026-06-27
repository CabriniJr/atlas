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


# ---------------------------------------------------------------------------
# E7-21 — Alias Job ↔ Routine (ADR-0021)
# ---------------------------------------------------------------------------


def test_job_lista_recursos_routine():
    """list('Job') devolve recursos criados como kind=Routine."""
    s = _store()
    s.create(Resource(kind="Routine", name="diario"), agora=T0)
    jobs = s.list("Job")
    assert len(jobs) == 1
    assert jobs[0].name == "diario"


def test_job_get_encontra_routine():
    s = _store()
    s.create(Resource(kind="Routine", name="checkin"), agora=T0)
    r = s.get("Job", "checkin")
    assert r is not None
    assert r.name == "checkin"


def test_job_lista_ambos_routine_e_job():
    """list('Job') combina Routine e Job numa única lista."""
    s = _store()
    s.create(Resource(kind="Routine", name="antigo"), agora=T0)
    s.create(Resource(kind="Job", name="novo"), agora=T0)
    nomes = {r.name for r in s.list("Job")}
    assert "antigo" in nomes and "novo" in nomes


def test_kinds_expoe_job_quando_ha_routine():
    """kinds() mostra 'Job' em vez de 'Routine' quando há recursos Routine."""
    s = _store()
    s.create(Resource(kind="Routine", name="x"), agora=T0)
    k = set(s.kinds())
    assert "Job" in k
    assert "Routine" not in k


def test_kinds_job_direto():
    """kinds() mostra 'Job' para recursos novos gravados como Job."""
    s = _store()
    s.create(Resource(kind="Job", name="novo"), agora=T0)
    assert "Job" in set(s.kinds())


def test_routine_list_continua_funcionando():
    """list('Routine') ainda funciona para compatibilidade com código legado."""
    s = _store()
    s.create(Resource(kind="Routine", name="legado"), agora=T0)
    assert s.list("Routine")[0].name == "legado"
