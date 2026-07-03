"""Dois estágios (MT bruta + refino) e resume por esgotamento de tokens (ADR-0031)."""

from __future__ import annotations

import fitz

from atlas.ia import InvocarErro
from atlas.traducao.extracao import BlocoTraducao
from atlas.traducao.pipeline import traduzir_pdf
from atlas.traducao.traducao_ia import CacheTraducao, ConfigTraducao, refinar_blocos
from atlas.traducao.tradutor_bruto import _cod_idioma


def _blocos(*textos):
    return [BlocoTraducao(id=i, pagina=0, bbox=(0, 0, 1, 1), texto=t) for i, t in enumerate(textos)]


def _pdf(path, *linhas):
    doc = fitz.open()
    p = doc.new_page()
    y = 100
    for ln in linhas:
        p.insert_text((72, y), ln, fontname="helv", fontsize=12)
        y += 40
    doc.save(str(path))
    doc.close()


def test_cod_idioma():
    assert _cod_idioma("pt-BR") == "pt"
    assert _cod_idioma("en") == "en"
    assert _cod_idioma("zh-CN") == "zh-cn"


def test_refino_usa_bruto_e_origem_no_prompt():
    blocos = _blocos("The pod scales.")
    brutos = {0: "O pod escala."}
    cfg = ConfigTraducao(glossario=["pod"])
    cache = CacheTraducao()
    visto = {}

    def fake(prompt, modelo=None, timeout=60, motor="claude"):
        visto["prompt"] = prompt
        return "[[0]] O pod dimensiona automaticamente."

    res, esgotou, motivo = refinar_blocos(blocos, brutos, cfg, cache, invocar_fn=fake)
    assert not esgotou
    assert motivo is None
    assert res[0] == "O pod dimensiona automaticamente."
    assert "ORIGEM: The pod scales." in visto["prompt"]
    assert "BRUTO: O pod escala." in visto["prompt"]
    # refinado foi cacheado (resume barato)
    assert cache.get("The pod scales.", cfg) == "O pod dimensiona automaticamente."


def test_refino_esgota_tokens_cai_para_bruto_sem_cachear():
    blocos = _blocos("A.", "B.", "C.")
    brutos = {0: "a", 1: "b", 2: "c"}
    cfg = ConfigTraducao(lote_refino=1)
    cache = CacheTraducao()
    chamadas = {"n": 0}

    def fake(prompt, modelo=None, timeout=60, motor="claude"):
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            return "[[0]] A refinado"
        raise InvocarErro("sem tokens")  # 2º lote falha

    res, esgotou, motivo = refinar_blocos(blocos, brutos, cfg, cache, invocar_fn=fake)
    assert esgotou
    assert motivo == "erro"  # "sem tokens" não contém "timeout" (ADR-0039)
    assert res[0] == "A refinado"  # 1º refinado
    assert res[1] == "b" and res[2] == "c"  # restante = bruto (sem perda)
    assert cache.get("A.", cfg) == "A refinado"  # só o refinado é cacheado
    assert cache.get("B.", cfg) is None  # bruto não cacheado ⇒ retry no próximo run


def test_refino_classifica_timeout_para_retry_curto(monkeypatch):
    """ADR-0039: falha de timeout é elegível a retry curto (5min); outro erro
    (ex.: rate-limit) vai direto pra escassez confirmada (5h)."""
    from atlas.ia import InvocarErro as IAErro

    blocos = _blocos("A.")
    brutos = {0: "a"}
    cfg = ConfigTraducao()
    cache = CacheTraducao()

    def timeout_fn(*a, **k):
        raise IAErro("timeout após 60s invocando IA")

    _, esgotou, motivo = refinar_blocos(blocos, brutos, cfg, cache, invocar_fn=timeout_fn)
    assert esgotou and motivo == "timeout"

    def rate_limit_fn(*a, **k):
        raise IAErro("rate_limit_error: você atingiu o limite de uso")

    _, esgotou2, motivo2 = refinar_blocos(blocos, brutos, cfg, cache, invocar_fn=rate_limit_fn)
    assert esgotou2 and motivo2 == "erro"


