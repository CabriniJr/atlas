"""Collect acoplável ``traduzir-pdf`` — traduz um Kind ``Traducao`` (ADR-0030).

Espelha ``rotinas/prompt.py``: a rotina aponta um ``Traducao/<label>``; o collect
lê o spec, roda o pipeline de tradução e grava progresso/saída no ``status``.
On-demand (via ``/run``/API), não por cron. O ``status.progresso_pct`` alimenta a
barra de progresso do web shell (ADR-0029).
"""

from __future__ import annotations

import logging
from pathlib import Path

from atlas.executor import CollectResult, ContextoExecucao
from atlas.ia import invocar
from atlas.rotinas import registrar
from atlas.traducao.pipeline import traduzir_pdf
from atlas.traducao.traducao_ia import CacheTraducao, ConfigTraducao

_log = logging.getLogger(__name__)


def _saida_para(origem: str, idioma_destino: str) -> str:
    p = Path(origem)
    return str(p.with_suffix(f".{idioma_destino}.pdf"))


def _cache_para(origem: str, idioma_destino: str) -> str:
    p = Path(origem)
    return str(p.with_suffix(f".{idioma_destino}.cache.json"))


def _verdade(v) -> bool:
    """Aceita bool ou string ('true'/'false' do form do web shell) como booleano."""
    if isinstance(v, str):
        return v.strip().lower() in {"true", "1", "sim", "yes"}
    return bool(v)


@registrar("traduzir-pdf")
def collect(ctx: ContextoExecucao) -> CollectResult:
    label = getattr(ctx.rotina, "label", None) or ctx.rotina.nome
    store = getattr(ctx, "store", None)
    if store is None:
        return CollectResult(data={"_saida": f"⚠️ traduzir-pdf/{label}: store indisponível."})

    t = store.get("Traducao", label)
    if t is None:
        return CollectResult(
            data={
                "_saida": (
                    f"❓ traduzir-pdf/{label}: Traducao não encontrada.\n"
                    f'Crie com: /apply Traducao {label} spec.origem="data/pdfs/x.pdf"'
                )
            }
        )

    origem = (t.spec.get("origem") or "").strip()
    if not origem or not Path(origem).exists():
        _erro(store, t, ctx, f"origem ausente/inexistente: {origem!r}")
        return CollectResult(
            data={"_saida": f"⚠️ traduzir-pdf/{label}: origem inválida ({origem!r})."}
        )

    idioma_destino = t.spec.get("idioma_destino", "pt-BR")
    saida = _saida_para(origem, idioma_destino)
    cache_path = _cache_para(origem, idioma_destino)
    cache = CacheTraducao.carregar(cache_path)  # reusa traduções de runs anteriores
    cfg = ConfigTraducao(
        idioma_origem=t.spec.get("idioma_origem", "en"),
        idioma_destino=idioma_destino,
        assunto=t.spec.get("assunto", ""),
        glossario=list(t.spec.get("glossario", []) or []),
        glossario_auto=_verdade(t.spec.get("glossario_auto", False)),
        motor=t.spec.get("motor", "claude"),
        modelo=t.spec.get("modelo"),
    )

    _status(store, t, ctx, {"fase": "traduzindo", "progresso_pct": 0, "saida": None, "erro": None})

    def on_progress(prog):
        pct = int(prog.paginas_prontas * 100 / prog.paginas_total) if prog.paginas_total else 0
        _status(
            store,
            t,
            ctx,
            {
                "fase": "traduzindo",
                "paginas_total": prog.paginas_total,
                "paginas_prontas": prog.paginas_prontas,
                "progresso_pct": pct,
            },
        )

    try:
        prog = traduzir_pdf(
            origem, saida, cfg, invocar_fn=invocar, on_progress=on_progress, cache=cache
        )
    except Exception as exc:  # noqa: BLE001 — nunca derruba o loop (ADR-0006)
        _log.exception("traduzir-pdf/%s falhou", label)
        cache.salvar(cache_path)  # persiste o que já traduziu antes de falhar (resumível)
        _erro(store, t, ctx, str(exc))
        return CollectResult(data={"_saida": f"⚠️ traduzir-pdf/{label} falhou: {exc}"})

    cache.salvar(cache_path)  # persiste o cache p/ reruns baratos (ADR-0030)
    _status(
        store,
        t,
        ctx,
        {
            "fase": "pronto",
            "saida": saida,
            "paginas_total": prog.paginas_total,
            "paginas_prontas": prog.paginas_prontas,
            "progresso_pct": 100,
            "glossario_auto": prog.glossario_auto,
            "erro": None,
        },
    )
    return CollectResult(
        data={"_saida": f"✓ traduzir-pdf/{label}: {prog.paginas_prontas} páginas → {saida}"}
    )


def _status(store, t, ctx, patch: dict) -> None:
    novo = {**(store.get("Traducao", t.name).status or {}), **patch}
    store.set_status("Traducao", t.name, novo, ctx.agora)


def _erro(store, t, ctx, msg: str) -> None:
    _status(store, t, ctx, {"fase": "erro", "progresso_pct": 0, "erro": msg})
