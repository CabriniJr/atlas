"""Estágio 1 do estágio 2 (ADR-0031): tradução **bruta** por MT real.

Usa ``deep-translator`` (GoogleTranslator) para produzir uma tradução completa —
rápida e barata — que o refino por LLM depois compara com a origem e melhora. O
bruto nunca perde informação: já é uma tradução inteira, só mais "crua". Falha de
rede/serviço num item devolve o texto original (o refino ainda pode traduzir).
"""

from __future__ import annotations

from atlas.traducao.traducao_ia import ConfigTraducao


def _cod_idioma(idioma: str) -> str:
    """Normaliza 'pt-BR' → 'pt', 'en' → 'en' para os códigos do GoogleTranslator."""
    idioma = (idioma or "").strip().lower()
    combinados = {"zh-cn", "zh-tw", "pt-br", "pt-pt"}
    if idioma in combinados:
        # Google usa 'pt' para pt-BR; mantém 'zh-CN'/'zh-TW' com hífen/caixa original.
        return "pt" if idioma.startswith("pt") else idioma
    return idioma.split("-")[0] or "auto"


def traduzir_bruto(textos: list[str], cfg: ConfigTraducao) -> list[str]:
    """Traduz uma lista de textos com MT. Preserva a ordem; item vazio ⇒ vazio."""
    if not textos:
        return []
    from deep_translator import GoogleTranslator

    tradutor = GoogleTranslator(
        source=_cod_idioma(cfg.idioma_origem), target=_cod_idioma(cfg.idioma_destino)
    )
    saida: list[str] = []
    for t in textos:
        if not t or not t.strip():
            saida.append(t)
            continue
        try:
            saida.append(tradutor.translate(t) or t)
        except Exception:  # noqa: BLE001 — MT best-effort; refino ainda pode salvar o bloco
            saida.append(t)
    return saida
