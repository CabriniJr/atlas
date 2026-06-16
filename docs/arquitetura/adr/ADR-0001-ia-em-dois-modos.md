---
titulo: ADR-0001 — IA em dois modos: análise (2a) vs agente (2b)
id: ADR-0001
status: aceito
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-16
substitui: —
substituido-por: —
---

# ADR-0001 — IA em dois modos: análise (2a) vs agente (2b)

## Histórico de revisão
| Versão | Data       | Autor     | Mudança          | Aprovado por |
|--------|------------|-----------|------------------|--------------|
| 1.0    | 2026-06-16 | Tech Lead | Aceito (endurecimento A1) | PO/PM |

---

## Status
`aceito`.

## Contexto
A constituição original tratava "IA" como sinônimo de "Claude Code" (`claude -p`,
agente com tools e acesso a filesystem) para **toda** chamada. Mas as fases de
análise (resumo diário, interpretar diff, revisão de leitura) são *um prompt → uma
resposta*: não precisam de loop agêntico, tools, nem filesystem. Rodar o agente
pesado para isso custa cold-start e abre superfície desnecessária. Havia ainda uma
tensão de princípio: "economia de token acima de tudo" vs. "uso sai da assinatura,
sem billing por token" — se o token sai da assinatura, o recurso escasso é o
**limite de uso da assinatura**, não o token.

## Decisão
Separar explicitamente dois modos de invocação de IA, ambos na assinatura:

- **Análise (Camada 2a):** `claude -p --output-format json --max-turns 1`, **sem
  tools e sem acesso a arquivos**, modelo da config da rotina. Usada por toda fase
  `analyze`.
- **Agente (Camada 2b):** Claude Code completo, com tools e escrita de arquivo.
  **Único consumidor: o meta-loop.**

Reorientar o princípio P1: o recurso escasso é o **limite de uso da assinatura**;
"economia de token" é o proxy. A Camada 2 passa a ter sub-níveis 2a/2b.

## Alternativas consideradas
| Alternativa | Prós | Contras | Por que não |
|---|---|---|---|
| Usar Claude Messages API para análise | Mais leve, controle fino | Reintroduz billing por token de API | Viola decisão travada (assinatura) |
| Manter tudo em Claude Code agêntico | Um caminho só | Overhead e superfície agêntica desnecessários | Caro e arriscado para análise |

## Consequências
- **Positivas:** análise mais barata e segura (tool-less); meta-loop isolado como
  único ponto agêntico.
- **Negativas:** o motor precisa de dois caminhos de invocação distintos.
- **Impacto na constituição:** decisão #2 e #7 reescritas; princípio P1 reorientado.

## Pendências
Confirmar empiricamente flags e formato do `claude -p` na máquina alvo (ver
[ADR-0010](ADR-0010-observabilidade-claude-p.md)).
