"""TDD — contexto de projeto no repo-sync."""

from __future__ import annotations

from pathlib import Path

from atlas.rotinas.repo_sync import _coletar_contexto, _spec_int
from atlas.core.resource import Resource


def _montar_repo(tmp: Path) -> Path:
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / "README.md").write_text("# Projeto X\nFaz coisas.", encoding="utf-8")
    docs = tmp / "docs"
    docs.mkdir()
    (docs / "arquitetura.md").write_text("## Arquitetura\nCamadas A/B.", encoding="utf-8")
    (docs / "sub").mkdir()
    (docs / "sub" / "guia.md").write_text("Guia interno.", encoding="utf-8")
    (tmp / "pyproject.toml").write_text("[project]\nname='x'", encoding="utf-8")
    (tmp / "ignorar.py").write_text("print(1)", encoding="utf-8")
    return tmp


def test_coleta_readme_docs_e_metadados(tmp_path):
    corpus, arquivos = _coletar_contexto(_montar_repo(tmp_path))
    assert "Projeto X" in corpus
    assert "Arquitetura" in corpus
    assert "Guia interno" in corpus
    assert "[project]" in corpus
    assert "print(1)" not in corpus  # .py fora da allowlist
    assert "README.md" in arquivos
    assert "docs/arquitetura.md" in arquivos
    assert "docs/sub/guia.md" in arquivos


def test_coleta_respeita_corpus_max_priorizando_docs(tmp_path):
    corpus, arquivos = _coletar_contexto(_montar_repo(tmp_path), corpus_max=40)
    assert len(corpus) <= 120  # cabeçalho + 1 bloco + aviso, bem curto
    assert "README.md" in arquivos  # README entra antes dos metadados


def test_spec_int_le_e_faz_fallback():
    r = Resource(kind="Repo", name="x", spec={"diff_prompt_max": "50"})
    assert _spec_int(r, "diff_prompt_max", 10) == 50
    assert _spec_int(r, "ausente", 7) == 7
    assert _spec_int(Resource(kind="Repo", name="y", spec={"k": "abc"}), "k", 9) == 9


from datetime import datetime, timedelta
from unittest.mock import patch

from atlas.core.store import ResourceStore
from atlas.rotinas.repo_sync import (
    _contexto_atual,
    _contexto_obsoleto,
    _gerar_contexto,
)


class _Ctx:
    def __init__(self, agora):
        self.agora = agora


def _store(tmp_path):
    return ResourceStore(str(tmp_path / "s.db"))


def test_gerar_contexto_cria_doc_tipo_contexto(tmp_path):
    repo_dir = _montar_repo(tmp_path / "repo")
    store = _store(tmp_path)
    agora = datetime(2026, 6, 21, 9, 0)
    store.apply(Resource(kind="Repo", name="nora", spec={"url": "x"}), agora)
    with patch("atlas.rotinas.repo_sync.invocar", return_value="RESUMO RICO DO PROJETO") as inv:
        _gerar_contexto(store.get("Repo", "nora"), repo_dir, store, _Ctx(agora))
    doc = store.get("Doc", "repo-nora-contexto")
    assert doc is not None
    assert doc.labels["tipo"] == "contexto"
    assert doc.spec["body"] == "RESUMO RICO DO PROJETO"
    assert doc.status["generated_at"] == agora.isoformat()
    # usou o modelo de contexto (Opus por default)
    assert inv.call_args.kwargs["modelo"] == "claude-opus-4-8"
    # marcou no Repo
    assert store.get("Repo", "nora").status["last_context_at"] == agora.isoformat()


def test_gerar_contexto_degrada_se_ia_falha(tmp_path):
    repo_dir = _montar_repo(tmp_path / "repo")
    store = _store(tmp_path)
    agora = datetime(2026, 6, 21, 9, 0)
    store.apply(Resource(kind="Repo", name="nora", spec={"url": "x"}), agora)
    with patch("atlas.rotinas.repo_sync.invocar", side_effect=RuntimeError("sem ia")):
        _gerar_contexto(store.get("Repo", "nora"), repo_dir, store, _Ctx(agora))
    assert store.get("Doc", "repo-nora-contexto") is None  # não grava


def test_contexto_obsoleto_e_atual(tmp_path):
    store = _store(tmp_path)
    agora = datetime(2026, 6, 21, 9, 0)
    assert _contexto_obsoleto("nora", store, agora, 7) is True  # ausente
    store.apply(
        Resource(
            kind="Doc",
            name="repo-nora-contexto",
            labels={"tipo": "contexto"},
            spec={"body": "CTX"},
            status={"generated_at": (agora - timedelta(days=2)).isoformat()},
        ),
        agora,
    )
    assert _contexto_obsoleto("nora", store, agora, 7) is False  # fresco
    assert _contexto_obsoleto("nora", store, agora, 1) is True  # vencido
    assert _contexto_atual("nora", store) == "CTX"
    assert _contexto_atual("ausente", store) == ""


from atlas.rotinas.repo_sync import _analisar


def test_analisar_injeta_contexto_e_diff_no_prompt():
    capturado = {}

    def fake_invocar(prompt, modelo, timeout):
        capturado["prompt"] = prompt
        capturado["modelo"] = modelo
        return "analise"

    with patch("atlas.rotinas.repo_sync.invocar", side_effect=fake_invocar):
        out = _analisar("DIFF_AQUI", "nora", "claude-sonnet-4-6", "CONTEXTO_DO_PROJETO")
    assert out == "analise"
    assert "CONTEXTO_DO_PROJETO" in capturado["prompt"]
    assert "DIFF_AQUI" in capturado["prompt"]
    assert capturado["modelo"] == "claude-sonnet-4-6"


def test_analisar_sem_contexto_ainda_roda():
    with patch("atlas.rotinas.repo_sync.invocar", return_value="ok"):
        out = _analisar("DIFF", "nora", "claude-sonnet-4-6", "")
    assert out == "ok"


import subprocess as _sp

from atlas.executor import ContextoExecucao
from atlas.db import Database
from atlas.routines import Rotina
from atlas.rotinas.repo_sync import collect


def _rotina():
    return Rotina(nome="nora-sync", descricao="x", label="nora", agenda="@daily 09:00",
                  modelo="none", saida="telegram", coletar="repo-sync")


def test_clone_gera_contexto(tmp_path, monkeypatch):
    monkeypatch.setenv("ATLAS_DB_PATH", str(tmp_path / "atlas.sqlite"))
    store = ResourceStore(str(tmp_path / "atlas.sqlite"))
    agora = datetime(2026, 6, 21, 9, 0)
    store.apply(Resource(kind="Repo", name="nora", spec={"url": "https://x/y"}), agora)

    # fake git: 'clone' cria o diretório com docs; demais comandos retornam vazio
    real_run = _sp.run

    def fake_run(args, **kw):
        if args[:2] == ["git", "clone"]:
            dest = Path(args[-1])
            _montar_repo(dest)
            return _sp.CompletedProcess(args, 0, "", "")
        if args[1] == "rev-parse":
            return _sp.CompletedProcess(args, 0, "abc1234\n", "")
        return _sp.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(_sp, "run", fake_run)
    ctx = ContextoExecucao(rotina=_rotina(), db=Database(str(tmp_path / "m.db")), agora=agora)
    ctx.store = store
    with patch("atlas.rotinas.repo_sync.invocar", return_value="CTX RICO"):
        collect(ctx)
    doc = store.get("Doc", "repo-nora-contexto")
    assert doc is not None and doc.spec["body"] == "CTX RICO"
