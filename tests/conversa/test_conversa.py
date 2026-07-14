"""Camada NL global — Binding + roteador + ações + descritores (ADR-0050)."""

from __future__ import annotations

from datetime import datetime

import pytest

from atlas.conversa import acoes, binding
from atlas.conversa.descritores import descritor_de, normalizar
from atlas.conversa.router import Contexto, responder
from atlas.core.resource import Resource
from atlas.core.store import ResourceStore

TELE = {"interface": "telegram"}


@pytest.fixture
def store():
    return ResourceStore(":memory:")


def _apply(store, kind, name, *, spec=None, status=None, labels=None):
    r = Resource(kind=kind, name=name, labels={**TELE, **(labels or {})}, spec=spec or {},
                 status=status or {})
    store.apply(r, datetime.now())
    return r


def _seed(store):
    binding.aplicar_seeds(store, datetime.now())


# ── descritores ──────────────────────────────────────────────────────────────
def test_descritor_torrent_ativo_e_inativo():
    d = descritor_de("Torrent")
    ativo = Resource(kind="Torrent", name="h1", spec={"nome": "Astral Chain"},
                     status={"fase": "baixando", "progresso_pct": 42.0, "velocidade": "3 MB/s",
                             "seeds": 5})
    assert "Astral Chain" in d.nome_exibicao(ativo)
    assert "42%" in d.linha_progresso(ativo)
    parado = Resource(kind="Torrent", name="h2", spec={"nome": "X"}, status={"fase": "concluido"})
    assert d.linha_progresso(parado) is None


def test_descritor_traducao_nome_do_pdf():
    d = descritor_de("Traducao")
    r = Resource(kind="Traducao", name="lbl", spec={"origem": "data/pdfs/Kubernetes.pdf"},
                 status={"fase": "traduzindo", "paginas_prontas": 3, "paginas_total": 10})
    assert d.nome_exibicao(r) == "Kubernetes.pdf"
    assert "pág 3/10" in d.linha_progresso(r)


def test_normalizar_tira_acento_e_caixa():
    assert normalizar("Astral CHAIN") == "astral chain"
    assert normalizar("Configuração") == "configuracao"


# ── progresso-global ─────────────────────────────────────────────────────────
def test_progresso_global_so_ativos(store):
    _apply(store, "Torrent", "t1", spec={"nome": "Jogo A"},
           status={"fase": "baixando", "progresso_pct": 10, "velocidade": "1 MB/s", "seeds": 2})
    _apply(store, "Traducao", "t2", spec={"origem": "x/Livro.pdf"},
           status={"fase": "traduzindo", "paginas_prontas": 1, "paginas_total": 5})
    _apply(store, "Torrent", "t3", spec={"nome": "Parado"}, status={"fase": "concluido"})
    alvos = [store.get("Torrent", "t1"), store.get("Traducao", "t2"), store.get("Torrent", "t3")]
    r = acoes.progresso_global(store, Contexto(), alvos, {})
    assert "Jogo A" in r.texto and "Livro.pdf" in r.texto
    assert "Parado" not in r.texto
    assert "2 em andamento" in r.texto


def test_progresso_global_vazio(store):
    r = acoes.progresso_global(store, Contexto(), [], {})
    assert "nada em andamento" in r.texto


# ── buscar ───────────────────────────────────────────────────────────────────
def test_buscar_agrupa_por_kind(store):
    _apply(store, "Torrent", "h", spec={"nome": "Astral Chain [NSP]"})
    _apply(store, "Traducao", "l", spec={"origem": "x/Astral notes.pdf"})
    _apply(store, "Repo", "atlas")
    alvos = [store.get("Torrent", "h"), store.get("Traducao", "l"), store.get("Repo", "atlas")]
    r = acoes.buscar(store, Contexto(), alvos, {"termo": "astral"})
    assert "Torrent" in r.texto and "Traducao" in r.texto
    assert "Astral Chain [NSP]" in r.texto
    assert "atlas" not in r.texto  # não casou o termo


def test_buscar_sem_match_texto_vazio(store):
    _apply(store, "Repo", "atlas")
    r = acoes.buscar(store, Contexto(), [store.get("Repo", "atlas")], {"termo": "inexistente"})
    assert r.texto == ""


# ── enviar ───────────────────────────────────────────────────────────────────
def test_preparar_envio_arquivo_grande_ausente(tmp_path):
    pequeno = tmp_path / "a.pdf"
    pequeno.write_bytes(b"%PDF-1.7")
    assert acoes.preparar_envio(str(pequeno))[0] == "arquivo"
    grande = tmp_path / "b.pdf"
    grande.write_bytes(b"\x00" * (acoes.LIMITE_TELEGRAM_BYTES + 1))
    assert acoes.preparar_envio(str(grande))[0] == "grande"
    assert acoes.preparar_envio(str(tmp_path / "nao_existe.pdf"))[0] == "ausente"


