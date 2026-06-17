"""TDD — loader de manifestos (atlas apply -f)."""

from __future__ import annotations


def test_pyyaml_disponivel():
    import yaml  # noqa: F401

    assert hasattr(yaml, "safe_load_all")
