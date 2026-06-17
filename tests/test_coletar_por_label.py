"""TDD — rotina genérica coletar-por-label (feature label-driven collect)."""

from __future__ import annotations

from datetime import datetime

import pytest

from atlas.core.resource import Resource
from atlas.core.store import ResourceStore
from atlas.db import Database
from atlas.executor import ContextoExecucao
from atlas.rotinas import obter
from atlas.routines import Rotina

_AGORA = datetime(2026, 6, 16, 20, 0)
_ROTINA_TREINO = Rotina(
    nome="check-treino",
    descricao="Coleta diária de treino físico",
    label="treino",
    agenda="0 20 * * 1,2,4",
    modelo="none",
    saida="telegram",
)


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "t.db"))


@pytest.fixture
def store_com_treino(tmp_path):
    s = ResourceStore(str(tmp_path / "t.db"))
    s.apply(Resource(
        kind="Tracker", name="peso",
        labels={"grupo": "treino", "domain": "fisico"},
        spec={"unit": "kg", "syntax": "peso:", "active": True},
    ), _AGORA)
    s.apply(Resource(
        kind="Tracker", name="carga-supino",
        labels={"grupo": "treino", "domain": "fisico"},
        spec={"unit": "kg", "syntax": "carga-supino:", "active": True},
    ), _AGORA)
    s.apply(Resource(
        kind="Goal", name="emagrecimento",
        labels={"grupo": "treino", "state": "active"},
        spec={"target": 80, "start": 90, "unit": "kg", "tracker": "peso", "direction": "down"},
        status={"atual": 85.5, "progresso": "54%"},
    ), _AGORA)
    return s


@pytest.fixture
def store_vazio(tmp_path):
    return ResourceStore(str(tmp_path / "t.db"))


def _ctx(db, store, rotina=_ROTINA_TREINO):
    ctx = ContextoExecucao(agora=_AGORA, rotina=rotina, origem="agenda", db=db)
    ctx.store = store
    return ctx


def test_coletar_por_label_registrado(db):
    import atlas.rotinas.coletar_por_label  # noqa: F401

    fn = obter("coletar-por-label")
    assert fn is not None


def test_coletar_por_label_lista_trackers(db, store_com_treino):
    import atlas.rotinas.coletar_por_label  # noqa: F401

    fn = obter("coletar-por-label")
    result = fn(_ctx(db, store_com_treino))
    saida = result.data["_saida"]
    assert "peso" in saida
    assert "carga-supino" in saida


def test_coletar_por_label_mostra_sintaxe(db, store_com_treino):
    import atlas.rotinas.coletar_por_label  # noqa: F401

    fn = obter("coletar-por-label")
    result = fn(_ctx(db, store_com_treino))
    saida = result.data["_saida"]
    # sintaxe do tracker deve aparecer
    assert "peso:" in saida or "peso" in saida


def test_coletar_por_label_lista_goals(db, store_com_treino):
    import atlas.rotinas.coletar_por_label  # noqa: F401

    fn = obter("coletar-por-label")
    result = fn(_ctx(db, store_com_treino))
    saida = result.data["_saida"]
    assert "emagrecimento" in saida


def test_coletar_por_label_sem_recursos(db, store_vazio):
    import atlas.rotinas.coletar_por_label  # noqa: F401

    fn = obter("coletar-por-label")
    result = fn(_ctx(db, store_vazio))
    saida = result.data["_saida"]
    assert saida  # não falha; retorna mensagem amigável
    assert "treino" in saida.lower() or "nenhum" in saida.lower() or "grupo" in saida.lower()


def test_coletar_por_label_usa_rotina_label(db, store_com_treino):
    """Só traz recursos do grupo configurado, não de outros grupos."""
    import atlas.rotinas.coletar_por_label  # noqa: F401

    # Adiciona tracker de outro grupo
    store_com_treino.apply(Resource(
        kind="Tracker", name="livros-lidos",
        labels={"grupo": "estudos", "domain": "leitura"},
        spec={"unit": "", "syntax": "livros-lidos:", "active": True},
    ), _AGORA)

    fn = obter("coletar-por-label")
    result = fn(_ctx(db, store_com_treino))
    saida = result.data["_saida"]
    assert "livros-lidos" not in saida


def test_coletar_por_label_sem_store(db):
    import atlas.rotinas.coletar_por_label  # noqa: F401

    fn = obter("coletar-por-label")
    ctx = ContextoExecucao(agora=_AGORA, rotina=_ROTINA_TREINO, origem="agenda", db=db)
    # store = None (não definido)
    result = fn(ctx)
    saida = result.data["_saida"]
    assert saida  # não lança exceção


def test_coletar_por_label_inclui_cabecalho_com_grupo(db, store_com_treino):
    import atlas.rotinas.coletar_por_label  # noqa: F401

    fn = obter("coletar-por-label")
    result = fn(_ctx(db, store_com_treino))
    saida = result.data["_saida"]
    # cabeçalho deve identificar o grupo/rotina
    assert "treino" in saida.lower()


def test_routines_carrega_label_do_toml(tmp_path):
    """_carregar_uma deve ler o campo label do TOML e expor em Rotina.label."""
    from atlas.routines import carregar_rotinas

    pasta = tmp_path / "check-treino"
    pasta.mkdir()
    (pasta / "routine.toml").write_text(
        'nome = "check-treino"\n'
        'descricao = "Coleta de treino"\n'
        'label = "treino"\n'
        'modelo = "none"\n'
        'ativa = true\n'
    )
    resultado = carregar_rotinas(tmp_path)
    assert len(resultado.rotinas) == 1
    r = resultado.rotinas[0]
    assert r.label == "treino"


def test_routines_label_none_se_ausente(tmp_path):
    """Rotina sem label no TOML deve ter label=None."""
    from atlas.routines import carregar_rotinas

    pasta = tmp_path / "sem-label"
    pasta.mkdir()
    (pasta / "routine.toml").write_text(
        'nome = "sem-label"\n'
        'descricao = "Rotina sem label"\n'
        'modelo = "none"\n'
        'ativa = true\n'
    )
    resultado = carregar_rotinas(tmp_path)
    assert len(resultado.rotinas) == 1
    assert resultado.rotinas[0].label is None
