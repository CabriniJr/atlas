"""Tradução de blocos via IA (ADR-0030, estágio 2).

Envia blocos numerados ao ``ia.invocar`` num único prompt (batch), com instrução
de tradução técnica + glossário (termos que ficam em inglês). Cache por hash do
texto normalizado evita repagar blocos idênticos (repetições, reprocessamento).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from atlas.ia import _MODELO_PADRAO
from atlas.ia import invocar as _invocar_padrao
from atlas.traducao.extracao import BlocoTraducao

_RE_BLOCO = re.compile(r"\[\[(\d+)\]\]\s*(.*?)(?=\n\[\[\d+\]\]|\Z)", re.DOTALL)


@dataclass
class ConfigTraducao:
    idioma_origem: str = "en"
    idioma_destino: str = "pt-BR"
    assunto: str = ""
    glossario: list[str] = field(default_factory=list)
    glossario_auto: bool = False
    motor: str = "claude"
    modelo: str | None = None
    refino: bool = True  # ADR-0031: LLM refina o bruto (False = tradução puramente MT)
    timeout: int = 60  # timeout por chamada de refino
    lote_refino: int = 20  # blocos por chamada de refino (limita gasto/timeout, dá resume)


class CacheTraducao:
    """Cache texto-normalizado → tradução. Opcionalmente persistido em JSON."""

    def __init__(self, inicial: dict[str, str] | None = None) -> None:
        self._d: dict[str, str] = dict(inicial or {})

    @staticmethod
    def _chave(texto: str, cfg: ConfigTraducao) -> str:
        base = f"{cfg.idioma_origem}>{cfg.idioma_destino}:{texto.strip()}"
        return hashlib.sha256(base.encode("utf-8")).hexdigest()

    def get(self, texto: str, cfg: ConfigTraducao) -> str | None:
        return self._d.get(self._chave(texto, cfg))

    def put(self, texto: str, cfg: ConfigTraducao, traducao: str) -> None:
        self._d[self._chave(texto, cfg)] = traducao

    def to_dict(self) -> dict[str, str]:
        return dict(self._d)

    @classmethod
    def carregar(cls, path: str | Path) -> CacheTraducao:
        """Carrega o cache de um JSON em disco; ausente/corrompido ⇒ cache vazio."""
        try:
            dados = json.loads(Path(path).read_text(encoding="utf-8"))
            if isinstance(dados, dict):
                return cls({str(k): str(v) for k, v in dados.items()})
        except (OSError, ValueError):
            pass
        return cls()

    def salvar(self, path: str | Path) -> None:
        """Persiste o cache em JSON (cria o diretório se preciso)."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self._d, ensure_ascii=False), encoding="utf-8")


_RE_TERMO = re.compile(r"[A-Za-z][A-Za-z0-9._+-]{1,}")


def detectar_glossario(
    blocos: list[BlocoTraducao],
    cfg: ConfigTraducao,
    invocar_fn=_invocar_padrao,
    limite: int = 40,
) -> list[str]:
    """Detecta termos técnicos a preservar em inglês (glossario_auto, ADR-0030).

    Uma única chamada de IA sobre uma amostra dos blocos tradutíveis. Devolve a
    lista de termos (nomes de APIs, comandos, jargão) que **não** devem ser
    traduzidos. Robusto a ruído: só aceita termos que aparecem no texto amostrado.
    """
    amostra = [b.texto for b in blocos if not b.skip][:limite]
    if not amostra:
        return []
    corpus = "\n".join(amostra)
    prompt = (
        f"Abaixo, trechos de um livro técnico sobre {cfg.assunto or 'tecnologia'} "
        f"em {cfg.idioma_origem}. Liste os termos técnicos que devem permanecer em "
        f"inglês numa tradução para {cfg.idioma_destino}: nomes de APIs, comandos, "
        f"ferramentas e jargão consagrado. Responda APENAS os termos separados por "
        f"vírgula, sem explicações.\n\n{corpus}"
    )
    try:
        resposta = invocar_fn(prompt, modelo=cfg.modelo or _MODELO_PADRAO, motor=cfg.motor)
    except Exception:  # noqa: BLE001 — detecção é best-effort; falha não derruba a tradução
        return []

    presentes = {t.strip("._+-").lower() for t in _RE_TERMO.findall(corpus)}
    vistos: set[str] = set()
    termos: list[str] = []
    for bruto in resposta.replace("\n", ",").split(","):
        termo = bruto.strip().strip(".;:")
        low = termo.lower()
        if termo and low in presentes and low not in vistos:
            vistos.add(low)
            termos.append(termo)
    return termos


def montar_prompt(blocos: list[BlocoTraducao], cfg: ConfigTraducao) -> str:
    glossario = ", ".join(cfg.glossario) if cfg.glossario else "(nenhum)"
    corpo = "\n".join(f"[[{b.id}]] {b.texto}" for b in blocos)
    return (
        f"Traduza de {cfg.idioma_origem} para {cfg.idioma_destino} o texto de um livro "
        f"técnico sobre: {cfg.assunto or 'tecnologia'}.\n"
        f"Regras: preserve o tom técnico; NÃO traduza termos técnicos, nomes de APIs, "
        f"comandos ou código; mantenha em inglês os termos do glossário: {glossario}.\n"
        f"Responda cada bloco no MESMO formato numerado, sem comentários extras:\n"
        f"[[N]] <tradução>\n\n{corpo}"
    )


