---
titulo: ADR-0008 — Roteamento e extração de parâmetros
id: ADR-0008
status: aceito
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-16
substitui: —
substituido-por: —
---

# ADR-0008 — Roteamento e extração de parâmetros

## Histórico de revisão
| Versão | Data       | Autor     | Mudança          | Aprovado por |
|--------|------------|-----------|------------------|--------------|
| 1.0    | 2026-06-16 | Tech Lead | Aceito (endurecimento C8) | PO/PM |

---

## Status
`aceito`.

## Contexto
O roteador não definia o que fazer quando `triggers` de rotinas diferentes casam.
E havia a promessa de extrair parâmetros de linguagem natural ("perna hoje,
agachamento 80kg 4x10") **sem IA**, o que é frágil — em tensão com o ideal de 0 IA
na entrada.

## Decisão
- **Conflito de triggers:** vence o match mais **específico** (palavra/alias mais
  longo); empate → o roteador pergunta; ambiguidade é logada. Rotinas podem
  declarar prioridade opcional.
- **Extração:** caminho feliz é uma **micro-sintaxe** parseável por regex
  (ex.: `treino: agachamento 80kg 4x10`) — 0 IA. Texto livre que não casa cai no
  **fallback Haiku (Camada 1)**.

## Alternativas consideradas
| Alternativa | Prós | Contras | Por que não |
|---|---|---|---|
| Regex puro para todo NL | 0 IA sempre | Quebra com linguagem real | Frágil; frustra o usuário |
| IA para toda entrada | Robusto | Caro, lento | Fere P1 |
| Primeira rotina que casar | Simples | Não-determinístico em conflito | Comportamento imprevisível |

## Consequências
- **Positivas:** 0 IA no caso comum, com degradação graciosa; conflito resolvido
  deterministicamente.
- **Negativas:** rotinas precisam declarar micro-sintaxe/triggers com cuidado.
- **Impacto na constituição:** comportamento do roteador (§ arquitetura geral).

## Pendências
Definir a gramática exata da micro-sintaxe comum a domínios de tracking.
