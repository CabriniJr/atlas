"""Máquina de estados do Kind Torrent (ADR-0049)."""

from __future__ import annotations

from datetime import datetime

import pytest

from atlas import torrent_cmd
from atlas.core.store import ResourceStore
from atlas.torrent import download, servico
from atlas.torrent.download import Progresso
from atlas.torrent.scan import bencode


@pytest.fixture
def store():
    return ResourceStore(":memory:")


def _torrent_bytes(nome="filme.mkv", tam=700 * 1024 * 1024, ext_perigosa=False):
    fn = "malware.exe" if ext_perigosa else nome
    info = {b"piece length": 262144, b"name": b"pasta",
            b"files": [{b"length": tam, b"path": [fn.encode()]}]}
    return bencode({b"announce": b"http://t/x", b"info": info})


def _criar(store, tmp_path, *, chat=1, ext_perigosa=False):
    return servico.criar_do_bytes(
        store, _torrent_bytes(ext_perigosa=ext_perigosa), "a.torrent", chat,
        datetime.now(), dir_torrents=str(tmp_path),
    )


def _fake_baixar_ok(*a, **k):
    # simula on_progress + conclusão
    on = k.get("on_progress")
    if on:
        on(Progresso(pct=50, velocidade="1.0 MB/s", seeds=3))
        on(Progresso(pct=100, concluido=True))
    return download.ResultadoDownload(True, concluido=True, destino="/tmp/x")


def test_criar_do_bytes_cria_recurso_aguardando(store, tmp_path):
    res, sc = servico.criar_do_bytes(
        store, _torrent_bytes(), "filme.torrent", 42, datetime.now(), dir_torrents=str(tmp_path)
    )
    assert sc.ok
    assert res is not None
    assert res.status["fase"] == servico.AGUARDANDO
    assert res.name == sc.infohash
    assert store.get("Torrent", sc.infohash) is not None


def test_criar_do_bytes_scan_invalido_nao_cria(store, tmp_path):
    res, sc = servico.criar_do_bytes(
        store, b"lixo", "x.torrent", 42, datetime.now(), dir_torrents=str(tmp_path)
    )
    assert res is None and sc.ok is False
    assert store.list("Torrent") == []


def test_pendente_confirmacao(store, tmp_path):
    _criar(store, tmp_path)
    assert servico.pendente_confirmacao(store) is not None


def test_confirmar_dispara_download(monkeypatch, store, tmp_path):
    monkeypatch.setattr(download, "motor_disponivel", lambda: True)
    res, _ = _criar(store, tmp_path)
    disparados = []
    ok, msg = servico.confirmar(store, res.name, datetime.now(), dispatch=disparados.append)
    assert ok
    assert disparados == [res.name]
    assert store.get("Torrent", res.name).status["fase"] == servico.BAIXANDO


def test_confirmar_risco_alto_exige_forte(monkeypatch, store, tmp_path):
    monkeypatch.setattr(download, "motor_disponivel", lambda: True)
    res, sc = _criar(store, tmp_path, ext_perigosa=True)
    assert sc.risco == 2
    ok, msg = servico.confirmar(store, res.name, datetime.now(), dispatch=lambda n: None)
    assert ok is False and "SIM" in msg
    ok2, _ = servico.confirmar(store, res.name, datetime.now(), dispatch=lambda n: None, forte=True)
    assert ok2 is True


def test_confirmar_sem_motor_orienta_instalar(monkeypatch, store, tmp_path):
    monkeypatch.setattr(download, "motor_disponivel", lambda: False)
    res, _ = _criar(store, tmp_path)
    ok, msg = servico.confirmar(store, res.name, datetime.now(), dispatch=lambda n: None)
    assert ok is False and "qbittorrent-nox" in msg


def test_recusar(store, tmp_path):
    res, _ = _criar(store, tmp_path)
    ok, _ = servico.recusar(store, res.name, datetime.now())
    assert ok and store.get("Torrent", res.name).status["fase"] == servico.RECUSADO


