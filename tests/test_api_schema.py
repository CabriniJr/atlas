"""TDD — metadata de UI por kind servida pela API (/_schema)."""

from __future__ import annotations

from atlas.api_schema import schema_payload


def test_payload_tem_kinds_principais():
    p = schema_payload()
    kinds = p["kinds"]
    for k in ("Tracker", "Goal", "Routine", "Timer", "Repo", "Prompt"):
        assert k in kinds


def test_tracker_tem_campos_e_meta():
    tracker = schema_payload()["kinds"]["Tracker"]
    assert tracker["meta"]["icon"]
    campos = {c["k"]: c for c in tracker["spec"]}
    assert campos["unit"]["type"] == "text"
    assert campos["type"]["type"] == "select"
    assert "number" in campos["type"]["opts"]


def test_acoes_por_kind():
    kinds = schema_payload()["kinds"]
    # Timer expõe start/stop; Routine expõe run; Goal expõe check
    assert any(a["id"] == "start" for a in kinds["Timer"]["actions"])
    assert any(a["id"] == "stop" for a in kinds["Timer"]["actions"])
    assert any(a["id"] == "run" for a in kinds["Routine"]["actions"])
    assert any(a["id"] == "check" for a in kinds["Goal"]["actions"])


def test_repo_tem_campos_de_especializacao():
    """ADR-0023: Repo ganha config schema-driven de multi-branch/serialize/analyze."""
    repo = schema_payload()["kinds"]["Repo"]
    campos = {c["k"]: c for c in repo["spec"]}
    assert "serialize" in campos and campos["serialize"]["type"] == "select"
    assert "off" in campos["serialize"]["opts"]
    assert "docs+code" in campos["serialize"]["opts"]
    assert "default_branch" in campos
    assert "analyze_branches" in campos
    assert "analyze_max_per_run" in campos


def test_repo_tem_acao_backfill():
    repo = schema_payload()["kinds"]["Repo"]
    assert any(a["id"] == "backfill" for a in repo["actions"])


def test_kinds_ocultos_branch_commit_diff():
    """Branch/Commit/Diff são objetos de primeira classe, mas hidden (ADR-0023 §1)."""
    kinds = schema_payload()["kinds"]
    for k in ("Branch", "Commit", "Diff"):
        assert k in kinds, f"{k} ausente no schema"
        assert kinds[k]["meta"].get("hidden") is True


def test_agente_no_schema(tmp_path):
    """E7-23: Kind Agente aparece no schema com motor/modelo/nivel_contexto."""
    kinds = schema_payload()["kinds"]
    assert "Agente" in kinds
    a = kinds["Agente"]
    campos = {c["k"]: c for c in a["spec"]}
    assert "motor" in campos and "ollama" in campos["motor"]["opts"]
    assert "nivel_contexto" in campos
    assert "prompt" in campos
    assert any(x["id"] == "chat" for x in a["actions"])


def test_serializa_para_json():
    import json

    json.dumps(schema_payload())  # não levanta
