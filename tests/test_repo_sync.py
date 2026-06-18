"""TDD — rotina genérica repo-sync: git pull + Diff Resource + explicação Haiku."""

from __future__ import annotations

import subprocess
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from atlas.core.resource import Resource
from atlas.core.store import ResourceStore
from atlas.db import Database
from atlas.executor import ContextoExecucao
from atlas.rotinas import obter
from atlas.routines import Rotina

_AGORA = datetime(2026, 6, 17, 9, 0)
_ROTINA = Rotina(nome="nora-sync", descricao="Monitor nora", label="nora",
                 coletar="repo-sync", modelo="none")


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "t.db"))


@pytest.fixture
def store(tmp_path):
    s = ResourceStore(str(tmp_path / "t.db"))
    s.apply(Resource(
        kind="Repo", name="nora",
        labels={"grupo": "repos"},
        spec={"url": "https://github.com/sys0xFF/nora", "branch": "HEAD"},
        status={},
    ), _AGORA)
    return s


@pytest.fixture
def store_sem_repo(tmp_path):
    return ResourceStore(str(tmp_path / "t.db"))


def _ctx(db, store, rotina=_ROTINA, tmp_path=None):
    ctx = ContextoExecucao(agora=_AGORA, rotina=rotina, origem="agenda", db=db, store=store)
    return ctx


def _mk(stdout="", rc=0, stderr=""):
    return MagicMock(stdout=stdout, returncode=rc, stderr=stderr)


# ── registro ──────────────────────────────────────────────────────────────────

def test_repo_sync_registrado(db):
    import atlas.rotinas.repo_sync  # noqa: F401
    assert obter("repo-sync") is not None


# ── sem Repo configurado ──────────────────────────────────────────────────────

def test_repo_sync_sem_repo_resource(db, store_sem_repo, tmp_path, monkeypatch):
    """Sem Repo/<label> no store, retorna instrução de setup."""
    import atlas.rotinas.repo_sync  # noqa: F401
    monkeypatch.setenv("ATLAS_DB_PATH", str(tmp_path / "atlas.sqlite"))

    fn = obter("repo-sync")
    result = fn(_ctx(db, store_sem_repo))
    saida = result.data["_saida"]
    assert "/apply Repo" in saida or "não configurado" in saida.lower()
    assert "nora" in saida


def test_repo_sync_sem_store_retorna_aviso(db):
    """Sem store injetado, não levanta exceção."""
    import atlas.rotinas.repo_sync  # noqa: F401
    ctx = ContextoExecucao(agora=_AGORA, rotina=_ROTINA, origem="agenda", db=db)
    fn = obter("repo-sync")
    result = fn(ctx)
    assert result.data["_saida"]


# ── clone inicial ─────────────────────────────────────────────────────────────

def test_repo_sync_clona_primeira_vez(db, store, tmp_path, monkeypatch):
    """Se repo local não existe, clona e retorna mensagem."""
    import atlas.rotinas.repo_sync  # noqa: F401
    monkeypatch.setenv("ATLAS_DB_PATH", str(tmp_path / "atlas.sqlite"))
    chamadas = []

    def fake_run(args, **kw):
        chamadas.append(list(args))
        return _mk()

    monkeypatch.setattr(subprocess, "run", fake_run)
    fn = obter("repo-sync")
    result = fn(_ctx(db, store))
    saida = result.data["_saida"]
    assert any("clone" in " ".join(a) for a in chamadas)
    assert "nora" in saida.lower() or "clon" in saida.lower()


# ── sem mudanças ──────────────────────────────────────────────────────────────