def test_executar_download_conclui_e_notifica(store, tmp_path):
    res, _ = _criar(store, tmp_path, chat=77)
    store.set_status("Torrent", res.name, {**res.status, "fase": servico.BAIXANDO}, datetime.now())
    avisos = []
    servico.executar_download(
        store, res.name, notificar=lambda chat, msg: avisos.append((chat, msg)),
        cliente=object(), baixar_fn=_fake_baixar_ok, intervalo_s=0,
    )
    t = store.get("Torrent", res.name)
    assert t.status["fase"] == servico.CONCLUIDO
    assert t.status["progresso_pct"] == 100.0
    # última notificação é a de conclusão
    assert avisos[-1][0] == 77 and "baixado" in avisos[-1][1]


def test_notifica_marcos_10_50_90(store, tmp_path):
    res, _ = _criar(store, tmp_path, chat=9)
    store.set_status("Torrent", res.name, {**res.status, "fase": servico.BAIXANDO}, datetime.now())

    def _baixar_marcos(*a, **k):
        on = k["on_progress"]
        for pct in (5, 12, 55, 92, 100):  # cruza 10, 50, 90 e conclui
            on(Progresso(pct=pct, velocidade="2.0 MB/s", concluido=pct >= 100))
        return download.ResultadoDownload(True, concluido=True, destino="/tmp/x")

    marcos = []
    servico.executar_download(
        store, res.name, notificar=lambda c, m: marcos.append(m),
        cliente=object(), baixar_fn=_baixar_marcos, intervalo_s=0,
    )
    texto = "\n".join(marcos)
    assert "10%" in texto and "50%" in texto and "90%" in texto
    assert "baixado" in texto  # conclusão
    # cada marco só uma vez
    assert texto.count("10%") == 1 and texto.count("50%") == 1 and texto.count("90%") == 1


def test_executar_download_erro_notifica(store, tmp_path):
    res, _ = _criar(store, tmp_path, chat=5)
    store.set_status("Torrent", res.name, {**res.status, "fase": servico.BAIXANDO}, datetime.now())

    def _falha(*a, **k):
        return download.ResultadoDownload(False, motivo="WebUI do motor não respondeu")

    avisos = []
    servico.executar_download(store, res.name, notificar=lambda c, m: avisos.append(m),
                              cliente=object(), baixar_fn=_falha, intervalo_s=0)
    assert store.get("Torrent", res.name).status["fase"] == servico.ERRO
    assert avisos and "falhou" in avisos[0]


def test_cancelar_sinaliza_flag(store, tmp_path):
    res, _ = _criar(store, tmp_path)
    store.set_status("Torrent", res.name, {**res.status, "fase": servico.BAIXANDO}, datetime.now())
    ok, _ = servico.cancelar(store, res.name, datetime.now())
    assert ok
    t = store.get("Torrent", res.name)
    assert t.status["cancelar"] is True and t.status["fase"] == servico.CANCELADO


def test_retomar_no_boot_auto_resume(store, tmp_path):
    """Persistência (ADR-0049): um torrent que estava baixando retoma sozinho
    após restart — re-despachado, não volta pra confirmação."""
    from atlas.torrent.pool import TorrentPool

    res, _ = _criar(store, tmp_path)
    store.set_status("Torrent", res.name, {**res.status, "fase": servico.BAIXANDO}, datetime.now())
    disparados = []
    n = servico.retomar_no_boot(
        store, datetime.now(), dispatch=disparados.append, pool=TorrentPool(3)
    )
    assert n == 1
    assert disparados == [res.name]  # re-despachado (retomou)
    assert store.get("Torrent", res.name).status["fase"] == servico.BAIXANDO