def test_refino_desligado_traducao_puramente_mt(tmp_path):
    src = tmp_path / "l.pdf"
    _pdf(src, "The pod scales.")
    cfg = ConfigTraducao(refino=False)

    def nunca(*a, **k):
        raise AssertionError("não deve chamar LLM quando refino=False")

    # marcador não-caixa-alta: um texto TODO em maiúscula seria convertido em
    # versalete no render (caixa-baixa), então usa-se um sufixo como sentinela.
    prog = traduzir_pdf(
        str(src),
        str(tmp_path / "o.pdf"),
        cfg,
        invocar_fn=nunca,
        bruto_fn=lambda ts, c: [f"{t} [mt]" for t in ts],
    )
    assert not prog.parcial
    # normaliza espaços: a fonte embutida pode quebrar a linha diferente do original.
    import re as _re

    saida = _re.sub(r"\s+", " ", fitz.open(str(tmp_path / "o.pdf"))[0].get_text())
    assert "The pod scales. [mt]" in saida


def test_pipeline_parcial_quando_tokens_acabam(tmp_path):
    src = tmp_path / "l.pdf"
    _pdf(src, "First line here.", "Second line here.")
    cfg = ConfigTraducao(lote_refino=1)

    def fake(prompt, modelo=None, timeout=60, motor="claude"):
        raise InvocarErro("tokens acabaram")

    out = tmp_path / "o.pdf"
    prog = traduzir_pdf(
        str(src), str(out), cfg, invocar_fn=fake, bruto_fn=lambda ts, c: [f"BR:{t}" for t in ts]
    )
    assert prog.parcial  # esgotou ⇒ parcial
    # PDF saiu completo com o bruto (sem perda)
    assert "BR:" in fitz.open(str(out))[0].get_text()


def test_resume_do_cache_em_disco(tmp_path):
    """Run 1 refina 1 bloco e para; run 2 refina o restante reusando o cache."""
    src = tmp_path / "l.pdf"
    _pdf(src, "Alpha line.", "Beta line.")
    cache_path = str(tmp_path / "c.json")
    cfg = ConfigTraducao(lote_refino=1)

    estado = {"falhar_depois": 1, "n": 0}

    def fake(prompt, modelo=None, timeout=60, motor="claude"):
        estado["n"] += 1
        if estado["n"] > estado["falhar_depois"]:
            raise InvocarErro("sem tokens")
        import re

        i = re.search(r"\[\[(\d+)\]\]", prompt).group(1)
        return f"[[{i}]] REF{i}"

    # Run 1: refina 1, esgota no 2 → parcial
    p1 = traduzir_pdf(
        str(src),
        str(tmp_path / "o1.pdf"),
        cfg,
        invocar_fn=fake,
        cache=CacheTraducao.carregar(cache_path),
        cache_path=cache_path,
        bruto_fn=lambda ts, c: [f"BR:{t}" for t in ts],
    )
    assert p1.parcial

    # Run 2: agora com tokens; deve refinar o que ficou (só chama p/ o bloco pendente)
    estado["falhar_depois"] = 99
    n_antes = estado["n"]
    p2 = traduzir_pdf(
        str(src),
        str(tmp_path / "o2.pdf"),
        cfg,
        invocar_fn=fake,
        cache=CacheTraducao.carregar(cache_path),
        cache_path=cache_path,
        bruto_fn=lambda ts, c: [f"BR:{t}" for t in ts],
    )
    assert not p2.parcial
    # o bloco já refinado no run 1 veio do cache (não re-chamou p/ ele)
    assert estado["n"] - n_antes <= 2
    texto = fitz.open(str(tmp_path / "o2.pdf"))[0].get_text()
    assert "REF0" in texto and "REF1" in texto
