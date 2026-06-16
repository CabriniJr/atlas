---
titulo: Diretrizes gerais para agentes
id: AGT-DIRETRIZES
status: aprovado
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-16
---

# Diretrizes gerais para agentes

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-06-16 | Tech Lead | Criação | PO/PM        |

---

> Valem para **todo** agente, independente do papel. A ficha específica do agente
> adiciona regras, nunca relaxa estas.

## Antes de agir
1. Leia o [`CLAUDE.md`](../../CLAUDE.md) da raiz.
2. Leia a [visão de produto](../visao/visao-produto.md) e os
   [princípios](../visao/principios.md).
3. Leia a [constituição](../arquitetura/constituicao.md) e os
   [ADRs](../arquitetura/adr/README.md) relevantes.
4. Leia o documento específico da área que vai tocar.

## Durante o trabalho
- **A doc é a fonte de verdade (P8).** Código que diverge está errado ou precisa
  de ADR. Nunca "conserte" uma divergência em silêncio.
- **Siga os padrões existentes.** Leia código/doc vizinho antes de escrever.
- **TDD (P10).** Teste primeiro; ver [Definição de Pronto](../processos/definicao-de-pronto.md).
- **Não invente escopo.** Faça o que a tarefa pede; o resto vira item de
  [backlog](../roadmap/backlog.md).
- **Toda decisão de arquitetura vira ADR** antes de virar código.
- **Atualize a doc junto com o código.** Header + histórico de revisão sempre.
- **Mensagens pequenas, mudanças focadas.** Um arquivo que cresce demais sinaliza
  responsabilidade demais — divida.

## Limites (todo agente)
- **Nunca** ative/auto-execute código do meta-loop sem revisão humana ([ADR-0003](../arquitetura/adr/ADR-0003-seguranca-meta-loop.md)).
- **Nunca** commite segredos.
- **Nunca** contrarie a constituição sem ADR aceito.
- **Nunca** apague documento — marque `obsoleto` e aponte o sucessor.

## Ao entregar
- Diga claramente **o que foi feito, o que foi verificado e o que ficou de fora**.
- Se um teste falhou, reporte com a saída — não esconda.
- Afirme "pronto" só com evidência (comando rodado, saída observada).

## Comunicação com o PO/PM
O PO/PM valida em **alto nível** (visão, dor, prioridade). Não o sobrecarregue com
detalhe de implementação: traga decisões, trade-offs e pedidos de aceite, não
dumps de código.