def test_confirmar_alem_do_teto_vai_pra_fila(monkeypatch, store, tmp_path):
    from atlas.torrent.pool import TorrentPool

    monkeypatch.setattr(download, "motor_disponivel", lambda: True)
    pool = TorrentPool(max_concorrente=1)
    a, _ = servico.criar_do_bytes(
        store, _torrent_bytes(nome="a.mkv"), "a.torrent", 1, datetime.now(),
        dir_torrents=str(tmp_path),
    )
    # 2º torrent (infohash diferente)
    b, _ = servico.criar_do_bytes(
        store, _torrent_bytes(nome="b.mkv", tam=123), "b.torrent", 1, datetime.now(),
        dir_torrents=str(tmp_path),
    )
    disparados = []
    d = disparados.append
    ok1, _ = servico.confirmar(store, a.name, datetime.now(), dispatch=d, pool=pool)
    ok2, msg2 = servico.confirmar(store, b.name, datetime.now(), dispatch=d, pool=pool)
    assert ok1 and ok2
    assert disparados == [a.name]  # só o 1º baixa
    assert store.get("Torrent", a.name).status["fase"] == servico.BAIXANDO
    assert store.get("Torrent", b.name).status["fase"] == servico.FILA
    assert "fila" in msg2.lower()


def test_ao_concluir_slot_despacha_proximo(store, tmp_path):
    from atlas.torrent.pool import TorrentPool

    pool = TorrentPool(max_concorrente=1)
    a, _ = servico.criar_do_bytes(
        store, _torrent_bytes(nome="a.mkv"), "a.torrent", 1, datetime.now(),
        dir_torrents=str(tmp_path),
    )
    b, _ = servico.criar_do_bytes(
        store, _torrent_bytes(nome="b.mkv", tam=9), "b.torrent", 1, datetime.now(),
        dir_torrents=str(tmp_path),
    )
    pool.tentar_iniciar(a.name)
    pool.tentar_iniciar(b.name)  # b na fila
    store.set_status("Torrent", b.name, {**b.status, "fase": servico.FILA}, datetime.now())
    prox = servico.ao_concluir_slot(store, a.name, pool=pool)
    assert prox == b.name
    assert store.get("Torrent", b.name).status["fase"] == servico.BAIXANDO


def test_cancelar_da_fila(monkeypatch, store, tmp_path):
    from atlas.torrent.pool import TorrentPool

    pool = TorrentPool(max_concorrente=1)
    res, _ = _criar(store, tmp_path)
    pool.tentar_iniciar("ocupa-o-slot")
    pool.tentar_iniciar(res.name)  # vai pra fila
    store.set_status("Torrent", res.name, {**res.status, "fase": servico.FILA}, datetime.now())
    ok, msg = servico.cancelar(store, res.name, datetime.now(), pool=pool)
    assert ok and "fila" in msg.lower()
    assert store.get("Torrent", res.name).status["fase"] == servico.CANCELADO
    assert pool.posicao_na_fila(res.name) is None


def test_executar_download_verifica_integridade_falha(store, tmp_path):
    """Ao concluir, um .nsz sem magic PFS0 → integridade=falha + aviso."""
    res, _ = _criar(store, tmp_path, chat=7)
    dest = tmp_path / "dl"
    (dest / res.spec["nome"]).mkdir(parents=True)
    (dest / res.spec["nome"] / "jogo.nsz").write_bytes(b"LIXO" + b"\x00" * 10)
    store.set_status(
        "Torrent", res.name,
        {**res.status, "fase": servico.BAIXANDO, "destino": str(dest)}, datetime.now(),
    )
    # o spec.destino também precisa apontar pro dest
    store.patch("Torrent", res.name, {"destino": str(dest)}, datetime.now())
    avisos = []
    servico.executar_download(
        store, res.name, notificar=lambda c, m: avisos.append(m),
        cliente=object(), baixar_fn=_fake_baixar_ok, intervalo_s=0,
    )
    t = store.get("Torrent", res.name)
    assert t.status["fase"] == servico.CONCLUIDO
    assert t.status["integridade"] == "falha"
    assert any("integridade falhou" in m.lower() or "invalid pfs0" in m.lower() for m in avisos)


