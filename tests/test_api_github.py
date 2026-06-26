"""TDD — endpoints de GitHub device flow na API (ADR-0027 F3).

Testa as funções de handler module-level (padrão de ``_agente_chat``), com
``github_auth`` monkeypatchado — sem rede e sem subir o servidor HTTP.
"""

from __future__ import annotations

import pytest

import atlas.secrets_store as sec
from atlas import api
from atlas import credentials as cred
from atlas import github_auth as gh
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


def test_device_start_devolve_user_code(monkeypatch):
    monkeypatch.setattr(
        gh,
        "start_device_flow",
        lambda **kw: {
            "user_code": "WDJB-MJHT",
            "verification_uri": "https://github.com/login/device",
            "device_code": "DEV",
        },
    )
    out = api._github_device_start(scope="repo")
    assert out["user_code"] == "WDJB-MJHT"


def test_device_start_sem_client_id_devolve_erro(monkeypatch):
    def boom(**kw):
        raise gh.GitHubAuthError("ATLAS_GITHUB_CLIENT_ID não configurado")

    monkeypatch.setattr(gh, "start_device_flow", boom)
    out = api._github_device_start()
    assert "error" in out


def test_device_poll_conecta_e_salva(store, monkeypatch):
    monkeypatch.setattr(
        gh,
        "poll_access_token",
        lambda dc, **kw: {"status": "connected", "access_token": "gho_TOK", "scope": "repo"},
    )
    out = api._github_device_poll(store, owner="luigi", device_code="DEV")
    assert out["status"] == "connected"
    assert cred.get_secret(cred.credential_id("github", "luigi")) == "gho_TOK"


def test_device_poll_pendente_nao_salva(store, monkeypatch):
    monkeypatch.setattr(
        gh,
        "poll_access_token",
        lambda dc, **kw: {"status": "pending", "error": "authorization_pending"},
    )
    out = api._github_device_poll(store, owner="luigi", device_code="DEV")
    assert out["status"] == "pending"
    assert store.get("Credential", cred.credential_id("github", "luigi")) is None


def test_pat_fallback_salva_credential(store):
    out = api._github_pat(store, owner="ana", token="ghp_PAT")
    assert out["status"] == "connected"
    assert cred.get_secret(cred.credential_id("github", "ana")) == "ghp_PAT"


def test_pat_token_vazio_devolve_erro(store):
    out = api._github_pat(store, owner="ana", token="")
    assert "error" in out
    assert store.get("Credential", cred.credential_id("github", "ana")) is None
