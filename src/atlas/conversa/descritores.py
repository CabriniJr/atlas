"""Descritores por kind para a camada NL global (ADR-0050).

Cada kind "de conteúdo" expõe duas funções PURAS: ``nome_exibicao`` (o texto que a
busca casa) e ``linha_progresso`` (uma linha se o recurso está ATIVO, senão
``None``). É o único ponto que conhece o formato de cada kind — plugar um kind
novo é adicionar um descritor aqui + carimbar o label ``interface=telegram``.
"""

from __future__ import annotations

import os
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass

from atlas.core.resource import Resource


def normalizar(s: str) -> str:
    """Minúsculo sem acento — base de comparação para busca/gatilho."""
    base = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(c for c in base if unicodedata.category(c) != "Mn").strip()


@dataclass
class Descritor:
    kind: str
    nome_exibicao: Callable[[Resource], str]
    linha_progresso: Callable[[Resource], str | None]
    acao_sugerida: str  # verbo natural p/ um match da busca (ex. "enviar", "sync")


def _st(r: Resource) -> dict:
    return r.status or {}


def _sp(r: Resource) -> dict:
    return r.spec or {}


# ── Torrent ──────────────────────────────────────────────────────────────────
def _torrent_nome(r: Resource) -> str:
    return _sp(r).get("nome") or r.name


def _torrent_progresso(r: Resource) -> str | None:
    s = _st(r)
    if s.get("fase") != "baixando":
        return None
    return (
        f"⬇️ {_torrent_nome(r)} — {s.get('progresso_pct', 0):.0f}% · "
        f"{s.get('velocidade') or '—'} · seeds {s.get('seeds', 0)}"
    )


# ── Traducao ─────────────────────────────────────────────────────────────────
def _traducao_nome(r: Resource) -> str:
    origem = _sp(r).get("origem") or ""
    return os.path.basename(origem) if origem else r.name


def _traducao_progresso(r: Resource) -> str | None:
    s = _st(r)
    if s.get("fase") not in ("traduzindo", "preparando"):
        return None
    prontas = s.get("paginas_prontas", 0)
    total = s.get("paginas_total", 0)
    alvo = f"pág {prontas}/{total}" if total else (s.get("atividade") or "preparando…")
    return f"📖 {_traducao_nome(r)} — {alvo}"


# ── Repo ─────────────────────────────────────────────────────────────────────
def _repo_progresso(r: Resource) -> str | None:
    s = _st(r)
    if s.get("fase") not in ("sincronizando", "analisando"):
        return None
    return f"🔄 {r.name} — {s.get('fase')}"


# ── Doc ──────────────────────────────────────────────────────────────────────
def _doc_nome(r: Resource) -> str:
    return _sp(r).get("path") or _sp(r).get("titulo") or r.name


DESCRITORES: dict[str, Descritor] = {
    "Torrent": Descritor("Torrent", _torrent_nome, _torrent_progresso, "progresso"),
    "Traducao": Descritor("Traducao", _traducao_nome, _traducao_progresso, "enviar"),
    "Repo": Descritor("Repo", (lambda r: r.name), _repo_progresso, "sync"),
    "Doc": Descritor("Doc", _doc_nome, (lambda r: None), "abrir"),
}


def descritor_de(kind: str) -> Descritor | None:
    return DESCRITORES.get(kind)
