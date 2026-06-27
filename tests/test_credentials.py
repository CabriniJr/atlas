"""TDD — credenciais por usuário: metadados no store + segredo cifrado (ADR-0027 F2)."""

from __future__ import annotations

import pytest

import atlas.secrets_store as sec
from atlas import credentials as cred
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


def test_credential_id_estavel_e_seguro():
    assert cred.credential_id("github", "Luigi") == "github-luigi"
    assert cred.credential_id("github", "a b/c") == "github-a-b-c"


def test_save_persiste_metadados_sem_segredo(store):
    cid = cred.save_credential(
        store,
        owner="luigi",
        provider="github",
        secret="ghp_SECRET",
        account="luigi",
        scopes="repo",
    )
    r = store.get("Credential", cid)
    assert r is not None
    assert r.labels["owner"] == "luigi"
    assert r.spec["provider"] == "github"
    assert r.spec["status"] == "conectado"
    # o segredo NÃO está no recurso
    assert "ghp_SECRET" not in str(r.spec) + str(r.status) + str(r.labels)


def test_get_secret_recupera_do_cofre(store):
    cid = cred.save_credential(store, owner="luigi", provider="github", secret="ghp_X")
    assert cred.get_secret(cid) == "ghp_X"


def test_delete_remove_segredo_e_recurso(store):
    cid = cred.save_credential(store, owner="luigi", provider="github", secret="ghp_X")
    assert cred.delete_credential(store, cid) is True
    assert store.get("Credential", cid) is None
    assert cred.get_secret(cid) is None


def test_list_por_owner(store):
    cred.save_credential(store, owner="ana", provider="github", secret="a")
    cred.save_credential(store, owner="bob", provider="github", secret="b")
    assert {c.labels["owner"] for c in cred.list_credentials(store, owner="ana")} == {"ana"}
    assert len(cred.list_credentials(store)) == 2
