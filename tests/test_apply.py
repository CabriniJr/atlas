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
