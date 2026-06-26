"""TDD — isolamento por dono (ADR-0027, Fase 5).

Políticas puras de visibilidade/escrita por ``labels.owner`` + migração dos
recursos atuais. ``admin`` enxerga tudo; recursos ``labels.scope=system`` são
visíveis a todos (read-only p/ não-admin).
"""

from __future__ import annotations

from datetime import datetime

from atlas import scoping
from atlas.core.resource import Resource
from atlas.core.store import ResourceStore

_AGORA = datetime(2026, 6, 26, 12, 0)


def _r(name, owner=None, scope=None):
    labels = {}
    if owner:
        labels["owner"] = owner
    if scope:
        labels["scope"] = scope
    return Resource(kind="Task", name=name, labels=labels, spec={})


# ── can_see ──────────────────────────────────────────────────────────────────


def test_admin_ve_tudo():
    assert scoping.can_see(_r("a", owner="ana"), "bob", "admin") is True


def test_dono_ve_o_seu():
    assert scoping.can_see(_r("a", owner="ana"), "ana", "member") is True


def test_nao_dono_nao_ve():
    assert scoping.can_see(_r("a", owner="ana"), "bob", "member") is False


def test_system_visivel_a_todos():
    assert scoping.can_see(_r("a", scope="system"), "bob", "member") is True


def test_sem_dono_nao_visivel_a_member():
    assert scoping.can_see(_r("a"), "bob", "member") is False


# ── can_write ────────────────────────────────────────────────────────────────


def test_admin_escreve_tudo():
    assert scoping.can_write(_r("a", owner="ana"), "bob", "admin") is True


def test_criar_novo_permitido():
    assert scoping.can_write(None, "bob", "member") is True


def test_member_escreve_o_seu_nao_o_alheio():
    assert scoping.can_write(_r("a", owner="bob"), "bob", "member") is True
    assert scoping.can_write(_r("a", owner="ana"), "bob", "member") is False


def test_system_readonly_p_member():
    assert scoping.can_write(_r("a", scope="system"), "bob", "member") is False


# ── stamp_owner ──────────────────────────────────────────────────────────────


def test_stamp_member_forca_o_proprio_dono():
    out = scoping.stamp_owner({"owner": "ana"}, "bob", "member")
    assert out["owner"] == "bob"  # member não pode se passar por outro


def test_stamp_admin_respeita_dono_informado():
    out = scoping.stamp_owner({"owner": "ana"}, "bob", "admin")
    assert out["owner"] == "ana"


def test_stamp_admin_sem_dono_nao_inventa():
    out = scoping.stamp_owner({}, "bob", "admin")
    assert "owner" not in out


# ── visible (filtro de lista) ────────────────────────────────────────────────


def test_visible_filtra_por_dono():
    rs = [_r("a", owner="ana"), _r("b", owner="bob"), _r("c", scope="system")]
    nomes = {r.name for r in scoping.visible(rs, "ana", "member")}
    assert nomes == {"a", "c"}
    assert len(scoping.visible(rs, "x", "admin")) == 3


# ── migração ─────────────────────────────────────────────────────────────────


def test_migrate_estampa_sem_dono_e_pula_system(tmp_path):
    store = ResourceStore(str(tmp_path / "t.db"))
    store.apply(Resource(kind="Task", name="velho", labels={}, spec={}), _AGORA)
    store.apply(Resource(kind="Task", name="dele", labels={"owner": "ana"}, spec={}), _AGORA)
    store.apply(Resource(kind="Doc", name="sys", labels={"scope": "system"}, spec={}), _AGORA)

    n = scoping.migrate_unowned(store, "admin")
    assert n == 1  # só o "velho"
    assert store.get("Task", "velho").labels["owner"] == "admin"
    assert store.get("Task", "dele").labels["owner"] == "ana"  # intacto
    assert "owner" not in store.get("Doc", "sys").labels  # system fica global
    # idempotente
    assert scoping.migrate_unowned(store, "admin") == 0