def test_repo_sync_sem_mudancas(db, store, tmp_path, monkeypatch):
    """Pull sem diff retorna mensagem 'sem mudanças'."""
    import atlas.rotinas.repo_sync  # noqa: F401
    monkeypatch.setenv("ATLAS_DB_PATH", str(tmp_path / "atlas.sqlite"))

    repo_dir = tmp_path / "repos" / "nora"
    repo_dir.mkdir(parents=True)
    (repo_dir / ".git").mkdir()

    def fake_run(args, **kw):
        if "diff" in " ".join(args):
            return _mk(stdout="")
        return _mk(stdout="abc1234\n" if "rev-parse" in " ".join(args) else "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    fn = obter("repo-sync")
    result = fn(_ctx(db, store))
    saida = result.data["_saida"]
    assert "sem mudança" in saida.lower() or "atualizado" in saida.lower()


# ── diff + Diff Resource ──────────────────────────────────────────────────────

def test_repo_sync_cria_diff_resource_no_store(db, store, tmp_path, monkeypatch):
    """Com diff, cria um Resource Kind=Diff no store."""
    import atlas.rotinas.repo_sync  # noqa: F401
    monkeypatch.setenv("ATLAS_DB_PATH", str(tmp_path / "atlas.sqlite"))

    repo_dir = tmp_path / "repos" / "nora"
    repo_dir.mkdir(parents=True)
    (repo_dir / ".git").mkdir()

    SHA = "abc1234"

    def fake_run(args, **kw):
        cmd = " ".join(args)
        if "diff" in cmd:
            return _mk(stdout="+class Nora:\n+    pass\n")
        if "rev-parse" in cmd:
            return _mk(stdout=SHA + "\n")
        return _mk()

    monkeypatch.setattr(subprocess, "run", fake_run)

    with patch("atlas.rotinas.repo_sync.invocar", return_value="Adicionada classe Nora."):
        fn = obter("repo-sync")
        fn(_ctx(db, store))

    diffs = store.list("Diff", labels={"repo": "nora"})
    assert len(diffs) == 1
    d = diffs[0]
    assert "nora" in d.name
    assert SHA[:7] in d.name or SHA in d.name
    assert d.labels.get("repo") == "nora"
    assert "Nora" in d.spec.get("diff_raw", "") or "Nora" in str(d.spec)


def test_repo_sync_diff_resource_tem_explicacao(db, store, tmp_path, monkeypatch):
    """O Diff Resource armazena a explicação do Haiku no spec."""
    import atlas.rotinas.repo_sync  # noqa: F401
    monkeypatch.setenv("ATLAS_DB_PATH", str(tmp_path / "atlas.sqlite"))

    repo_dir = tmp_path / "repos" / "nora"
    repo_dir.mkdir(parents=True)
    (repo_dir / ".git").mkdir()

    EXPLICACAO = "Classe Nora adicionada para abstração de usuários."

    def fake_run(args, **kw):
        if "diff" in " ".join(args):
            return _mk(stdout="+class Nora: pass\n")
        if "rev-parse" in " ".join(args):
            return _mk(stdout="deadbeef\n")
        return _mk()

    monkeypatch.setattr(subprocess, "run", fake_run)
    with patch("atlas.rotinas.repo_sync.invocar", return_value=EXPLICACAO):
        fn = obter("repo-sync")
        fn(_ctx(db, store))

    diffs = store.list("Diff", labels={"repo": "nora"})
    assert diffs
    assert diffs[0].spec.get("explicacao") == EXPLICACAO


def test_repo_sync_label_unica_por_repo(db, tmp_path, monkeypatch):
    """Diffs de repos diferentes ficam em labels separadas."""
    import atlas.rotinas.repo_sync  # noqa: F401
    monkeypatch.setenv("ATLAS_DB_PATH", str(tmp_path / "atlas.sqlite"))

    s = ResourceStore(str(tmp_path / "t.db"))
    s.apply(Resource(kind="Repo", name="alpha", labels={},
                     spec={"url": "https://github.com/x/alpha"}, status={}), _AGORA)
    s.apply(Resource(kind="Repo", name="beta", labels={},
                     spec={"url": "https://github.com/x/beta"}, status={}), _AGORA)

    db2 = Database(str(tmp_path / "t.db"))

    for repo_label in ("alpha", "beta"):
        d = tmp_path / "repos" / repo_label
        d.mkdir(parents=True, exist_ok=True)
        (d / ".git").mkdir(exist_ok=True)

    def fake_run(args, **kw):
        if "diff" in " ".join(args):
            return _mk(stdout="+mudança\n")
        if "rev-parse" in " ".join(args):
            return _mk(stdout="cafebabe\n")
        return _mk()

    monkeypatch.setattr(subprocess, "run", fake_run)

    with patch("atlas.rotinas.repo_sync.invocar", return_value="ok"):
        for repo_label in ("alpha", "beta"):
            rotina = Rotina(nome=f"{repo_label}-sync", descricao="x",
                            label=repo_label, coletar="repo-sync", modelo="none")
            ctx = ContextoExecucao(agora=_AGORA, rotina=rotina, origem="agenda",
                                   db=db2, store=s)
            fn = obter("repo-sync")
            fn(ctx)

    alpha_diffs = s.list("Diff", labels={"repo": "alpha"})
    beta_diffs  = s.list("Diff", labels={"repo": "beta"})
    assert alpha_diffs
    assert beta_diffs
    # não se misturam
    assert all(d.labels["repo"] == "alpha" for d in alpha_diffs)
    assert all(d.labels["repo"] == "beta"  for d in beta_diffs)


# ── atualiza Repo status ──────────────────────────────────────────────────────

def test_repo_sync_atualiza_repo_status(db, store, tmp_path, monkeypatch):
    """Após sync com diff, atualiza Repo/<label>.status.last_commit."""
    import atlas.rotinas.repo_sync  # noqa: F401
    monkeypatch.setenv("ATLAS_DB_PATH", str(tmp_path / "atlas.sqlite"))

    repo_dir = tmp_path / "repos" / "nora"
    repo_dir.mkdir(parents=True)
    (repo_dir / ".git").mkdir()

    SHA = "feedface"

    def fake_run(args, **kw):
        if "diff" in " ".join(args):
            return _mk(stdout="+algo\n")
        if "rev-parse" in " ".join(args):
            return _mk(stdout=SHA + "\n")
        return _mk()

    monkeypatch.setattr(subprocess, "run", fake_run)
    with patch("atlas.rotinas.repo_sync.invocar", return_value="ok"):
        fn = obter("repo-sync")
        fn(_ctx(db, store))

    repo_res = store.get("Repo", "nora")
    assert repo_res is not None
    assert SHA[:7] in (repo_res.status.get("last_commit") or "")


# ── IA best-effort ────────────────────────────────────────────────────────────

def test_repo_sync_diff_sem_ia_ainda_salva_resource(db, store, tmp_path, monkeypatch):
    """Se Haiku falha, o Diff Resource é criado sem explicação."""
    import atlas.rotinas.repo_sync  # noqa: F401
    monkeypatch.setenv("ATLAS_DB_PATH", str(tmp_path / "atlas.sqlite"))

    repo_dir = tmp_path / "repos" / "nora"
    repo_dir.mkdir(parents=True)
    (repo_dir / ".git").mkdir()

    def fake_run(args, **kw):
        if "diff" in " ".join(args):
            return _mk(stdout="+def foo(): pass\n")
        if "rev-parse" in " ".join(args):
            return _mk(stdout="badc0de\n")
        return _mk()

    monkeypatch.setattr(subprocess, "run", fake_run)
    with patch("atlas.rotinas.repo_sync.invocar", side_effect=Exception("claude off")):
        fn = obter("repo-sync")
        result = fn(_ctx(db, store))

    saida = result.data["_saida"]
    assert "foo" in saida  # diff aparece
    diffs = store.list("Diff", labels={"repo": "nora"})
    assert diffs  # Resource criado mesmo sem Haiku


def test_repo_sync_trunca_diff_grande_no_haiku(db, store, tmp_path, monkeypatch):
    """Diffs enormes são truncados antes de enviar ao Haiku."""
    import atlas.rotinas.repo_sync  # noqa: F401
    monkeypatch.setenv("ATLAS_DB_PATH", str(tmp_path / "atlas.sqlite"))

    repo_dir = tmp_path / "repos" / "nora"
    repo_dir.mkdir(parents=True)
    (repo_dir / ".git").mkdir()

    DIFF_GRANDE = "+linha\n" * 5000

    def fake_run(args, **kw):
        if "diff" in " ".join(args):
            return _mk(stdout=DIFF_GRANDE)
        if "rev-parse" in " ".join(args):
            return _mk(stdout="1234abc\n")
        return _mk()

    monkeypatch.setattr(subprocess, "run", fake_run)
    prompts = []
    with patch(
        "atlas.rotinas.repo_sync.invocar",
        side_effect=lambda p, **kw: prompts.append(p) or "ok",
    ):
        fn = obter("repo-sync")
        fn(_ctx(db, store))

    assert prompts
    assert len(prompts[0]) < len(DIFF_GRANDE)


def test_repo_sync_usa_haiku(db, store, tmp_path, monkeypatch):
    """A IA é chamada com modelo Haiku."""
    import atlas.rotinas.repo_sync  # noqa: F401
    monkeypatch.setenv("ATLAS_DB_PATH", str(tmp_path / "atlas.sqlite"))

    repo_dir = tmp_path / "repos" / "nora"
    repo_dir.mkdir(parents=True)
    (repo_dir / ".git").mkdir()

    def fake_run(args, **kw):
        if "diff" in " ".join(args):
            return _mk(stdout="+x\n")
        if "rev-parse" in " ".join(args):
            return _mk(stdout="cafecafe\n")
        return _mk()

    monkeypatch.setattr(subprocess, "run", fake_run)
    modelos = []
    with patch("atlas.rotinas.repo_sync.invocar",
               side_effect=lambda p, modelo="", **kw: modelos.append(modelo) or "ok"):
        fn = obter("repo-sync")
        fn(_ctx(db, store))

    assert modelos and "haiku" in modelos[0].lower()


# ── TOML ─────────────────────────────────────────────────────────────────────

# ── metadados ricos (descrição da última atualização + diff) ──────────────────

_DIFF_COM_STAT = (
    " src/foo.py | 8 ++++++--\n"
    " src/bar.py | 5 +++++\n"
    " 2 files changed, 10 insertions(+), 3 deletions(-)\n"
    "\n"
    "diff --git a/src/foo.py b/src/foo.py\n"
    "index 111..222 100644\n"
    "--- a/src/foo.py\n"
    "+++ b/src/foo.py\n"
    "@@ -1 +1,2 @@\n"
    "+nova linha\n"
    "diff --git a/src/bar.py b/src/bar.py\n"
    "index 333..444 100644\n"
    "--- a/src/bar.py\n"
    "+++ b/src/bar.py\n"
    "@@ -0,0 +1 @@\n"
    "+outra\n"
)


def _fake_run_rico(sha="abc1234"):
    """fake subprocess.run que devolve diff com --stat e metadados de commit."""
    def fake_run(args, **kw):
        cmd = " ".join(args)
        if "log" in cmd:  # git log -1 --format=...
            return _mk(stdout="feat: nova feature\nLuigi\nluigi@ex.com\n"
                              "2026-06-17T09:00:00-03:00\nhá 2 horas\n")
        if "diff" in cmd:
            return _mk(stdout=_DIFF_COM_STAT)
        if "rev-parse" in cmd:
            return _mk(stdout=sha + "\n")
        return _mk()
    return fake_run


def test_repo_sync_repo_status_metadados_ricos(db, store, tmp_path, monkeypatch):
    """Repo.status ganha mensagem, autor, data e estatísticas do diff."""
    import atlas.rotinas.repo_sync  # noqa: F401
    monkeypatch.setenv("ATLAS_DB_PATH", str(tmp_path / "atlas.sqlite"))
    repo_dir = tmp_path / "repos" / "nora"
    repo_dir.mkdir(parents=True)
    (repo_dir / ".git").mkdir()

    monkeypatch.setattr(subprocess, "run", _fake_run_rico())
    with patch("atlas.rotinas.repo_sync.invocar", return_value="ok"):
        obter("repo-sync")(_ctx(db, store))

    st = store.get("Repo", "nora").status
    assert st.get("last_commit_msg") == "feat: nova feature"
    assert st.get("last_author") == "Luigi"
    assert st.get("files_changed") == 2
    assert st.get("insertions") == 10
    assert st.get("deletions") == 3
    assert "feat: nova feature" in (st.get("last_summary") or "")


def test_repo_sync_diff_metadados_ricos(db, store, tmp_path, monkeypatch):
    """Diff.spec guarda subject, author, stats e lista de arquivos."""
    import atlas.rotinas.repo_sync  # noqa: F401
    monkeypatch.setenv("ATLAS_DB_PATH", str(tmp_path / "atlas.sqlite"))
    repo_dir = tmp_path / "repos" / "nora"
    repo_dir.mkdir(parents=True)
    (repo_dir / ".git").mkdir()

    monkeypatch.setattr(subprocess, "run", _fake_run_rico())
    with patch("atlas.rotinas.repo_sync.invocar", return_value="ok"):
        obter("repo-sync")(_ctx(db, store))

    d = store.list("Diff", labels={"repo": "nora"})[0]
    assert d.spec.get("subject") == "feat: nova feature"
    assert d.spec.get("author") == "Luigi"
    assert d.spec.get("files_changed") == 2
    assert d.spec.get("insertions") == 10
    assert "src/foo.py" in d.spec.get("files_list", [])
    assert "src/bar.py" in d.spec.get("files_list", [])


def test_repo_sync_saida_descreve_atualizacao(db, store, tmp_path, monkeypatch):
    """A saída traz a descrição da última atualização (mensagem + autor)."""
    import atlas.rotinas.repo_sync  # noqa: F401
    monkeypatch.setenv("ATLAS_DB_PATH", str(tmp_path / "atlas.sqlite"))
    repo_dir = tmp_path / "repos" / "nora"
    repo_dir.mkdir(parents=True)
    (repo_dir / ".git").mkdir()

    monkeypatch.setattr(subprocess, "run", _fake_run_rico())
    with patch("atlas.rotinas.repo_sync.invocar", return_value="explica"):
        saida = obter("repo-sync")(_ctx(db, store)).data["_saida"]

    assert "feat: nova feature" in saida
    assert "Luigi" in saida


def test_repo_sync_arquiva_diff_como_doc(db, store, tmp_path, monkeypatch):
    """Cada atualização vira um Doc arquivado (histórico represado), rotulado p/ hierarquia."""
    import atlas.rotinas.repo_sync  # noqa: F401
    monkeypatch.setenv("ATLAS_DB_PATH", str(tmp_path / "atlas.sqlite"))
    repo_dir = tmp_path / "repos" / "nora"
    repo_dir.mkdir(parents=True)
    (repo_dir / ".git").mkdir()

    monkeypatch.setattr(subprocess, "run", _fake_run_rico())
    with patch("atlas.rotinas.repo_sync.invocar", return_value="análise e sugestões da IA"):
        obter("repo-sync")(_ctx(db, store))

    docs = store.list("Doc", labels={"repo": "nora"})
    assert docs, "deve arquivar a atualização como Doc"
    d = docs[0]
    assert d.labels.get("topic") == "repo"          # hierarquia: topic > repo
    assert d.labels.get("repo") == "nora"
    assert "feat: nova feature" in d.spec.get("body", "")
    assert "análise e sugestões da IA" in d.spec.get("body", "")


def test_repo_sync_doc_acumula_historico(db, store, tmp_path, monkeypatch):
    """Docs de commits diferentes coexistem (represados, não sobrescrevem)."""
    import atlas.rotinas.repo_sync  # noqa: F401
    monkeypatch.setenv("ATLAS_DB_PATH", str(tmp_path / "atlas.sqlite"))
    repo_dir = tmp_path / "repos" / "nora"
    repo_dir.mkdir(parents=True)
    (repo_dir / ".git").mkdir()

    monkeypatch.setattr(subprocess, "run", _fake_run_rico(sha="aaa1111"))
    with patch("atlas.rotinas.repo_sync.invocar", return_value="x"):
        obter("repo-sync")(_ctx(db, store))
    monkeypatch.setattr(subprocess, "run", _fake_run_rico(sha="bbb2222"))
    with patch("atlas.rotinas.repo_sync.invocar", return_value="y"):
        obter("repo-sync")(_ctx(db, store))

    docs = store.list("Doc", labels={"repo": "nora"})
    assert len(docs) == 2  # dois commits → dois Docs preservados


def test_routines_carrega_nora_sync_toml(tmp_path):
    from atlas.routines import carregar_rotinas

    pasta = tmp_path / "nora-sync"
    pasta.mkdir()
    (pasta / "routine.toml").write_text(
        'nome = "nora-sync"\n'
        'descricao = "Monitor nora"\n'
        'label = "nora"\n'
        'coletar = "repo-sync"\n'
        'agenda = "0 9 * * *"\n'
        'modelo = "none"\n'
        'ativa = false\n'
    )
    resultado = carregar_rotinas(tmp_path)
    r = resultado.rotinas[0]
    assert r.label == "nora"
    assert r.coletar == "repo-sync"
    assert r.ativa is False
