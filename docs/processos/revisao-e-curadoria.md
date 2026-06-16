---
titulo: Revisão e curadoria (best-of-two)
id: PROC-CURADORIA
status: aprovado
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-16
---

# Revisão e curadoria (best-of-two)

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-06-16 | Tech Lead | Criação | PO/PM        |

---

> Como o Tech Lead/Curador transforma N soluções paralelas em uma final melhor.

## Entrada
- Duas (ou mais) implementações da **mesma** tarefa, cada uma com seu resumo de
  abordagem.
- A spec da tarefa e o [DoD](definicao-de-pronto.md).

## Régua de avaliação
Aplicar, nesta ordem (ver também [revisor-curador](../agentes/revisor-curador.md)):
1. **Correção** — testes passam, contrato satisfeito.
2. **Aderência à doc** — constituição, ADRs, princípios.
3. **Simplicidade (P7)** — menos partes móveis vence.
4. **Clareza e limites** — unidades pequenas, testáveis, responsabilidades nítidas.
5. **Economia (P1/P2)** — script-primeiro; IA só quando justifica.
6. **Segurança** — limites do meta-loop e de segredos respeitados.

## Procedimento
1. **Comparar** as soluções contra a régua, ponto a ponto.
2. **Escolher a melhor base** — a que ganha na maioria dos critérios.
3. **Enxertar** o que a(s) outra(s) fez(eram) melhor (um trecho mais simples, um
   teste melhor, um nome mais claro).
4. **Melhorar** — o curador pode refinar além do que qualquer Dev entregou.
5. **Revalidar o DoD** na solução fundida.
6. **Registrar a curadoria:** o que veio de cada solução e por quê (rastreável).
7. **Levar ao PO/PM** para aceite de alto nível.

## Anti-padrões a evitar
- "Empatou, escolhe qualquer uma." → Funda o melhor das duas; não jogue trabalho
  fora.
- "Está perto do DoD." → Perto não é pronto. Conserte ou rejeite.
- "A solução é elegante mas foge da doc." → A doc é a régua (P8). Ou alinha, ou
  abre ADR.

## Saída
A solução curada + o registro da curadoria, prontos para commit após aceite.
