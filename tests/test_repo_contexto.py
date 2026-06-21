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
