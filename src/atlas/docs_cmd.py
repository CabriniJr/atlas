"""Comando /docs — interface com Kind Doc via Telegram.

Toda documentação é um Resource(kind="Doc"). O boot sync carrega os arquivos
Markdown do projeto e as kind-refs embutidas. Este módulo é um adapter que
traduz comandos de chat para consultas no ResourceStore.

Hierarquia de tópicos (via labels.topic):
  arch     — arquitetura e ADRs
  roadmap  — backlog, amadurecimento, planejamento
  spec     — specs técnicas de cada módulo
  adr      — Architecture Decision Records
  kindref  — referência de uso de cada Kind
  user     — notas criadas pelo usuário via /apply Doc

Comandos:
  /docs                  — índice + counts por tópico
  /docs <slug>           — lê Doc pelo nome
  /docs kinds            — catálogo de kinds
  /docs backlog          — backlog priorizado
  /docs arch             — visão geral da arquitetura
  /docs adr <n>          — ADR pelo número
  /docs adr              — lista todos os ADRs
  /docs spec <nome>      — spec pelo slug (ex: trackers)
  /docs kind <Kind>      — kind-ref do Kind (ex: /docs kind Tracker)
  /docs -l topic=arch    — lista por label selector
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from atlas.core.resource import Resource
from atlas.core.store import ResourceStore

_MAX_CHARS = 3_500
_DOCS_ROOT = Path(os.environ.get("ATLAS_DOCS_DIR", "docs"))

# Alias de conveniência slug → nome no store
_ALIASES: dict[str, str] = {
    "kinds": "kinds",
    "arch": "arch",
    "arquitetura": "arch",
    "constituicao": "constituicao",
    "backlog": "backlog",
    "amadurecimento": "amadurecimento",
    "planejamento": "planejamento",
}

_SPEC_ALIASES: dict[str, str] = {
    "trackers": "spec-trackers",
    "alarmes": "spec-alarmes",
    "pool": "spec-pool",
    "scheduler": "spec-scheduler",
    "executor": "spec-executor",
    "interface": "spec-interface",
    "barreira": "spec-barreira",
    "core-api": "spec-core-api",
    "meta-loop": "spec-meta-loop",
}


def responder_docs(
    texto: str,
    agora: datetime,
    store: ResourceStore | None = None,
) -> str | None:
    partes = texto.strip().split()
    if not partes or partes[0] != "/docs":
        return None

    if len(partes) == 1:
        return _indice(store)

    sub = partes[1].lower()

    # /docs -l topic=arch
    if sub == "-l" and len(partes) >= 3:
        seletor = _parse_seletor(partes[2])
        return _listar_por_label(store, seletor)

    # /docs kind <Kind>
    if sub == "kind":
        kind = partes[2] if len(partes) >= 3 else ""
        if not kind:
            return "Usage: /docs kind <Kind>   e.g. /docs kind Tracker"
        slug = f"kind-{kind.lower()}"
        return _ler_store(store, slug) or f"❓ kind-ref '{kind}' não encontrado."

    # /docs adr [n]
    if sub == "adr":
        if len(partes) >= 3:
            return _adr(partes[2], store)
        return _listar_adrs(store)

    # /docs spec <nome>
    if sub == "spec":
        nome = partes[2].lower() if len(partes) >= 3 else ""
        if not nome:
            return "Usage: /docs spec <nome>   e.g. /docs spec trackers"
        slug = _SPEC_ALIASES.get(nome, f"spec-{nome}")
        return _ler_store(store, slug) or _fallback_filesystem(f"specs/{nome}.md", nome)

    # slug direto ou alias
    slug = _ALIASES.get(sub, sub)
    resultado = _ler_store(store, slug)
    if resultado:
        return resultado

    # fallback filesystem para slugs conhecidos (quando store indisponível)
    resultado_fs = _fallback_slug(slug)
    if resultado_fs is not None:
        return resultado_fs

    # fallback: busca parcial no store
    if store is not None:
        todos = store.list("Doc")
        matches = [d for d in todos if sub in d.name]
        if len(matches) == 1:
            return _formatar_doc(matches[0])
        if len(matches) > 1:
            nomes = ", ".join(d.name for d in matches[:8])
            return f"❓ '{partes[1]}' ambíguo. Matches: {nomes}"

    return f"❓ '{partes[1]}' não encontrado. Use /docs para ver o índice."


# ---------------------------------------------------------------------------
# Helpers de leitura
# ---------------------------------------------------------------------------


def _indice(store: ResourceStore | None) -> str:
    if store is None:
        return _indice_filesystem()

    counts: dict[str, int] = {}
    for d in store.list("Doc"):
        topic = d.labels.get("topic", "outros")
        counts[topic] = counts.get(topic, 0) + 1

    linhas = [
        "📚  Atlas — Kind Doc\n",
        "Toda documentação é um Resource. Leia, filtre e crie notes:\n",
        f"  /list Doc                      → {sum(counts.values())} docs no store",
        f"  /list Doc -l topic=arch        → {counts.get('arch', 0)} docs de arquitetura",
        f"  /list Doc -l topic=roadmap     → {counts.get('roadmap', 0)} docs de roadmap",
        f"  /list Doc -l topic=spec        → {counts.get('spec', 0)} specs técnicas",
        f"  /list Doc -l topic=adr         → {counts.get('adr', 0)} ADRs",
        f"  /list Doc -l topic=kindref     → {counts.get('kindref', 0)} referências de kinds",
        "",
        "Atalhos rápidos:",
        "  /docs kinds              catálogo de kinds",
        "  /docs backlog            backlog priorizado",
        "  /docs arch               visão geral da arquitetura",
        "  /docs adr 15             ADR-0015",
        "  /docs adr                lista todos os ADRs",
        "  /docs spec trackers      spec técnica de trackers",
        "  /docs kind Tracker       referência de uso do Kind Tracker",
        "  /docs kind Goal          referência de uso do Kind Goal",
        "",
        "Criar nota pessoal como Doc:",
        "  /apply Doc minha-ideia labels.topic=user spec.body=<texto>",
        "",
        "Inspecionar qualquer doc:",
        "  /describe Doc backlog",
    ]
    return "\n".join(linhas)


def _listar_por_label(store: ResourceStore | None, seletor: dict[str, str]) -> str:
    if store is None:
        return "❓ store não disponível para filtro por label"
    docs = store.list("Doc", labels=seletor)
    if not docs:
        return f"Nenhum Doc com labels {seletor}."
    linhas = [f"📚 Doc -l {','.join(f'{k}={v}' for k, v in seletor.items())} ({len(docs)})"]
    for d in docs:
        chars = d.status.get("chars", "?")
        linhas.append(f"  {d.name:<30} {chars} chars  → /docs {d.name}")
    return "\n".join(linhas)


def _ler_store(store: ResourceStore | None, slug: str) -> str | None:
    if store is None:
        return None
    r = store.get("Doc", slug)
    if r is None:
        return None
    return _formatar_doc(r)


def _formatar_doc(r: Resource) -> str:
    body = r.spec.get("body", "")
    title = r.spec.get("title", r.name)
    source = r.spec.get("source", "")

    # Remove frontmatter YAML
    if body.startswith("---"):
        fim = body.find("\n---", 3)
        if fim != -1:
            body = body[fim + 4 :].lstrip("\n")

    chars_total = len(body)
    if chars_total > _MAX_CHARS:
        body = body[:_MAX_CHARS]
        ultimo_nl = body.rfind("\n")
        if ultimo_nl > 0:
            body = body[:ultimo_nl]
        sufixo = f"\n\n… [{chars_total} chars total] /describe Doc {r.name}"
        if source:
            sufixo += f"  |  src: {source}"
        return f"📄 {title}\n\n{body}{sufixo}"

    header = f"📄 {title}"
    if source:
        header += f"  [src: {source}]"
    return f"{header}\n\n{body}"


def _adr(num_str: str, store: ResourceStore | None) -> str:
    try:
        n = int(num_str)
    except ValueError:
        return f"❓ '{num_str}' não é um número. Use /docs adr <n>"
    slug = f"adr-{n:04d}"
    if store is not None:
        docs = store.list("Doc", labels={"topic": "adr"})
        for d in docs:
            if d.name.startswith(slug):
                return _formatar_doc(d)
    return _fallback_filesystem_adr(n)


def _listar_adrs(store: ResourceStore | None) -> str:
    if store is not None:
        adrs = store.list("Doc", labels={"topic": "adr"})
        if adrs:
            linhas = [f"📋 ADRs ({len(adrs)})"]
            for d in adrs:
                title = d.spec.get("title", d.name)
                partes = d.name.split("-", 2)
                num = partes[1] if len(partes) > 1 else "?"
                linhas.append(f"  /docs adr {int(num)}  — {title}")
            return "\n".join(linhas)
    return _fallback_listar_adrs()


# ---------------------------------------------------------------------------
# Fallback filesystem (quando store não disponível ou doc não carregado)
# ---------------------------------------------------------------------------

_SLUG_TO_PATH: dict[str, str] = {
    "kinds": "arquitetura/kinds.md",
    "arch": "arquitetura/visao-geral.md",
    "constituicao": "arquitetura/constituicao.md",
    "modelo-dados": "arquitetura/modelo-de-dados.md",
    "seguranca": "arquitetura/seguranca.md",
    "ciclo": "arquitetura/ciclo-de-vida-rotina.md",
    "backlog": "roadmap/backlog.md",
    "amadurecimento": "roadmap/amadurecimento.md",
    "planejamento": "roadmap/planejamento.md",
    "spec-trackers": "specs/trackers-via-chat.md",
    "spec-alarmes": "specs/alarmes.md",
    "spec-pool": "specs/pool-de-ideias.md",
    "spec-scheduler": "specs/scheduler.md",
    "spec-executor": "specs/executor-e-notificacao.md",
    "spec-interface": "specs/interface-config-chat.md",
    "spec-barreira": "specs/barreira-entrada.md",
    "spec-core-api": "specs/core-api-objetos.md",
    "spec-meta-loop": "specs/meta-loop-chat.md",
}


def _fallback_slug(slug: str) -> str | None:
    rel = _SLUG_TO_PATH.get(slug)
    if rel is None:
        return None
    path = _DOCS_ROOT / rel
    if not path.exists():
        return None
    return _fallback_filesystem(rel, slug.replace("-", " ").title())


def _fallback_filesystem(rel_path: str, label: str) -> str:
    path = _DOCS_ROOT / rel_path
    if not path.exists():
        return f"❓ '{label}' não encontrado"
    body = path.read_text(encoding="utf-8")
    if body.startswith("---"):
        fim = body.find("\n---", 3)
        if fim != -1:
            body = body[fim + 4 :].lstrip("\n")
    if len(body) > _MAX_CHARS:
        body = body[:_MAX_CHARS]
        nl = body.rfind("\n")
        if nl > 0:
            body = body[:nl]
        body += f"\n\n… [truncado — arquivo: {rel_path}]"
    return f"📄 {label}\n\n{body}"


def _fallback_filesystem_adr(n: int) -> str:
    adr_dir = _DOCS_ROOT / "arquitetura" / "adr"
    if not adr_dir.exists():
        return "❓ diretório de ADRs não encontrado"
    padrao = f"ADR-{n:04d}-"
    for f in sorted(adr_dir.iterdir()):
        if f.name.startswith(padrao):
            return _fallback_filesystem(str(f.relative_to(_DOCS_ROOT)), f.stem)
    return f"❓ ADR-{n:04d} não encontrado"


def _fallback_listar_adrs() -> str:
    adr_dir = _DOCS_ROOT / "arquitetura" / "adr"
    if not adr_dir.exists():
        return "❓ diretório de ADRs não encontrado"
    adrs = sorted(f for f in adr_dir.iterdir() if f.suffix == ".md" and f.name != "README.md")
    linhas = [f"📋 ADRs ({len(adrs)})"]
    for f in adrs:
        partes = f.stem.split("-", 2)
        num = partes[1] if len(partes) > 1 else "?"
        titulo = partes[2].replace("-", " ") if len(partes) > 2 else f.stem
        linhas.append(f"  /docs adr {int(num)}  — {titulo}")
    return "\n".join(linhas)


def _indice_filesystem() -> str:
    return (
        "📚 Atlas docs (store não disponível — lendo do disco)\n\n"
        "  /docs kinds · /docs backlog · /docs arch · /docs constituicao\n"
        "  /docs adr <n> · /docs spec <nome>\n"
        "  /docs kind Tracker|Alarm|Timer|Goal|Tracker|Routine|Doc"
    )


def _parse_seletor(expr: str) -> dict[str, str]:
    selector: dict[str, str] = {}
    for par in expr.split(","):
        par = par.strip()
        if "=" in par:
            k, _, v = par.partition("=")
            selector[k.strip()] = v.strip()
    return selector