def parsear_resposta(resposta: str, ids: list[int]) -> dict[int, str]:
    achados = {int(n): t.strip() for n, t in _RE_BLOCO.findall(resposta)}
    return {i: achados[i] for i in ids if i in achados}


def traduzir_blocos(
    blocos: list[BlocoTraducao],
    cfg: ConfigTraducao,
    cache: CacheTraducao,
    invocar_fn=_invocar_padrao,
) -> dict[int, str]:
    resultado: dict[int, str] = {}
    pendentes: list[BlocoTraducao] = []
    for b in blocos:
        cached = cache.get(b.texto, cfg)
        if cached is not None:
            resultado[b.id] = cached
        else:
            pendentes.append(b)
    if pendentes:
        prompt = montar_prompt(pendentes, cfg)
        # cfg.modelo pode ser None → usa o padrão do motor (invocar não aceita None).
        resposta = invocar_fn(prompt, modelo=cfg.modelo or _MODELO_PADRAO, motor=cfg.motor)
        traducoes = parsear_resposta(resposta, [b.id for b in pendentes])
        for b in pendentes:
            t = traducoes.get(b.id, b.texto)  # fallback: mantém original se IA falhou
            cache.put(b.texto, cfg, t)
            resultado[b.id] = t
    return resultado


def montar_prompt_refino(
    pares: list[tuple[int, str, str]], cfg: ConfigTraducao
) -> str:
    """Prompt de refino (ADR-0031): melhora a tradução BRUTA comparando com a origem.

    ``pares`` = lista de ``(id, origem, bruto)``. O LLM não traduz do zero: corrige o
    bruto para ficar fiel à origem, sem perder informação, respeitando o glossário.
    """
    glossario = ", ".join(cfg.glossario) if cfg.glossario else "(nenhum)"
    corpo = "\n\n".join(
        f"[[{i}]]\nORIGEM: {origem}\nBRUTO: {bruto}" for i, origem, bruto in pares
    )
    return (
        f"Você revisa a tradução de {cfg.idioma_origem} para {cfg.idioma_destino} de um "
        f"livro técnico sobre: {cfg.assunto or 'tecnologia'}.\n"
        f"Para cada bloco há a ORIGEM e uma tradução BRUTA (automática). Corrija o BRUTO "
        f"para ficar FIEL à origem e natural, SEM PERDER informação, mantendo o tom "
        f"técnico. NÃO traduza termos técnicos, nomes de APIs, comandos ou código; "
        f"mantenha em inglês os termos do glossário: {glossario}.\n"
        f"Responda cada bloco no MESMO formato numerado, só a versão final, sem "
        f"comentários:\n[[N]] <tradução final>\n\n{corpo}"
    )


def refinar_blocos(
    blocos: list[BlocoTraducao],
    brutos: dict[int, str],
    cfg: ConfigTraducao,
    cache: CacheTraducao,
    invocar_fn=_invocar_padrao,
) -> tuple[dict[int, str], bool]:
    """Refina os blocos em lotes (ADR-0031). Devolve ``(traduções, esgotou)``.

    - Bloco já no cache ⇒ usa o refinado salvo (resume barato).
    - Lote refinado com sucesso ⇒ cacheia (persiste o progresso).
    - Falha do LLM (timeout/tokens) ⇒ ``esgotou=True``, para de chamar o LLM; os
      pendentes caem para o BRUTO (tradução completa, sem perda) e **não** são
      cacheados, para serem refinados num próximo run.
    """
    resultado: dict[int, str] = {}
    pendentes: list[BlocoTraducao] = []
    for b in blocos:
        cached = cache.get(b.texto, cfg)
        if cached is not None:
            resultado[b.id] = cached
        else:
            pendentes.append(b)

    esgotou = False
    i = 0
    while i < len(pendentes):
        lote = pendentes[i : i + max(1, cfg.lote_refino)]
        pares = [(b.id, b.texto, brutos.get(b.id, b.texto)) for b in lote]
        prompt = montar_prompt_refino(pares, cfg)
        try:
            resposta = invocar_fn(
                prompt,
                modelo=cfg.modelo or _MODELO_PADRAO,
                timeout=cfg.timeout,
                motor=cfg.motor,
            )
        except Exception:  # noqa: BLE001 — tokens/timeout: pausa e mantém resumível
            esgotou = True
            break
        refinados = parsear_resposta(resposta, [b.id for b in lote])
        for b in lote:
            t = refinados.get(b.id)
            if t:
                cache.put(b.texto, cfg, t)  # progresso persistido
                resultado[b.id] = t
            else:
                resultado[b.id] = brutos.get(b.id, b.texto)  # sem cache ⇒ retry depois
        i += len(lote)

    for b in pendentes[i:]:  # pendentes após esgotar ⇒ bruto (sem perda), sem cache
        resultado[b.id] = brutos.get(b.id, b.texto)
    return resultado, esgotou
