"""TDD — rotinas de check-in por grupo carregam e nascem inativas."""

from __future__ import annotations

from pathlib import Path

from atlas.routines import carregar_rotinas

_ROUTINES = Path(__file__).resolve().parent.parent / "routines"


def test_rotinas_checkin_carregam_inativas():
    res = carregar_rotinas(_ROUTINES)
    por_nome = {r.nome: r for r in res.rotinas}
    for grupo in ("academia", "saude", "produtividade"):
        r = por_nome[f"check-{grupo}"]
        assert r.coletar == "coletar-por-label"
        assert r.label == grupo
        assert r.ativa is False
        assert r.modelo == "none"
