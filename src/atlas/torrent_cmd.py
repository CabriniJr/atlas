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
) -> str | None:
    """Resolve mensagens de texto ligadas a torrents. Devolve ``None`` se a
    mensagem não tem a ver com torrent (deixa o roteador base seguir)."""
    t = texto.strip()
    low = t.lower()

    # --- comandos explícitos ---
    if low == "/torrents" or low == "/torrent":
        return _listar(store)
    if low.startswith("/torrent "):
        return _detalhe(store, t.split(None, 1)[1].strip())

    # --- confirmação stateful (só se há um torrent aguardando) ---
    pend = servico.pendente_confirmacao(store)
    if pend is not None:
        if t == "SIM" or low in _SIM:
            forte = t == "SIM"
            _ok, msg = servico.confirmar(store, pend.name, agora, dispatch=dispatch, forte=forte)
            return msg
        if low in _NAO:
            _ok, msg = servico.recusar(store, pend.name, agora)
            return msg

    # --- progresso / cancelar (sobre o que está baixando) ---
    andando = servico.em_andamento(store)
    if low in _PROGRESSO:
        alvo = andando or pend or _ultimo(store)
        if alvo is None:
            return "nenhum torrent no momento. Mande um arquivo .torrent para começar."
        return servico.linha_progresso(alvo)
    if low in _CANCELAR:
        alvo = andando or pend
        if alvo is None:
            return "nenhum download em andamento para cancelar."
        _ok, msg = servico.cancelar(store, alvo.name, agora)
        return msg

    return None


def _ultimo(store: ResourceStore):
    torrents = store.list(servico.KIND)
    if not torrents:
        return None
    return max(torrents, key=lambda t: (t.status or {}).get("criado_em") or "")


def _listar(store: ResourceStore) -> str:
    torrents = sorted(
        store.list(servico.KIND),
        key=lambda t: (t.status or {}).get("criado_em") or "",
        reverse=True,
    )
    if not torrents:
        return "nenhum torrent ainda. Mande um arquivo .torrent para começar."
    linhas = ["📥 Torrents:"]
    for t in torrents[:15]:
        s = t.status or {}
        nome = t.spec.get("nome") or t.name
        fase = s.get("fase")
        extra = f" {s.get('progresso_pct', 0):.0f}%" if fase == servico.BAIXANDO else ""
        linhas.append(f"  • {nome} — {fase}{extra}  [{t.name[:8]}]")
    return "\n".join(linhas)


def _detalhe(store: ResourceStore, ref: str) -> str:
    """``/torrent <id>`` — ``id`` pode ser o infohash inteiro ou o prefixo curto."""
    ref = ref.lower()
    for t in store.list(servico.KIND):
        if t.name.lower() == ref or t.name.lower().startswith(ref):
            return servico.linha_progresso(t)
    return f"torrent {ref!r} não encontrado. Veja /torrents."
