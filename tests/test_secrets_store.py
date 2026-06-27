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


# ── rotação da chave mestra (item 1.4 do hardening / ADR-0027 §Pendências) ─────


def test_list_secret_ids():
    sec.put_secret("a-1", "x")
    sec.put_secret("b-2", "y")
    assert sec.list_secret_ids() == ["a-1", "b-2"]


def test_rotate_reencripta_e_preserva_segredos(tmp_path):
    sec.put_secret("c1", "tok-1")
    sec.put_secret("c2", "tok-2")
    blob_antes = (tmp_path / "secrets" / "credentials" / "c1.enc").read_text()
    key_antes = (tmp_path / "secrets" / "secret.key").read_bytes()

    out = sec.rotate_key()

    assert out["rotated"] == 2
    # segredos seguem legíveis (agora com a chave nova)
    assert sec.get_secret("c1") == "tok-1"
    assert sec.get_secret("c2") == "tok-2"
    # ciphertext e chave mudaram
    blob_depois = (tmp_path / "secrets" / "credentials" / "c1.enc").read_text()
    key_depois = (tmp_path / "secrets" / "secret.key").read_bytes()
    assert blob_depois != blob_antes
    assert key_depois != key_antes
    assert out["new_key"].encode() == key_depois


def test_rotate_faz_backup_da_chave_antiga(tmp_path):
    sec.put_secret("c1", "tok-1")
    key_antes = (tmp_path / "secrets" / "secret.key").read_bytes()
    out = sec.rotate_key()
    assert out["backup"] is not None
    from pathlib import Path

    assert Path(out["backup"]).read_bytes() == key_antes


def test_rotate_com_chave_fornecida(tmp_path):
    from cryptography.fernet import Fernet

    nova = Fernet.generate_key()
    sec.put_secret("c1", "tok-1")
    out = sec.rotate_key(new_key=nova)
    assert out["new_key"].encode() == nova
    assert sec.get_secret("c1") == "tok-1"


def test_rotate_cofre_vazio_ok():
    out = sec.rotate_key()
    assert out["rotated"] == 0
    sec.put_secret("c1", "depois")
    assert sec.get_secret("c1") == "depois"


def test_rotate_aborta_se_segredo_corrompido(tmp_path):
    sec.put_secret("c1", "tok-1")
    key_antes = (tmp_path / "secrets" / "secret.key").read_bytes()
    # corrompe um blob → decifrar falha → rotação deve abortar sem trocar a chave
    (tmp_path / "secrets" / "credentials" / "c1.enc").write_text("lixo-nao-fernet")
    with pytest.raises(sec.SecretsError):
        sec.rotate_key()
    assert (tmp_path / "secrets" / "secret.key").read_bytes() == key_antes


def test_rotate_recusa_com_env_key(monkeypatch):
    from cryptography.fernet import Fernet

    monkeypatch.setenv("ATLAS_SECRET_KEY", Fernet.generate_key().decode())
    sec.reset_cache()
    sec.put_secret("c1", "tok-1")
    with pytest.raises(sec.SecretsError):
        sec.rotate_key()