def test_enviar_pronto_devolve_arquivo(store, tmp_path):
    pdf = tmp_path / "Kubernetes.pt-BR.pdf"
    pdf.write_bytes(b"%PDF-1.7")
    _apply(store, "Traducao", "k", spec={"origem": "x/Kubernetes.pdf"},
           status={"fase": "pronto", "saida": str(pdf)})
    r = acoes.enviar(store, Contexto(), [store.get("Traducao", "k")], {"termo": "kubernetes"})
    assert r.arquivos == [str(pdf)]


def test_enviar_nao_pronto_avisa_fase(store):
    _apply(store, "Traducao", "k", spec={"origem": "x/Livro.pdf"}, status={"fase": "traduzindo"})
    r = acoes.enviar(store, Contexto(), [store.get("Traducao", "k")], {"termo": "livro"})
    assert "ainda não está pronto" in r.texto


# ── roteador ─────────────────────────────────────────────────────────────────
def test_router_verbo_progresso(store):
    _seed(store)
    _apply(store, "Torrent", "t1", spec={"nome": "Jogo A"},
           status={"fase": "baixando", "progresso_pct": 20, "velocidade": "1 MB/s", "seeds": 1})
    assert "Jogo A" in responder("progresso", store)


def test_router_nome_solto_busca(store):
    _seed(store)
    _apply(store, "Torrent", "t1", spec={"nome": "Astral Chain"})
    out = responder("astral", store)
    assert out and "Astral Chain" in out


def test_router_none_quando_nada_casa(store):
    _seed(store)
    _apply(store, "Repo", "atlas")
    # "sim" não é verbo conhecido e não casa nome nenhum → None (cai no base)
    assert responder("sim", store) is None


def test_router_enviar_com_termo(store, tmp_path):
    _seed(store)
    pdf = tmp_path / "Kubernetes.pt-BR.pdf"
    pdf.write_bytes(b"%PDF-1.7")
    _apply(store, "Traducao", "k", spec={"origem": "x/Kubernetes.pdf"},
           status={"fase": "pronto", "saida": str(pdf)})
    enviados = []
    ctx = Contexto(chat_id=1, enviar_documento=lambda c, p, leg: enviados.append(p))
    out = responder("me manda o kubernetes", store, ctx)
    assert enviados == [str(pdf)]
    assert out  # legenda


def test_router_prioridade_verbo_antes_de_nome_solto(store):
    _seed(store)
    # "progresso" é verbo e nome-solto; verbo tem prioridade → resposta de progresso
    out = responder("progresso", store)
    assert "andamento" in out


# ── seed + carimbo ───────────────────────────────────────────────────────────
def test_seed_idempotente(store):
    n1 = binding.aplicar_seeds(store, datetime.now())
    n2 = binding.aplicar_seeds(store, datetime.now())
    assert n1 >= 3 and n2 == 0


def test_agregar_sync_header_soma_commits(store):
    from atlas.conversa import sync as sync_mod

    _apply(store, "Repo", "repo-a")
    _apply(store, "Repo", "repo-b")
    repos = [store.get("Repo", "repo-a"), store.get("Repo", "repo-b")]

    def fake(store, label, agora):
        if label == "repo-a":
            return 3, "  • repo-a: 3 commit(s) novos"
        return 0, "  • repo-b: sem novidades"

    txt = sync_mod.agregar_sync(store, repos, datetime.now(), sincronizar_fn=fake)
    assert "sync de 2 repo(s) — 3 commit(s) novos" in txt
    assert "repo-a: 3" in txt and "repo-b: sem novidades" in txt


def test_sync_repos_ack_e_notifica(store):
    from atlas.conversa import sync as sync_mod
    from atlas.conversa.router import Contexto

    _apply(store, "Repo", "repo-a")
    avisos = []
    ctx = Contexto(chat_id=9, notificar=lambda c, m: avisos.append((c, m)))
    r = sync_mod.sync_repos(store, ctx, [store.get("Repo", "repo-a")], {})
    assert "sincronizando 1 repo" in r.texto  # ack imediato


def test_sync_repos_sem_repo(store):
    from atlas.conversa import sync as sync_mod
    from atlas.conversa.router import Contexto

    r = sync_mod.sync_repos(store, Contexto(), [], {})
    assert "nenhum repositório" in r.texto


def test_router_sync_verbo_dispara(store):
    _seed(store)
    _apply(store, "Repo", "repo-a")
    out = responder("sync", store)
    assert out is not None and "sincronizando" in out


def test_carimbo_participacao_idempotente(store):
    r = Resource(kind="Torrent", name="h", labels={}, spec={"nome": "X"}, status={})
    store.apply(r, datetime.now())
    n1 = binding.carimbar_participacao(store, datetime.now())
    n2 = binding.carimbar_participacao(store, datetime.now())
    assert n1 == 1 and n2 == 0
    assert store.get("Torrent", "h").labels["interface"] == "telegram"
