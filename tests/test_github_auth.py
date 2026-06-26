"""TDD — GitHub device flow + PAT fallback + git helper escopado (ADR-0027 F3).

HTTP é injetado (parâmetro ``post``) para não tocar a rede nos testes.
"""

from __future__ import annotations

import base64

import pytest

import atlas.secrets_store as sec
from atlas import credentials as cred
from atlas import github_auth as gh
from atlas.core.store import ResourceStore


@pytest.fixture(autouse=True)
def _vault(tmp_path, monkeypatch):
    monkeypatch.setenv("ATLAS_SECRETS_DIR", str(tmp_path / "secrets"))
    monkeypatch.delenv("ATLAS_SECRET_KEY", raising=False)
    monkeypatch.delenv("ATLAS_GITHUB_CLIENT_ID", raising=False)
    sec.reset_cache()
    yield
    sec.reset_cache()


@pytest.fixture
def store(tmp_path):
    return ResourceStore(str(tmp_path / "t.db"))


# ── client_id ────────────────────────────────────────────────────────────────


def test_client_id_vem_do_env(monkeypatch):
    monkeypatch.setenv("ATLAS_GITHUB_CLIENT_ID", " Iv1.abc ")
    assert gh.client_id() == "Iv1.abc"


def test_client_id_ausente_eh_vazio():
    assert gh.client_id() == ""


# ── start_device_flow ────────────────────────────────────────────────────────


def test_start_device_flow_pede_codigo_ao_github():
    chamadas = []

    def fake_post(url, data):
        chamadas.append((url, data))
        return {
            "device_code": "DEV123",
            "user_code": "WDJB-MJHT",
            "verification_uri": "https://github.com/login/device",
            "expires_in": 900,
            "interval": 5,
        }

    out = gh.start_device_flow(cid="Iv1.xyz", scope="repo", post=fake_post)
    assert out["user_code"] == "WDJB-MJHT"
    assert out["device_code"] == "DEV123"
    url, data = chamadas[0]
    assert "device/code" in url
    assert data["client_id"] == "Iv1.xyz"
    assert data["scope"] == "repo"


def test_start_sem_client_id_levanta():
    with pytest.raises(gh.GitHubAuthError):
        gh.start_device_flow(cid="", post=lambda u, d: {})


# ── poll_access_token ────────────────────────────────────────────────────────


def test_poll_pendente_devolve_status_pending():
    out = gh.poll_access_token(
        "DEV123", cid="Iv1.x", post=lambda u, d: {"error": "authorization_pending"}
    )
    assert out["status"] == "pending"


def test_poll_slow_down_devolve_pending_com_intervalo():
    out = gh.poll_access_token(
        "DEV123", cid="Iv1.x", post=lambda u, d: {"error": "slow_down", "interval": 10}
    )
    assert out["status"] == "pending"
    assert out["interval"] == 10


def test_poll_erro_terminal_devolve_error():
    out = gh.poll_access_token(
        "DEV123", cid="Iv1.x", post=lambda u, d: {"error": "expired_token"}
    )
    assert out["status"] == "error"
    assert out["error"] == "expired_token"


def test_poll_sucesso_devolve_token():
    out = gh.poll_access_token(
        "DEV123",
        cid="Iv1.x",
        post=lambda u, d: {"access_token": "gho_TOKEN", "scope": "repo"},
    )
    assert out["status"] == "connected"
    assert out["access_token"] == "gho_TOKEN"


# ── complete_device_login: persiste Credential cifrada ───────────────────────


def test_complete_login_salva_credential_cifrada(store):
    out = gh.complete_device_login(
        store,
        owner="luigi",
        device_code="DEV123",
        cid="Iv1.x",
        post=lambda u, d: {"access_token": "gho_TOKEN", "scope": "repo"},
    )
    assert out["status"] == "connected"
    cid = cred.credential_id("github", "luigi")
    r = store.get("Credential", cid)
    assert r is not None
    assert r.spec["provider"] == "github"
    # segredo recuperável do cofre, nunca no recurso
    assert cred.get_secret(cid) == "gho_TOKEN"
    assert "gho_TOKEN" not in str(r.spec) + str(r.status)


def test_complete_login_pendente_nao_salva(store):
    out = gh.complete_device_login(
        store,
        owner="luigi",
        device_code="DEV123",
        cid="Iv1.x",
        post=lambda u, d: {"error": "authorization_pending"},
    )
    assert out["status"] == "pending"
    assert store.get("Credential", cred.credential_id("github", "luigi")) is None


# ── PAT fallback ─────────────────────────────────────────────────────────────


def test_connect_via_pat_salva_credential(store):
    cid = gh.connect_via_pat(store, owner="ana", token="ghp_PAT", account="ana")
    r = store.get("Credential", cid)
    assert r is not None
    assert r.spec["provider"] == "github"
    assert cred.get_secret(cid) == "ghp_PAT"


def test_connect_via_pat_rejeita_token_vazio(store):
    with pytest.raises(gh.GitHubAuthError):
        gh.connect_via_pat(store, owner="ana", token="  ")


# ── token_for_owner ──────────────────────────────────────────────────────────


def test_token_for_owner_resolve_do_cofre(store):
    gh.connect_via_pat(store, owner="ana", token="ghp_PAT")
    assert gh.token_for_owner(store, "ana") == "ghp_PAT"


def test_token_for_owner_sem_credential_eh_none(store):
    assert gh.token_for_owner(store, "ninguem") is None


# ── git helper escopado ──────────────────────────────────────────────────────


def test_git_auth_args_monta_extraheader_basic():
    args = gh.git_auth_args("gho_TOKEN")
    assert args[0] == "-c"
    cfg = args[1]
    assert cfg.startswith("http.extraheader=Authorization: Basic ")
    b64 = cfg.split("Basic ", 1)[1]
    assert base64.b64decode(b64).decode() == "x-access-token:gho_TOKEN"


def test_git_auth_args_sem_token_eh_vazio():
    assert gh.git_auth_args("") == []
    assert gh.git_auth_args(None) == []