def test_executar_download_reprova_truncado_mesmo_com_magic_ok(store, tmp_path):
    """Caso real (ADR-0049): arquivo com header PFS0 correto (passa no magic) mas
    TRUNCADO — o move do qBittorrent foi morto no meio. O magic sozinho dava ✅ e o
    jogo chegava corrompido; a checagem de completude por tamanho reprova."""
    res, _ = _criar(store, tmp_path, chat=7)  # torrent declara 700 MB
    dest = tmp_path / "dl"
    (dest / res.spec["nome"]).mkdir(parents=True)
    # header válido, mas só 104 bytes (muito menor que os 700 MB do .torrent)
    (dest / res.spec["nome"] / "jogo.nsp").write_bytes(b"PFS0" + b"\x00" * 100)
    store.set_status(
        "Torrent", res.name,
        {**res.status, "fase": servico.BAIXANDO, "destino": str(dest)}, datetime.now(),
    )
    store.patch("Torrent", res.name, {"destino": str(dest)}, datetime.now())
    avisos = []
    servico.executar_download(
        store, res.name, notificar=lambda c, m: avisos.append(m),
        cliente=object(), baixar_fn=_fake_baixar_ok, intervalo_s=0,
    )
    t = store.get("Torrent", res.name)
    assert t.status["integridade"] == "falha"
    assert "incompleto" in (t.status.get("integridade_detalhe") or "").lower()
    assert any("incompleto" in m.lower() for m in avisos)


# --- caminho container (ADR-0051) -------------------------------------------


class _CliContainerFake:
    def __init__(self):
        self.parados = []
        self.removidos = []

    def parar_p2p(self, infohash):
        self.parados.append(infohash)

    def remover(self, infohash, apagar_dados=False):
        self.removidos.append(infohash)


def test_confirmar_container_adiciona_e_marca_baixando(store, tmp_path):
    """Modo container: sempre adiciona (fila nativa), sem checar motor nox."""
    res, _ = _criar(store, tmp_path)
    disparados = []
    ok, msg = servico.confirmar(
        store, res.name, datetime.now(), dispatch=disparados.append, container=True
    )
    assert ok and disparados == [res.name]
    assert store.get("Torrent", res.name).status["fase"] == servico.BAIXANDO
    assert "baixando" in msg


def test_cancelar_container_remove_do_client(store, tmp_path):
    res, _ = _criar(store, tmp_path)
    store.set_status("Torrent", res.name, {**res.status, "fase": servico.BAIXANDO}, datetime.now())
    cli = _CliContainerFake()
    ok, _ = servico.cancelar(store, res.name, datetime.now(), cliente=cli)
    assert ok
    infohash = res.spec["infohash"]
    assert cli.parados == [infohash] and cli.removidos == [infohash]
    assert store.get("Torrent", res.name).status["fase"] == servico.CANCELADO


def test_retomar_no_boot_container_readiciona_todos(store, tmp_path):
    """Container: TODOS os pendentes são re-adicionados (fila nativa decide)."""
    a, _ = _criar(store, tmp_path)
    for fase in (servico.BAIXANDO, servico.FILA):
        store.set_status("Torrent", a.name, {**a.status, "fase": fase}, datetime.now())
    disparados = []
    n = servico.retomar_no_boot(
        store, datetime.now(), dispatch=disparados.append, container=True
    )
    assert n == 1 and disparados == [a.name]
    assert store.get("Torrent", a.name).status["fase"] == servico.BAIXANDO


