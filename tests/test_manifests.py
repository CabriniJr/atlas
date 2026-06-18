"""TDD — valida o conteúdo dos manifestos seed por grupo."""

from __future__ import annotations

from pathlib import Path

import yaml

_MANIFESTS = Path(__file__).resolve().parent.parent / "manifests"


def _carregar(grupo: str) -> dict[str, dict]:
    docs = yaml.safe_load_all((_MANIFESTS / f"{grupo}.yaml").read_text("utf-8"))
    return {d["name"]: d for d in docs if d}


def test_academia():
    objs = _carregar("academia")
    assert set(objs) == {"peso", "treino", "peso-alvo"}
    assert all(o["labels"]["grupo"] == "academia" for o in objs.values())
    peso = objs["peso"]
    assert peso["kind"] == "Tracker"
    assert peso["spec"] == {
        "unit": "kg",
        "type": "number",
        "syntax": "peso:",
        "aggregation": "last",
    }
    assert objs["treino"]["spec"]["type"] == "text"
    assert objs["peso-alvo"]["kind"] == "Goal"
    assert objs["peso-alvo"]["spec"]["unit"] == "kg"


def test_saude():
    objs = _carregar("saude")
    assert set(objs) == {"agua", "sono"}
    assert all(o["labels"]["grupo"] == "saude" for o in objs.values())
    assert objs["agua"]["spec"] == {
        "unit": "copos",
        "type": "count",
        "syntax": "agua:",
        "aggregation": "sum",
    }
    assert objs["sono"]["spec"]["aggregation"] == "mean"


def test_produtividade():
    objs = _carregar("produtividade")
    assert set(objs) == {"estudo", "foco"}
    assert all(o["labels"]["grupo"] == "produtividade" for o in objs.values())
    assert objs["estudo"]["spec"] == {
        "unit": "h",
        "type": "duration",
        "syntax": "estudo:",
        "aggregation": "sum",
    }
    assert objs["foco"]["kind"] == "Timer"
