"""Curadoria do gate do Agente modo `code` (SPEC-CURADORIA-GATE / ADR-0028 §4).

Funções puras sobre git: ver o diff que o agente deixou na working tree, descartar
(reverter) ou aprovar (promover para uma branch de revisão). Operam sobre o
``repo`` (raiz do projeto) confinadas a ``path`` (o workspace do run).

A working tree é compartilhada (ADR-0028): o diff de um run é o estado não-commitado
**atual** do seu workspace. Recomenda-se workspaces distintos por agente.
"""

from __future__ import annotations

from pathlib import Path

from atlas.rotinas.repo_sync import gitcmd


def _rel(path: str | None) -> str:
    """Caminho relativo do workspace; vazio = raiz do projeto (``.``)."""
    p = (path or "").strip()
    return p or "."


def workspace_diff(repo: str, path: str | None) -> str:
    """Diff textual das mudanças não-commitadas sob ``path`` (inclui arquivos novos).

    Usa ``add -N`` (intent-to-add) para que arquivos novos apareçam no diff, e
    desfaz com ``reset`` para não deixar resíduo no index (read-only de verdade).
    """
    root = Path(repo)
    rel = _rel(path)
    gitcmd.git(["add", "-N", "--", rel], cwd=root, check=False)
    try:
        return gitcmd.git(["diff", "--", rel], cwd=root)
    finally:
        gitcmd.git(["reset", "-q", "--", rel], cwd=root, check=False)


def discard_workspace(repo: str, path: str | None) -> None:
    """Reverte o que o agente escreveu sob ``path``: rastreados ao HEAD + remove novos."""
    root = Path(repo)
    rel = _rel(path)
    gitcmd.git(["checkout", "--", rel], cwd=root, check=False)  # rastreados → HEAD
    gitcmd.git(["clean", "-fd", "--", rel], cwd=root)           # remove não-rastreados


def approve_to_branch(repo: str, path: str | None, branch: str, message: str) -> str:
    """Promove as mudanças de ``path`` para ``branch`` e volta à branch original.

    Cria ``branch`` a partir do HEAD atual, comita **só** ``path`` lá e retorna à
    branch original — deixando a working tree limpa do que foi promovido (mudanças
    fora do workspace permanecem intactas). Erro se ``branch`` já existe.
    """
    root = Path(repo)
    rel = _rel(path)
    original = gitcmd.git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=root).strip()
    gitcmd.git(["checkout", "-b", branch], cwd=root)  # falha se já existe
    try:
        gitcmd.git(["add", "--", rel], cwd=root)
        gitcmd.git(["commit", "-q", "-m", message], cwd=root)
    finally:
        gitcmd.git(["checkout", original], cwd=root)
    return branch