def test_torrent_nasce_visivel_para_a_camada_nl(store, tmp_path):
    """Regressão: um torrent criado em runtime precisa do label de participação.

    O ``interface=telegram`` era aplicado SÓ pela retro-migração de boot
    (``binding.carimbar_participacao``), então todo torrent criado depois do boot
    ficava fora do selector da camada NL — `progresso` respondia "nada em
    andamento" com download em curso, até o próximo restart.
    """
    from atlas.conversa import binding
    from atlas.conversa.router import _alvos

    res, sc = servico.criar_do_bytes(
        store, _torrent_bytes(), "jogo.torrent", 42, datetime.now(),
        dir_torrents=str(tmp_path),
    )
    assert res is not None
    assert (res.labels or {}).get(binding.LABEL_INTERFACE) == binding.INTERFACE_TELEGRAM

    # e o recurso recém-nascido entra nos alvos do Binding 'progresso'
    sel = {binding.LABEL_INTERFACE: binding.INTERFACE_TELEGRAM}
    assert any(a.name == sc.infohash for a in _alvos(store, sel))


# ── display: id como indexador + nome em slug (pedido do PO, 2026-10-03) ──────
def test_slugificar_gera_lower_com_underscore():
    from atlas.conversa.descritores import slugificar
    assert slugificar("Marvel vs Capcom Fighting Collection [NSP]") == (
        "marvel_vs_capcom_fighting_collection_nsp"
    )
    assert slugificar("Pokémon Legends: Z-A") == "pokemon_legends_z_a"
    assert slugificar("") == "sem_nome"


def test_slug_nao_quebra_a_busca_por_nome_real(store, tmp_path):
    """O slug é só display: `buscar` continua casando o nome humano com espaços."""
    from atlas.conversa import binding
    from atlas.conversa.acoes import buscar
    from atlas.conversa.router import _alvos

    res, _sc = servico.criar_do_bytes(
        store, _torrent_bytes(nome="jogo.nsp"), "a.torrent", 1, datetime.now(),
        dir_torrents=str(tmp_path),
    )
    t = store.get("Torrent", res.name)
    novo = t.__class__(kind=t.kind, name=t.name, labels=t.labels,
                       spec={**t.spec, "nome": "Marvel vs Capcom"}, status=t.status)
    store.apply(novo, datetime.now())
    alvos = _alvos(store, {binding.LABEL_INTERFACE: binding.INTERFACE_TELEGRAM})
    # termo com espaço casa
    assert "Marvel vs Capcom" in buscar(store, None, alvos, {"termo": "marvel vs"}).texto
    # e termo em slug também casa (tolerância a underscore)
    assert "Marvel vs Capcom" in buscar(store, None, alvos, {"termo": "marvel_vs"}).texto


# ── #2: concluído cujos arquivos sumiram do disco vira `arquivado` ───────────
def test_arquivar_ausentes_tira_jogo_desinstalado_da_lista(store, tmp_path, monkeypatch):
    res, _sc = servico.criar_do_bytes(
        store, _torrent_bytes(), "a.torrent", 1, datetime.now(), dir_torrents=str(tmp_path)
    )
    destino = tmp_path / "destino"
    destino.mkdir()
    t = store.get("Torrent", res.name)
    novo = t.__class__(kind=t.kind, name=t.name, labels=t.labels,
                       spec={**t.spec, "nome": "jogo_x", "destino": str(destino)},
                       status={**t.status, "fase": servico.CONCLUIDO})
    store.apply(novo, datetime.now())

    # arquivos ainda não existem → arquiva
    n = servico.arquivar_ausentes(store, datetime.now())
    assert n == 1
    assert store.get("Torrent", res.name).status["fase"] == servico.ARQUIVADO

    # e sai da listagem do /torrents
    assert "jogo_x" not in torrent_cmd._listar(store)


def test_arquivar_ausentes_preserva_o_que_esta_no_disco(store, tmp_path):
    res, _sc = servico.criar_do_bytes(
        store, _torrent_bytes(), "a.torrent", 1, datetime.now(), dir_torrents=str(tmp_path)
    )
    destino = tmp_path / "destino"
    (destino / "jogo_y").mkdir(parents=True)
    # "estar no disco" exige CONTEÚDO: pasta vazia é jogo desinstalado
    (destino / "jogo_y" / "a.nsp").write_bytes(b"conteudo real")
    t = store.get("Torrent", res.name)
    novo = t.__class__(kind=t.kind, name=t.name, labels=t.labels,
                       spec={**t.spec, "nome": "jogo_y", "destino": str(destino)},
                       status={**t.status, "fase": servico.CONCLUIDO})
    store.apply(novo, datetime.now())
    assert servico.arquivar_ausentes(store, datetime.now()) == 0
    assert store.get("Torrent", res.name).status["fase"] == servico.CONCLUIDO


