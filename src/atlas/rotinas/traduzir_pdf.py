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


def _evento(msg: str) -> dict:
    """Linha de log de atividade (t + mensagem) para a view acompanhar ao vivo."""
    from datetime import datetime

    return {"t": datetime.now().isoformat(timespec="seconds"), "msg": msg}


def _eta(iniciado_iso: str, pct: int) -> int | None:
    """Estimativa grosseira de segundos restantes a partir do ritmo até agora."""
    if pct <= 0:
        return None
    from datetime import datetime

    try:
        decorrido = (datetime.now() - datetime.fromisoformat(iniciado_iso)).total_seconds()
    except (ValueError, TypeError):
        return None
    return int(decorrido * (100 - pct) / pct)


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
        modelo=t.spec.get("modelo") or None,
        refino=_verdade(t.spec.get("refino", True)),
        timeout=int(t.spec.get("timeout") or 60),
        lote_refino=int(t.spec.get("lote_refino") or 20),
        min_fonte_pct=int(t.spec.get("min_fonte_pct") or 90),
        notas_rodape=_verdade(t.spec.get("notas_rodape", False)),
    )

    iniciado = ctx.agora.isoformat()
    _status(
        store,
        t,
        ctx,
        {
            "fase": "preparando",
            "progresso_pct": 0,
            "saida": None,
            "erro": None,
            "iniciado_em": iniciado,
            "atividade": "abrindo PDF e preparando a tradução…",
            "log": [_evento("▶ tradução iniciada")],
        },
    )

    def on_progress(prog):
        atual = store.get("Traducao", t.name).status or {}
        log = list(atual.get("log") or [])
        if prog.fase == "glossario":
            msg = "🔤 detectando termos técnicos (glossário automático)…"
            patch = {"fase": "preparando", "progresso_pct": 0, "atividade": msg}
            log.append(_evento(msg))
        else:
            pct = int(prog.paginas_prontas * 100 / prog.paginas_total) if prog.paginas_total else 0
            msg = (
                f"📄 página {prog.paginas_prontas}/{prog.paginas_total} traduzida "
                f"· {prog.blocos_traduzidos} blocos"
            )
            patch = {
                "fase": "traduzindo",
                "paginas_total": prog.paginas_total,
                "paginas_prontas": prog.paginas_prontas,
                "blocos_traduzidos": prog.blocos_traduzidos,
                "progresso_pct": pct,
                "atividade": msg,
                "eta_seg": _eta(iniciado, pct),
            }
            # loga só marcos (1ª página, a cada 5, e a última) p/ não inflar o status
            if prog.paginas_prontas == 1 or prog.paginas_prontas % 5 == 0 or (
                prog.paginas_prontas == prog.paginas_total
            ):
                log.append(_evento(msg))
            if prog.glossario_auto and not atual.get("glossario_auto"):
                patch["glossario_auto"] = prog.glossario_auto
                log.append(_evento("🔤 glossário: " + ", ".join(prog.glossario_auto)))
        patch["log"] = log[-40:]  # mantém as últimas 40 linhas
        _status(store, t, ctx, patch)

    try:
        prog = traduzir_pdf(
            origem,
            saida,
            cfg,
            invocar_fn=invocar,
            on_progress=on_progress,
            cache=cache,
            cache_path=cache_path,
        )
    except Exception as exc:  # noqa: BLE001 — nunca derruba o loop (ADR-0006)
        _log.exception("traduzir-pdf/%s falhou", label)
        cache.salvar(cache_path)  # persiste o que já traduziu antes de falhar (resumível)
        _erro(store, t, ctx, str(exc))
        return CollectResult(data={"_saida": f"⚠️ traduzir-pdf/{label} falhou: {exc}"})

    cache.salvar(cache_path)  # persiste o cache p/ reruns baratos (ADR-0030/0031)
    log = list((store.get("Traducao", t.name).status or {}).get("log") or [])
    if prog.parcial:
        # tokens acabaram no meio: PDF saiu completo com o bruto; re-disparar refina o resto
        msg = f"⏸ parcial — {prog.paginas_prontas} páginas (tokens acabaram; re-disparar refina o restante)"
        fase = "parcial"
        atividade = "parcial: refino incompleto — re-disparar continua de onde parou"
    else:
        msg = f"✓ concluído — {prog.paginas_prontas} páginas, {prog.blocos_traduzidos} blocos"
        fase = "pronto"
        atividade = "tradução concluída"
    log.append(_evento(msg))
    _status(
        store,
        t,
        ctx,
        {
            "fase": fase,
            "saida": saida,
            "paginas_total": prog.paginas_total,
            "paginas_prontas": prog.paginas_prontas,
            "blocos_traduzidos": prog.blocos_traduzidos,
            "progresso_pct": 100,
            "parcial": prog.parcial,
            "glossario_auto": prog.glossario_auto,
            "atividade": atividade,
            "eta_seg": 0,
            "log": log[-40:],
            "erro": None,
        },
    )
    marca = "⏸" if prog.parcial else "✓"
    return CollectResult(
        data={"_saida": f"{marca} traduzir-pdf/{label}: {prog.paginas_prontas} páginas → {saida}"}
    )


def _status(store, t, ctx, patch: dict) -> None:
    novo = {**(store.get("Traducao", t.name).status or {}), **patch}
    store.set_status("Traducao", t.name, novo, ctx.agora)


def _erro(store, t, ctx, msg: str) -> None:
    log = list((store.get("Traducao", t.name).status or {}).get("log") or [])
    log.append(_evento(f"⚠️ erro: {msg}"))
    _status(
        store,
        t,
        ctx,
        {"fase": "erro", "progresso_pct": 0, "erro": msg, "atividade": f"erro: {msg}", "log": log[-40:]},
    )
