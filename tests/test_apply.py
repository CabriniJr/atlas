"""TDD — loader de manifestos (atlas apply -f)."""

from __future__ import annotations

import pytest

from atlas.apply import ManifestoInvalido, parse_manifests


def test_pyyaml_disponivel():
    import yaml  # noqa: F401

    assert hasattr(yaml, "safe_load_all")


_YAML_OK = """
kind: Tracker
name: peso
labels:
  grupo: academia
spec:
  unit: kg
  type: number
---
kind: Goal
name: peso-alvo
labels:
  grupo: academia
spec:
  target: 78
  unit: kg
"""


def test_parse_multidoc_retorna_lista():
    docs = parse_manifests(_YAML_OK)
    assert [d["kind"] for d in docs] == ["Tracker", "Goal"]
    assert docs[0]["name"] == "peso"
    assert docs[0]["labels"]["grupo"] == "academia"


def test_parse_ignora_documento_vazio():
    docs = parse_manifests("---\n\n---\nkind: Tracker\nname: peso\n")
    assert len(docs) == 1


def test_parse_erro_sem_kind():
    with pytest.raises(ManifestoInvalido, match="kind"):
        parse_manifests("name: peso\nspec: {}\n")


def test_parse_erro_sem_name():
    with pytest.raises(ManifestoInvalido, match="name"):
        parse_manifests("kind: Tracker\nspec: {}\n")


def test_parse_erro_documento_nao_mapa():
    with pytest.raises(ManifestoInvalido, match="mapa"):
        parse_manifests("- isto\n- e uma lista\n")


import json as _json

from atlas.apply import build_request


def test_build_request_monta_put():
    m = {"kind": "Tracker", "name": "peso", "labels": {"grupo": "academia"}, "spec": {"unit": "kg"}}
    method, url, body, headers = build_request("http://127.0.0.1:8080", m, token="t0k")
    assert method == "PUT"
    assert url == "http://127.0.0.1:8080/apis/atlas/v1/Tracker/peso"
    assert _json.loads(body) == {"labels": {"grupo": "academia"}, "spec": {"unit": "kg"}}
    assert headers["Authorization"] == "Bearer t0k"
    assert headers["Content-Type"] == "application/json"


def test_build_request_sem_token_nao_inclui_auth():
    m = {"kind": "Goal", "name": "peso-alvo"}
    _, url, body, headers = build_request("http://127.0.0.1:8080/", m, token=None)
    assert url == "http://127.0.0.1:8080/apis/atlas/v1/Goal/peso-alvo"
    assert "Authorization" not in headers
    assert _json.loads(body) == {"labels": {}, "spec": {}}


from atlas.apply import apply_manifests

_MANIFESTS = [
    {"kind": "Tracker", "name": "peso", "labels": {"grupo": "academia"}, "spec": {"unit": "kg"}},
    {"kind": "Goal", "name": "peso-alvo", "labels": {"grupo": "academia"}, "spec": {}},
]


def test_apply_chama_sender_por_objeto():
    chamadas = []

    def fake_send(method, url, body, headers):
        chamadas.append((method, url))

    res = apply_manifests(_MANIFESTS, "http://api", token="t", send=fake_send)
    assert res.ok is True
    assert res.aplicados == ["Tracker/peso", "Goal/peso-alvo"]
    assert chamadas == [
        ("PUT", "http://api/apis/atlas/v1/Tracker/peso"),
        ("PUT", "http://api/apis/atlas/v1/Goal/peso-alvo"),
    ]


def test_apply_dry_run_nao_chama_sender():
    def boom(*a, **k):
        raise AssertionError("não deveria chamar HTTP em dry-run")

    res = apply_manifests(_MANIFESTS, "http://api", token=None, dry_run=True, send=boom)
    assert res.ok is True
    assert res.aplicados == ["Tracker/peso", "Goal/peso-alvo"]


def test_apply_falha_parcial_continua_e_marca_nao_ok():
    def flaky_send(method, url, body, headers):
        if "Goal" in url:
            raise RuntimeError("HTTP 500")

    res = apply_manifests(_MANIFESTS, "http://api", token=None, send=flaky_send)
    assert res.ok is False
    assert res.aplicados == ["Tracker/peso"]
    assert res.falhas == [("Goal/peso-alvo", "HTTP 500")]
