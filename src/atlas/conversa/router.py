"""Roteador genérico da camada NL global (ADR-0050).

Casa o ``gatilho`` de um ``Binding`` contra a mensagem, roda a ``acao`` sobre os
recursos do ``selector`` (labels), agrega e responde. ``None`` quando nada casa —
o chamador cai no roteador base (``handler``).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from atlas.conversa import acoes
from atlas.conversa.descritores import normalizar
from atlas.core.resource import Resource
from atlas.core.store import ResourceStore

_PRIORIDADE = {"verbo": 0, "regex": 1, "nome-solto": 2}
_ARTIGOS = {"o", "a", "os", "as", "do", "da", "dos", "das", "de", "meu", "minha"}


def _limpar_termo(termo: str) -> str:
    """Remove artigos/preposições iniciais do resto da mensagem ("o kubernetes" →
    "kubernetes") para o match por nome não falhar por causa deles."""
    palavras = termo.split()
    while palavras and normalizar(palavras[0]) in _ARTIGOS:
        palavras.pop(0)
    return " ".join(palavras)


@dataclass
class Contexto:
    agora: datetime = field(default_factory=datetime.now)
    chat_id: int | None = None
    enviar_documento: Callable[[int, str, str], None] | None = None
    notificar: Callable[[int, str], None] | None = None  # p/ resultado de ação assíncrona


def _alvos(store: ResourceStore, selector: dict) -> list[Resource]:
    """Recursos que batem o selector. A chave especial ``kind`` filtra o kind; o
    resto são labels (match exato AND). Sem ``kind`` → varre todos os kinds."""
    selector = dict(selector or {})
    kind = selector.pop("kind", None)
    kinds = [kind] if kind else store.kinds()
    out: list[Resource] = []
    vistos: set[tuple[str, str]] = set()
    for k in kinds:
        for r in store.list(k, labels=selector or None):
            chave = (r.kind, r.name)
            if chave not in vistos:
                vistos.add(chave)
                out.append(r)
    return out


def _aliases(binding: Resource) -> list[str]:
    g = binding.spec.get("gatilho") or {}
    vals = [g.get("valor", "")] + list(g.get("aliases") or [])
    return [normalizar(v) for v in vals if v]


def _casa_gatilho(binding: Resource, texto: str, texto_norm: str) -> tuple[bool, str]:
    """``(casou, termo)`` — ``termo`` é o resto da mensagem relevante p/ a ação."""
    g = binding.spec.get("gatilho") or {}
    tipo = g.get("tipo")
    if tipo == "verbo":
        for a in sorted(_aliases(binding), key=len, reverse=True):
            if texto_norm == a:
                return True, ""
            if texto_norm.startswith(a + " "):
                return True, _limpar_termo(texto[len(a):].strip())
        return False, ""
    if tipo == "regex":
        m = re.search(g.get("valor", ""), texto, re.IGNORECASE)
        if m:
            return True, (texto[m.end():].strip() or texto.strip())
        return False, ""
    if tipo == "nome-solto":
        return (bool(texto_norm), texto.strip())
    return False, ""


def _ordenar(bindings: list[Resource]) -> list[Resource]:
    return sorted(
        bindings,
        key=lambda b: (_PRIORIDADE.get((b.spec.get("gatilho") or {}).get("tipo"), 9), b.name),
    )


def responder(texto: str, store: ResourceStore, ctx: Contexto | None = None) -> str | None:
    """Roda o 1º Binding cujo gatilho casa e cuja ação produz algo. ``None`` se
    nenhum produzir resposta (cai no roteador base)."""
    if not texto or not texto.strip():
        return None
    ctx = ctx or Contexto()
    texto_norm = normalizar(texto)
    for b in _ordenar(store.list("Binding")):
        casou, termo = _casa_gatilho(b, texto, texto_norm)
        if not casou:
            continue
        acao = b.spec.get("acao") or {}
        if acao.get("tipo") != "builtin":
            continue  # tipo=collect é resolvido por ações dedicadas (ver acoes)
        fn = acoes.acao_builtin(acao.get("nome", ""))
        if fn is None:
            continue
        alvos = _alvos(store, b.spec.get("selector") or {})
        res = fn(store, ctx, alvos, {"termo": termo})
        if not res.texto and not res.arquivos:
            continue  # ação não achou nada → tenta o próximo binding (ex. cai no base)
        texto = res.texto
        for caminho in res.arquivos:
            if ctx.enviar_documento and ctx.chat_id is not None:
                ctx.enviar_documento(ctx.chat_id, caminho, res.texto)
            else:  # sem canal p/ documento: entrega o caminho local
                texto = (texto + f"\n📁 {caminho}").strip()
        return texto or "📎 enviado."
    return None
