"""Estimativa de custo/tamanho de uma tradução (ADR-0030, pendência §Estimativa).

Antes de rodar (que pode custar caro em IA — ADR-0005, orçamento reativo), o web
shell mostra uma prévia: quantas páginas, quantos blocos tradutíveis, quantos
caracteres e uma estimativa de tokens/custo. Função **pura** sobre o PDF de origem
(reusa a extração do estágio 1); não chama IA, então estimar é **grátis** (P1).
"""

from __future__ import annotations

from dataclasses import dataclass

from atlas.traducao.extracao import extrair_pagina

# Custo aproximado por 1M de tokens (entrada+saída combinados, ordem de grandeza).
# Só para dar noção de gasto ao usuário; não é cobrança. Ollama é local ⇒ 0.
_USD_POR_MTOK = {
    "claude": 6.0,
    "ollama": 0.0,
}
_CHARS_POR_TOKEN = 4  # heurística usual (~4 chars/token)


@dataclass
class Estimativa:
    paginas: int
    blocos_traduziveis: int
    caracteres: int
    tokens_estimados: int
    custo_usd_estimado: float
    motor: str

    def to_dict(self) -> dict:
        return {
            "paginas": self.paginas,
            "blocos_traduziveis": self.blocos_traduziveis,
            "caracteres": self.caracteres,
            "tokens_estimados": self.tokens_estimados,
            "custo_usd_estimado": round(self.custo_usd_estimado, 4),
            "motor": self.motor,
        }


def estimar(origem: str, motor: str = "claude") -> Estimativa:
    """Abre o PDF, conta páginas/blocos/caracteres tradutíveis e estima tokens/custo.

    Blocos ``skip`` (código/monospace, sem letras) não entram — não são traduzidos.
    A saída (PT-BR) tende a ser ~30% mais longa que a entrada (EN); o fator de saída
    é embutido no custo (entrada + ~1.3× saída ≈ 2.3× os caracteres de origem).
    """
    import fitz  # import tardio: dep pesada só quando estimar de fato roda

    doc = fitz.open(origem)
    try:
        paginas = doc.page_count
        blocos = 0
        caracteres = 0
        for i in range(paginas):
            for b in extrair_pagina(doc[i], i):
                if b.skip:
                    continue
                blocos += 1
                caracteres += len(b.texto)
    finally:
        doc.close()

    # entrada (prompt ~ origem) + saída (~1.3× origem) ⇒ ~2.3× caracteres.
    tokens = int(caracteres * 2.3 / _CHARS_POR_TOKEN)
    custo = tokens / 1_000_000 * _USD_POR_MTOK.get(motor, _USD_POR_MTOK["claude"])
    return Estimativa(
        paginas=paginas,
        blocos_traduziveis=blocos,
        caracteres=caracteres,
        tokens_estimados=tokens,
        custo_usd_estimado=custo,
        motor=motor,
    )
