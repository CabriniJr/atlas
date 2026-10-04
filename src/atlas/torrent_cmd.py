"""Camada conversacional do Kind Torrent no Telegram (ADR-0049).

A "melhoria da interação via Telegram": o roteador base é stateless (texto entra
→ texto sai); aqui adicionamos **estado de conversa** consultando o recurso
pendente. Um `.torrent` chega como anexo → verifica → **pergunta**; um "sim"/"não"
solto é resolvido contra o torrent que está *aguardando confirmação*; "progresso"
e "cancelar" agem sobre o que está baixando.

O estado mora no recurso (não em memória de processo): sobrevive a restart e
aparece no dashboard. ``dispatch`` (injetado por quem tem o canal/adapter) sobe o
download em background com o notificador de término.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from atlas.conversa.descritores import slugificar
from atlas.core.store import ResourceStore
from atlas.torrent import servico

_SIM = {"sim", "s", "yes", "y", "pode", "bora", "baixa", "baixar"}
_NAO = {"não", "nao", "n", "no", "cancela", "deixa"}
_PROGRESSO = {"progresso", "progress", "status torrent", "andamento"}
_CANCELAR = {"cancelar", "cancela download", "para", "parar", "stop"}


def receber_documento(
    store: ResourceStore,
    dados: bytes,
    nome_arquivo: str,
    chat_id: int | None,
    agora: datetime,
    *,
    destino: str = servico.DESTINO_DEFAULT,
    permitir_sem_vpn: bool = True,
    vpn: str = "",
) -> str:
    """Processa um `.torrent` recebido: verifica, cria o recurso e devolve a
    pergunta de confirmação (ou o erro do scan)."""
    if not (nome_arquivo or "").lower().endswith(".torrent"):
        # Ainda tentamos: o conteúdo é que manda (o scan valida o bencode).
        pass
    res, sc = servico.criar_do_bytes(
        store, dados, nome_arquivo, chat_id, agora,
        destino=destino, permitir_sem_vpn=permitir_sem_vpn, vpn=vpn,
    )
    if res is None:
        return f"❌ não consegui ler esse arquivo como .torrent.\n{sc.erro}"
    pergunta = "Posso baixar? responda: sim / não"
    if sc.risco >= 2:
        pergunta = "🚨 risco ALTO. Para baixar mesmo assim, responda: SIM (maiúsculo) — ou não"
    return f"{sc.humano()}\n\n{pergunta}"


def responder_conversa(
    texto: str,
    store: ResourceStore,
    agora: datetime,
    *,
    dispatch: Callable[[str], None],
    cliente=None,
) -> str | None:
    """Resolve mensagens de texto ligadas a torrents. Devolve ``None`` se a
    mensagem não tem a ver com torrent (deixa o roteador base seguir).

    ``cliente`` (``ClienteContainer``, ADR-0051), se dado, usa o client único em
    container (fila nativa) em vez do modelo nox+pool."""
    t = texto.strip()
    low = t.lower()

    # --- comandos explícitos ---
    if low == "/torrents" or low == "/torrent":
        return _listar(store, agora)
    if low.startswith("/torrent "):
        return _detalhe(store, t.split(None, 1)[1].strip())

    # --- confirmação stateful (um ou vários torrents aguardando) ---
    pendentes = servico.pendentes_confirmacao(store)
    if pendentes:
        resp = _resolver_confirmacao(
            t, pendentes, store, agora, dispatch=dispatch, cliente=cliente
        )
        if resp is not None:
            return resp

    # --- progresso / cancelar (sobre o que está baixando) ---
    andando = servico.em_andamento(store)
    if low in _PROGRESSO:
        ativos = [
            t
            for t in store.list(servico.KIND)
            if (t.status or {}).get("fase") in (servico.BAIXANDO, servico.FILA)
        ]
        if ativos:  # instalação simultânea: mostra todos, não só um
            return "\n".join(servico.linha_progresso(t) for t in ativos)
        alvo = (pendentes[0] if pendentes else None) or _ultimo(store)
        if alvo is None:
            return "nenhum torrent no momento. Mande um arquivo .torrent para começar."
        return servico.linha_progresso(alvo)
    if low in _CANCELAR:
        alvo = andando or (pendentes[0] if pendentes else None)
        if alvo is None:
            return "nenhum download em andamento para cancelar."
        _ok, msg = servico.cancelar(store, alvo.name, agora, cliente=cliente)
        return msg

    return None


def _ultimo(store: ResourceStore):
    torrents = store.list(servico.KIND)
    if not torrents:
        return None
    return max(torrents, key=lambda t: (t.status or {}).get("criado_em") or "")


def _listar(store: ResourceStore, agora: datetime | None = None) -> str:
    """``/torrents`` — **id curto como indexador**, nome em slug.

    Antes de listar, arquiva o que não está mais no disco: jogo desinstalado não
    deve seguir aparecendo como pronto. ``arquivado`` fica fora da lista (o
    recurso continua no store e em ``/torrent <id>``)."""
    servico.arquivar_ausentes(store, agora or servico._agora())
    torrents = [
        t
        for t in sorted(
            store.list(servico.KIND),
            key=lambda t: (t.status or {}).get("criado_em") or "",
            reverse=True,
        )
        if (t.status or {}).get("fase") != servico.ARQUIVADO
    ]
    if not torrents:
        return "nenhum torrent ativo. Mande um arquivo .torrent para começar."
    linhas = ["📥 Torrents:"]
    for t in torrents[:15]:
        s = t.status or {}
        fase = s.get("fase")
        extra = f" {s.get('progresso_pct', 0):.0f}%" if fase == servico.BAIXANDO else ""
        nome = slugificar(t.spec.get("nome") or t.name)
        linhas.append(f"  {t.name[:8]}  {nome} — {fase}{extra}")
    return "\n".join(linhas)


def _detalhe(store: ResourceStore, ref: str) -> str:
    """``/torrent <id>`` — ``id`` pode ser o infohash inteiro ou o prefixo curto."""
    ref = ref.lower()
    for t in store.list(servico.KIND):
        if t.name.lower() == ref or t.name.lower().startswith(ref):
            return servico.linha_progresso(t)
    return f"torrent {ref!r} não encontrado. Veja /torrents."


_TODOS = {"todos", "todas", "tudo", "all"}


def _rotulo(t) -> str:
    """``<id curto>  <nome_slug>`` — o id é o indexador que o PO digita."""
    return f"{t.name[:8]}  {slugificar(t.spec.get('nome') or t.name)}"


def _por_id(pendentes: list, ref: str):
    """Casa um pendente por infohash inteiro ou prefixo curto."""
    ref = ref.lower()
    for t in pendentes:
        if t.name.lower() == ref or t.name.lower().startswith(ref):
            return t
    return None


def _resolver_confirmacao(
    texto: str, pendentes: list, store: ResourceStore, agora: datetime, *, dispatch, cliente
) -> str | None:
    """Resolve sim/não contra os pendentes. ``None`` = não é sim/não (segue o fluxo).

    Formas: ``sim`` (só se há **um** pendente), ``sim <id>``, ``sim todos``. Com
    vários pendentes um "sim" solto **não** confirma nada — pede o id, porque
    confirmar o mais recente às cegas instala o jogo errado.
    """
    partes = texto.split(None, 1)
    cab = partes[0]
    arg = partes[1].strip().lower() if len(partes) > 1 else ""
    low = cab.lower()
    sim, nao = low in _SIM, low in _NAO
    if not (sim or nao):
        return None
    forte = cab == "SIM"

    if arg in _TODOS and arg:
        alvos = list(reversed(pendentes))  # FIFO: o mais antigo primeiro
    elif arg:
        alvo = _por_id(pendentes, arg)
        if alvo is None:
            return (
                f"não achei {arg!r} entre os {len(pendentes)} aguardando. Pendentes:\n"
                + "\n".join(f"  {_rotulo(p)}" for p in pendentes)
            )
        alvos = [alvo]
    elif len(pendentes) == 1:
        alvos = list(pendentes)
    else:
        return (
            f"⏸️ {len(pendentes)} torrents aguardando — qual?\n"
            + "\n".join(f"  {_rotulo(p)}" for p in pendentes)
            + "\n\nResponda `sim <id>` para um, ou `sim todos` para a fila inteira."
        )

    msgs = []
    for alvo in alvos:
        if nao:
            _ok, msg = servico.recusar(store, alvo.name, agora)
        else:
            _ok, msg = servico.confirmar(
                store, alvo.name, agora, dispatch=dispatch, forte=forte,
                container=cliente is not None,
            )
        msgs.append(msg if len(alvos) == 1 else f"{alvo.name[:8]}: {msg}")
    return "\n".join(msgs)
