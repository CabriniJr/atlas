"""TDD — cofre de segredos cifrados em repouso (ADR-0027, Fase 1)."""

from __future__ import annotations

import pytest

import atlas.secrets_store as sec


@pytest.fixture(autouse=True)
def _isola(tmp_path, monkeypatch):
    # cofre isolado por teste + chave própria
    monkeypatch.setenv("ATLAS_SECRETS_DIR", str(tmp_path / "secrets"))
    monkeypatch.delenv("ATLAS_SECRET_KEY", raising=False)
    sec.reset_cache()
    yield
    sec.reset_cache()


def test_encrypt_decrypt_roundtrip():
    tok = sec.encrypt("meu-segredo")
    assert tok != "meu-segredo"
    assert sec.decrypt(tok) == "meu-segredo"


def test_token_nao_revela_plaintext():
    tok = sec.encrypt("github_pat_ABC123")
    assert "github_pat_ABC123" not in tok


def test_put_get_delete_secret():
    sec.put_secret("github-user1", "tok-123")
    assert sec.has_secret("github-user1")
    assert sec.get_secret("github-user1") == "tok-123"
    assert sec.delete_secret("github-user1") is True
    assert sec.get_secret("github-user1") is None
    assert sec.has_secret("github-user1") is False


def test_get_inexistente_retorna_none():
    assert sec.get_secret("nao-existe") is None


def test_id_invalido_recusado():
    with pytest.raises(sec.SecretsError):
        sec.put_secret("../escapa", "x")


def test_chave_de_env_persiste_entre_caches(monkeypatch):
    key = __import__("cryptography.fernet", fromlist=["Fernet"]).Fernet.generate_key().decode()
    monkeypatch.setenv("ATLAS_SECRET_KEY", key)
    sec.reset_cache()
    tok = sec.encrypt("x")
    sec.reset_cache()  # recarrega da mesma env key
    assert sec.decrypt(tok) == "x"


def test_arquivo_cifrado_nao_contem_segredo(tmp_path, monkeypatch):
    monkeypatch.setenv("ATLAS_SECRETS_DIR", str(tmp_path / "s"))
    sec.reset_cache()
    sec.put_secret("c1", "segredo-secreto")
    blob = (tmp_path / "s" / "credentials" / "c1.enc").read_text()
    assert "segredo-secreto" not in blob
