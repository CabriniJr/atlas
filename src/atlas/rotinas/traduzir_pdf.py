"""Collect acoplável ``traduzir-pdf`` — traduz um Kind ``Traducao`` (ADR-0030).

Espelha ``rotinas/prompt.py``: a rotina aponta um ``Traducao/<label>``; o collect
lê o spec, roda o pipeline de tradução e grava progresso/saída no ``status``.
On-demand (via ``/run``/API), não por cron. O ``status.progresso_pct`` alimenta a
barra de progresso do web shell (ADR-0029).
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from pathlib import Path

from atlas.executor import CollectResult, ContextoExecucao
from atlas.ia import InvocarErro, invocar
from atlas.retomada import campos_pausa
from atlas.rotinas import registrar
from atlas.traducao.pipeline import traduzir_pdf
from atlas.traducao.pool import pool_global
from atlas.traducao.traducao_ia import (
    CacheTraducao,
    ConfigTraducao,
    _classificar_erro,
    resolver_agente_refino,
)

_log = logging.getLogger(__name__)


def montar_invocar_escalavel(cfg: ConfigTraducao, on_escala=None, lock=None):
    """Wrapper de ``ia.invocar`` com escalada de MOTOR no nível do job (E9-16/ADR-0048).

    Contrato (substitui o `fallback=False` cru do ADR-0045):
    - Nunca troca de motor por chamada às escondidas (o problema que o 0045 evitou).
    - Motor pedido (``cfg.motor``, default ollama) é usado à risca enquanto funciona.
    - Erro de CONEXÃO no ollama (endpoint fora): tenta rápido até
      ``cfg.escalonar_apos_falhas`` vezes; esgotado, muta ``cfg.motor`` para
      ``cfg.escalonar_para`` (Claude) — o RESTANTE do job vai pro Claude, visível
      via ``on_escala`` — e retenta ESTA chamada no novo motor (modelo=None, nunca
      herda o modelo do outro motor). ``cfg.motor`` é a fonte única do motor atual,
      relida pelo pipeline a cada lote, então a escalada vale pro resto do job.
    - Timeout/erro no ollama propaga direto: o pipeline aplica o retry/pausa do
      ADR-0039 (Ollama ocupado ≠ Ollama fora; cota do Claude recupera com o tempo).
    - Já em Claude (pedido ou escalado): comportamento do 0039 intacto.
    """
    lock = lock or threading.Lock()

    def inv(prompt, modelo=None, timeout=60, motor="claude"):
        motor_atual = motor  # == cfg.motor no momento da chamada (pipeline relê)
        if motor_atual != "ollama":
            return invocar(prompt, modelo=modelo, timeout=timeout, motor=motor_atual, fallback=False)
        ultimo: Exception | None = None
        for _ in range(max(1, cfg.escalonar_apos_falhas)):
            try:
                return invocar(prompt, modelo=modelo, timeout=timeout, motor="ollama", fallback=False)
            except InvocarErro as exc:
                if _classificar_erro(exc) != "conexao":
                    raise  # timeout/erro → ADR-0039 no pipeline
                ultimo = exc
        # esgotou as tentativas de conexão no ollama → escala o restante do job.
        with lock:
            if cfg.motor == "ollama":
                cfg.motor = cfg.escalonar_para
                cfg.modelo = None  # não herda modelo do ollama no motor de destino
                if on_escala is not None:
                    on_escala("ollama", cfg.escalonar_para, str(ultimo))
        return invocar(prompt, modelo=None, timeout=timeout, motor=cfg.escalonar_para, fallback=False)

    return inv


def _saida_para(origem: str, idioma_destino: str) -> str:
    p = Path(origem)
    return str(p.with_suffix(f".{idioma_destino}.pdf"))


def _cache_para(origem: str, idioma_destino: str) -> str:
    p = Path(origem)
    return str(p.with_suffix(f".{idioma_destino}.cache.json"))


def _previa_para(origem: str, idioma_destino: str, variante: str = "refino") -> str:
    p = Path(origem)
    sufixo = "previa.pdf" if variante == "refino" else "previa.bruto.pdf"
    return str(p.with_suffix(f".{idioma_destino}.{sufixo}"))


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
        comparador=_verdade(t.spec.get("comparador", False)),
        modelo_comparador=t.spec.get("modelo_comparador") or None,
        render_motor=(t.spec.get("render_motor") or "html"),
        max_tentativas_timeout=int(t.spec.get("max_tentativas_timeout") or 5),
        janela_retry_timeout_seg=int(t.spec.get("janela_retry_timeout_seg") or 300),
    )
    # Agente de refino (ADR-0040, opt-in via spec.agente_refino): dita
    # motor/modelo/persona do refino, sobrepondo os campos próprios acima —
    # mesmo padrão do Repo.spec.analyze_agente (ADR-0024 regra 2).
    motor_ag, modelo_ag, instrucao_ag = resolver_agente_refino(t, store)
    if motor_ag:
        cfg.motor = motor_ag
    if modelo_ag:
        cfg.modelo = modelo_ag
    if instrucao_ag:
        cfg.instrucao_refino = instrucao_ag

    def _on_escala(de: str, para: str, motivo: str) -> None:
        atual = store.get("Traducao", t.name).status or {}
        log = list(atual.get("log") or [])
        log.append(_evento(f"⚡ motor {de} indisponível — escalado p/ {para}"))
        _status(
            store, t, ctx,
            {
                "motor_efetivo": para,
                "escalonado_em": ctx.agora.isoformat(),
                "escalonado_motivo": (motivo or "")[:200],
                "log": log[-40:],
            },
        )

    invocar_escalavel = montar_invocar_escalavel(cfg, on_escala=_on_escala)
    # tentativas curtas por timeout até aqui (ADR-0039) — persistido, sobrevive a restart.
    tentativas_timeout = int((t.status or {}).get("tentativas_timeout") or 0)

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
            "pausar_solicitado": False,  # reseta um pedido de pausa de um run anterior
            "motor_efetivo": cfg.motor,  # E9-16: motor realmente em uso (muda se escalar)
        },
    )

    def checar_pausa() -> bool:
        atual = store.get("Traducao", t.name).status or {}
        return bool(atual.get("pausar_solicitado"))

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
            if (
                prog.paginas_prontas == 1
                or prog.paginas_prontas % 5 == 0
                or (prog.paginas_prontas == prog.paginas_total)
            ):
                log.append(_evento(msg))
            if prog.glossario_auto and not atual.get("glossario_auto"):
                patch["glossario_auto"] = prog.glossario_auto
                log.append(_evento("🔤 glossário: " + ", ".join(prog.glossario_auto)))
        patch["log"] = log[-40:]  # mantém as últimas 40 linhas
        _status(store, t, ctx, patch)

    def on_evento(ev):
        """Log fino: uma linha por chamada de IA no refino (visibilidade do gasto)."""
        if ev.get("tipo") != "refino_lote":
            return
        atual = store.get("Traducao", t.name).status or {}
        linhas = list(atual.get("log_ia") or [])
        seg = ev.get("ms", 0) / 1000
        cab = (
            f"p.{ev.get('pagina', '?')} · lote {ev.get('lote')}/{ev.get('lotes')} · "
            f"{ev.get('blocos')} blocos · {ev.get('chars', 0)} chars · {seg:.1f}s · "
            f"{ev.get('modelo', '')}"
        )
        if not ev.get("ok"):
            cab += f" · ✗ {ev.get('erro', 'falhou')}"
        linhas.append({**_evento(cab), "ok": bool(ev.get("ok"))})
        _status(store, t, ctx, {"log_ia": linhas[-100:]})

    try:
        prog = traduzir_pdf(
            origem,
            saida,
            cfg,
            invocar_fn=invocar_escalavel,
            on_progress=on_progress,
            cache=cache,
            cache_path=cache_path,
            somente_render=_verdade(t.spec.get("somente_render", False)),
            on_evento=on_evento,
            paralelismo=pool_global.max_concorrente,  # ADR-0039: réplicas também dentro do job
            checar_pausa=checar_pausa,  # E9-16: honrado nos dois loops (sequencial + paralelo)
            preferir_bruto=_verdade(t.spec.get("preferir_bruto", False)),  # E9-15
        )
    except Exception as exc:  # noqa: BLE001 — nunca derruba o loop (ADR-0006)
        _log.exception("traduzir-pdf/%s falhou", label)
        cache.salvar(cache_path)  # persiste o que já traduziu antes de falhar (resumível)
        _erro(store, t, ctx, str(exc))
        return CollectResult(data={"_saida": f"⚠️ traduzir-pdf/{label} falhou: {exc}"})

    cache.salvar(cache_path)  # persiste o cache p/ reruns baratos (ADR-0030/0031)
    log = list((store.get("Traducao", t.name).status or {}).get("log") or [])
    pausa: dict = {}
    nova_tentativa = 0  # reseta por padrão (sucesso ou escassez confirmada — ADR-0039)
    if prog.parcial:
        retry_curto = (
            prog.motivo_pausa == "timeout" and tentativas_timeout + 1 <= cfg.max_tentativas_timeout
        )
        if prog.motivo_pausa == "manual":
            # pausa pedida pelo usuário (ADR-0045): sem retoma_em/retoma_collect —
            # o loop de retomada automática (ADR-0035) nunca dispara sozinho aqui;
            # só o botão "Retomar agora" (mesmo caminho de /_traduzir) continua.
            pausa = {"fase": "pausado"}
            msg = f"⏸ pausado manualmente — {prog.paginas_prontas} páginas prontas"
            atividade = "pausado manualmente — clique em retomar quando quiser"
        elif retry_curto:
            # timeout pontual: retry curto persistido (ADR-0039) — até
            # max_tentativas_timeout vezes antes de declarar escassez de verdade.
            nova_tentativa = tentativas_timeout + 1
            janela = cfg.janela_retry_timeout_seg
            pausa = campos_pausa(ctx.agora, janela, "traduzir-pdf")
            quando = datetime.fromisoformat(pausa["retoma_em"]).strftime("%H:%M")
            msg = (
                f"⏱ timeout — tentativa {nova_tentativa}/{cfg.max_tentativas_timeout}; "
                f"retry sozinho às {quando} ({janela // 60}min, continua de onde parou)"
            )
            atividade = (
                f"pausado (timeout {nova_tentativa}/{cfg.max_tentativas_timeout}) "
                f"— retry às {quando}"
            )
        else:
            # escassez confirmada: erro não-timeout, ou as tentativas curtas
            # já se esgotaram — aí sim é garantido que é limite de cota.
            janela = int(t.spec.get("janela_retomada_seg") or 18000)  # default 5 h
            pausa = campos_pausa(ctx.agora, janela, "traduzir-pdf")
            quando = datetime.fromisoformat(pausa["retoma_em"]).strftime("%H:%M")
            msg = (
                f"⏸ pausado por escassez — {prog.paginas_prontas} páginas; "
                f"retoma sozinho às {quando} (continua de onde parou)"
            )
            atividade = f"pausado (falha em {cfg.motor}) — retomada automática às {quando}"
    else:
        msg = f"✓ concluído — {prog.paginas_prontas} páginas, {prog.blocos_traduzidos} blocos"
        atividade = "tradução concluída"
    log.append(_evento(msg))
    _status(
        store,
        t,
        ctx,
        {
            "fase": "pronto",
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
            "tentativas_timeout": nova_tentativa,  # ADR-0039: persistido p/ sobreviver a restart
            **pausa,  # ADR-0035: fase="pausado" + retoma_em + retoma_collect (só se parcial)
        },
    )
    marca = "⏸" if prog.parcial else "✓"
    return CollectResult(
        data={"_saida": f"{marca} traduzir-pdf/{label}: {prog.paginas_prontas} páginas → {saida}"}
    )


def _merge_status(store, name, agora, patch: dict) -> None:
    novo = {**(store.get("Traducao", name).status or {}), **patch}
    store.set_status("Traducao", name, novo, agora)


def pausar_traducao(store, label: str, agora: datetime) -> tuple[bool, str]:
    """Pede pausa manual (ADR-0045): só marca o pedido — o loop em curso é quem
    para, entre páginas (``checar_pausa`` em ``collect``). Devolve
    ``(ok, mensagem)``."""
    t = store.get("Traducao", label)
    if t is None:
        return False, f"Traducao/{label} not found"
    fase = (t.status or {}).get("fase")
    if fase not in ("traduzindo", "preparando"):
        return False, f"Traducao/{label} não está rodando (fase={fase!r})"
    _merge_status(store, label, agora, {"pausar_solicitado": True})
    return True, "pausa solicitada — para entre páginas"


def reiniciar_traducao(store, label: str, agora: datetime) -> tuple[bool, str]:
    """ "Recomeçar do zero" (ADR-0045): apaga o cache (MT bruta + refinado) do
    ``Traducao``/label — o próximo ``/_traduzir`` paga tudo de novo. Não mexe
    no PDF de origem. Devolve ``(ok, mensagem)``."""
    t = store.get("Traducao", label)
    if t is None:
        return False, f"Traducao/{label} not found"
    fase = (t.status or {}).get("fase")
    if fase in ("traduzindo", "preparando", "fila"):
        return False, f"Traducao/{label} está rodando (fase={fase!r}) — pause antes"
    origem = (t.spec.get("origem") or "").strip()
    if origem:
        Path(_cache_para(origem, t.spec.get("idioma_destino", "pt-BR"))).unlink(missing_ok=True)
    store.set_status("Traducao", label, {}, agora)
    return True, "cache apagado — próxima tradução recomeça do zero"


def re_refinar_traducao(store, label: str, agora: datetime) -> tuple[bool, str]:
    """ "Re-refinar" (ADR-0045): descarta só o REFINADO cacheado (mantém a MT
    bruta, que é a parte mais lenta/cara) — útil depois de trocar o
    ``agente_refino``/modelo e querer um refino melhor sem repagar a MT.
    Devolve ``(ok, mensagem)``."""
    import fitz

    from atlas.traducao.extracao import extrair_pagina

    t = store.get("Traducao", label)
    if t is None:
        return False, f"Traducao/{label} not found"
    fase = (t.status or {}).get("fase")
    if fase in ("traduzindo", "preparando", "fila"):
        return False, f"Traducao/{label} está rodando (fase={fase!r}) — pause antes"
    origem = (t.spec.get("origem") or "").strip()
    if not origem or not Path(origem).exists():
        return False, f"origem inválida: {origem!r}"
    idioma_destino = t.spec.get("idioma_destino", "pt-BR")
    cache_path = _cache_para(origem, idioma_destino)
    cache = CacheTraducao.carregar(cache_path)
    cfg_chave = ConfigTraducao(
        idioma_origem=t.spec.get("idioma_origem", "en"), idioma_destino=idioma_destino
    )
    doc = fitz.open(origem)
    removidos = 0
    for i in range(doc.page_count):
        for b in extrair_pagina(doc[i], i):
            if not b.skip and cache.remover(b.texto, cfg_chave):
                removidos += 1
    doc.close()
    cache.salvar(cache_path)
    novo_status = {**(t.status or {}), "fase": "parcial", "parcial": True}
    store.set_status("Traducao", label, novo_status, agora)
    return True, f"{removidos} bloco(s) refinado(s) descartado(s) — MT bruta preservada"


def render_previa(store, label: str, agora: datetime, variante: str = "refino") -> None:
    """Renderiza uma PRÉVIA do cache atual (parcial) → ``.previa.pdf`` (refino) ou
    ``.previa.bruto.pdf`` (E9-15: ``variante="bruto"``, MT crua mesmo se o refino já
    existe), sem tocar na ``fase`` da tradução em curso (E9: renderizar enquanto
    traduz). Zero IA; roda em thread de background disparada pela API. Best-effort
    — nunca levanta (ADR-0006)."""
    t = store.get("Traducao", label)
    if t is None:
        return
    origem = (t.spec.get("origem") or "").strip()
    idioma_destino = t.spec.get("idioma_destino", "pt-BR")
    campo_previa = "previa" if variante == "refino" else "previa_bruto"
    if not origem or not Path(origem).exists():
        _merge_status(
            store, label, agora, {"previa_gerando": False, "previa_erro": "origem inválida"}
        )
        return
    previa = _previa_para(origem, idioma_destino, variante)
    cfg = ConfigTraducao(
        idioma_origem=t.spec.get("idioma_origem", "en"),
        idioma_destino=idioma_destino,
        min_fonte_pct=int(t.spec.get("min_fonte_pct") or 90),
        notas_rodape=_verdade(t.spec.get("notas_rodape", False)),
        render_motor=(t.spec.get("render_motor") or "html"),
    )
    _merge_status(store, label, agora, {"previa_gerando": True, "previa_erro": None})

    def _sem_ia(*a, **k):
        raise RuntimeError("IA não deve ser chamada na prévia (somente_render)")

    try:
        cache = CacheTraducao.carregar(_cache_para(origem, idioma_destino))
        traduzir_pdf(
            origem,
            previa,
            cfg,
            invocar_fn=_sem_ia,
            cache=cache,
            somente_render=True,
            preferir_bruto=(variante == "bruto"),
        )
        _merge_status(
            store,
            label,
            datetime.now(),
            {
                campo_previa: previa,
                "previa_gerando": False,
                "previa_em": datetime.now().isoformat(timespec="seconds"),
            },
        )
    except Exception as exc:  # noqa: BLE001
        _log.exception("prévia de %s falhou", label)
        _merge_status(
            store, label, datetime.now(), {"previa_gerando": False, "previa_erro": str(exc)}
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
        {
            "fase": "erro",
            "progresso_pct": 0,
            "erro": msg,
            "atividade": f"erro: {msg}",
            "log": log[-40:],
        },
    )
