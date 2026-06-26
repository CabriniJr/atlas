"""TDD — usuários e senha local (ADR-0027, Fase 4).

O Kind ``User`` guarda metadados (display_name, role). O **verificador de senha**
(PBKDF2) vai cifrado no cofre, nunca no spec.
"""

from __future__ import annotations

import pytest

import atlas.secrets_store as sec
from atlas import users
from atlas.core.store import ResourceStore


@pytest.fixture(autouse=True)
def _vault(tmp_path, monkeypatch):
    monkeypatch.setenv("ATLAS_SECRETS_DIR", str(tmp_path / "secrets"))
    monkeypatch.delenv("ATLAS_SECRET_KEY", raising=False)
    sec.reset_cache()
    yield
    sec.reset_cache()


@pytest.fixture
def store(tmp_path):
    return ResourceStore(str(tmp_path / "t.db"))


def test_create_user_persiste_metadados(store):
    u = users.create_user(store, "luigi", display_name="Luigi", role="admin")
    assert u.name == "luigi"
    r = store.get("User", "luigi")
    assert r is not None
    assert r.spec["display_name"] == "Luigi"
    assert r.spec["role"] == "admin"


def test_create_user_normaliza_nome(store):
    u = users.create_user(store, "  Luigi C ")
    assert u.name == "luigi-c"


def test_create_user_role_default_member(store):
    u = users.create_user(store, "ana")
    assert store.get("User", u.name).spec["role"] == "member"


def test_set_e_verify_password(store):
    users.create_user(store, "ana", password="s3nha-boa")
    assert users.verify_password("ana", "s3nha-boa") is True
    assert users.verify_password("ana", "errada") is False


def test_senha_nao_aparece_no_recurso(store):
    users.create_user(store, "ana", password="s3nha-boa")
    r = store.get("User", "ana")
    blob = str(r.spec) + str(r.status) + str(r.labels)
    assert "s3nha" not in blob


def test_verify_sem_senha_definida_eh_false(store):
    users.create_user(store, "semsenha")
    assert users.verify_password("semsenha", "qualquer") is False


def test_hash_usa_salt_distinto_por_usuario(store):
    users.create_user(store, "a", password="mesma")
    users.create_user(store, "b", password="mesma")
    import atlas.secrets_store as s

    assert s.get_secret("login-a") != s.get_secret("login-b")