# ── #4b: a camada NL precisa mostrar quem está na fila ───────────────────────
def test_progresso_nl_mostra_quem_esta_na_fila():
    from atlas.conversa.descritores import _torrent_progresso
    from atlas.core.resource import Resource
    r = Resource(kind="Torrent", name="abc", labels={},
                 spec={"nome": "Jogo Da Fila"}, status={"fase": servico.FILA})
    linha = _torrent_progresso(r)
    assert linha is not None
    assert "fila" in linha.lower()


# ── #4a: confirmar vários pendentes sem ambiguidade ──────────────────────────
def _tres_pendentes(store, tmp_path):
    """Três .torrent distintos aguardando confirmação (infohash difere pelo nome)."""
    nomes = ["Jogo Um", "Jogo Dois", "Jogo Tres"]
    criados = []
    for i, n in enumerate(nomes):
        dados = bencode({b"announce": b"http://t/x", b"info": {
            b"piece length": 262144, b"name": f"pasta{i}".encode(),
            b"files": [{b"length": 1000 + i, b"path": [b"a.nsp"]}]}})
        res, _ = servico.criar_do_bytes(
            store, dados, f"{i}.torrent", 1, datetime.now(), dir_torrents=str(tmp_path)
        )
        t = store.get("Torrent", res.name)
        store.apply(t.__class__(kind=t.kind, name=t.name, labels=t.labels,
                                spec={**t.spec, "nome": n}, status=t.status), datetime.now())
        criados.append(res.name)
    return criados


def test_pendentes_confirmacao_devolve_todos(store, tmp_path):
    nomes = _tres_pendentes(store, tmp_path)
    pend = servico.pendentes_confirmacao(store)
    assert {p.name for p in pend} == set(nomes)
    # o singular segue existindo (o mais recente) p/ o fluxo de um só
    assert servico.pendente_confirmacao(store) is not None


def test_sim_solto_com_varios_pendentes_pede_desambiguacao(store, tmp_path):
    _tres_pendentes(store, tmp_path)
    chamadas = []
    out = torrent_cmd.responder_conversa(
        "sim", store, datetime.now(), dispatch=lambda n: chamadas.append(n)
    )
    assert out is not None
    # não confirmou nada às cegas
    assert chamadas == []
    assert len(servico.pendentes_confirmacao(store)) == 3
    # e explica como escolher (agora com local/nuvem — ADR-0056)
    assert "local <id>" in out and "nuvem <id>" in out
    assert "todos" in out


def test_sim_com_id_confirma_so_aquele(store, tmp_path):
    nomes = _tres_pendentes(store, tmp_path)
    alvo = nomes[0]
    chamadas = []
    out = torrent_cmd.responder_conversa(
        f"sim {alvo[:8]}", store, datetime.now(),
        dispatch=lambda n: chamadas.append(n), cliente=object(),
    )
    assert out is not None
    assert store.get("Torrent", alvo).status["fase"] != servico.AGUARDANDO
    assert len(servico.pendentes_confirmacao(store)) == 2


def test_sim_todos_confirma_a_fila_inteira(store, tmp_path):
    _tres_pendentes(store, tmp_path)
    chamadas = []
    out = torrent_cmd.responder_conversa(
        "sim todos", store, datetime.now(),
        dispatch=lambda n: chamadas.append(n), cliente=object(),
    )
    assert out is not None
    assert servico.pendentes_confirmacao(store) == []
    assert len(chamadas) == 3


def test_um_pendente_so_mantem_o_sim_simples(store, tmp_path):
    """Regressão: com UM pendente, 'sim' continua confirmando direto."""
    res, _sc = servico.criar_do_bytes(
        store, _torrent_bytes(), "a.torrent", 1, datetime.now(), dir_torrents=str(tmp_path)
    )
    out = torrent_cmd.responder_conversa(
        "sim", store, datetime.now(), dispatch=lambda n: None, cliente=object()
    )
    assert out is not None
    assert store.get("Torrent", res.name).status["fase"] != servico.AGUARDANDO


# ── #5: escolher Local ou Nuvem na confirmação (ADR-0056) ───────────────────
def test_nuvem_confirma_e_marca_destino_nuvem(store, tmp_path):
    res, _sc = servico.criar_do_bytes(
        store, _torrent_bytes(), "a.torrent", 1, datetime.now(), dir_torrents=str(tmp_path)
    )
    out = torrent_cmd.responder_conversa(
        "nuvem", store, datetime.now(), dispatch=lambda n: None, cliente=object()
    )
    assert out is not None
    st = store.get("Torrent", res.name).status
    assert st["fase"] != servico.AGUARDANDO
    assert st["destino_nuvem"] is True


def test_local_confirma_sem_marcar_nuvem(store, tmp_path):
    res, _sc = servico.criar_do_bytes(
        store, _torrent_bytes(), "a.torrent", 1, datetime.now(), dir_torrents=str(tmp_path)
    )
    torrent_cmd.responder_conversa(
        "local", store, datetime.now(), dispatch=lambda n: None, cliente=object()
    )
    st = store.get("Torrent", res.name).status
    assert st["fase"] != servico.AGUARDANDO
    assert st.get("destino_nuvem") is False


def test_sim_segue_valendo_como_local(store, tmp_path):
    """Compatibilidade: quem já respondia 'sim' continua indo pro disco local."""
    res, _sc = servico.criar_do_bytes(
        store, _torrent_bytes(), "a.torrent", 1, datetime.now(), dir_torrents=str(tmp_path)
    )
    torrent_cmd.responder_conversa(
        "sim", store, datetime.now(), dispatch=lambda n: None, cliente=object()
    )
    assert store.get("Torrent", res.name).status.get("destino_nuvem") is False


def test_nuvem_todos_vale_para_a_fila_inteira(store, tmp_path):
    nomes = _tres_pendentes(store, tmp_path)
    out = torrent_cmd.responder_conversa(
        "nuvem todos", store, datetime.now(), dispatch=lambda n: None, cliente=object()
    )
    assert out is not None
    for n in nomes:
        assert store.get("Torrent", n).status["destino_nuvem"] is True


def test_pergunta_de_confirmacao_oferece_local_ou_nuvem(store, tmp_path):
    msg = torrent_cmd.receber_documento(
        store, _torrent_bytes(), "a.torrent", 1, datetime.now(), dir_torrents=str(tmp_path)
    )
    assert "local" in msg.lower() and "nuvem" in msg.lower()


def test_arquivar_trata_pasta_vazia_como_ausente(store, tmp_path):
    """Desinstalar jogo costuma deixar a pasta vazia; ela não é "estar no disco"."""
    res, _sc = servico.criar_do_bytes(
        store, _torrent_bytes(), "a.torrent", 1, datetime.now(), dir_torrents=str(tmp_path)
    )
    destino = tmp_path / "destino"
    (destino / "jogo_vazio").mkdir(parents=True)  # existe, mas vazia
    t = store.get("Torrent", res.name)
    store.apply(t.__class__(kind=t.kind, name=t.name, labels=t.labels,
                            spec={**t.spec, "nome": "jogo_vazio", "destino": str(destino)},
                            status={**t.status, "fase": servico.CONCLUIDO}), datetime.now())
    assert servico.arquivar_ausentes(store, datetime.now()) == 1
    assert store.get("Torrent", res.name).status["fase"] == servico.ARQUIVADO
