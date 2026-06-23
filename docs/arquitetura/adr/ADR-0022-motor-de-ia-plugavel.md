---
titulo: ADR-0022 — Motor de IA selecionável e plugável (incl. local)
id: ADR-0022
status: aceito
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-23
substitui: —
substituido-por: —
---

# ADR-0022 — Motor de IA selecionável e plugável (incl. local)

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 0.1    | 2026-06-23 | Tech Lead | Proposta (brainstorm Repo, carro-chefe) | — |

---

## Status
`aceito` — aceito pelo PO/PM (2026-06-23); em implementação ágil.

## Contexto

A invocação de IA hoje é via `claude -p` em `atlas.ia.invocar`
([ADR-0001](ADR-0001-ia-em-dois-modos.md), [ADR-0010](ADR-0010-observabilidade-claude-p.md)).
O [ADR-0016](ADR-0016-ia-plugavel-kind-prompt.md) tornou o **prompt** plugável (Kind
`Prompt`), mas o **motor** (provider/modelo) ainda é fixo. O PO quer o motor
**selecionável e plugável**, incluindo **modelos locais** (Ollama/Gemma) para reduzir
o consumo da assinatura — coerente com o princípio da *economia do recurso escasso* e
com a direção futura de *agnosticismo de provider* ([backlog](../../roadmap/backlog.md)).

O gatilho imediato é o [ADR-0024](ADR-0024-kind-agente.md) (Kind `Agente`), que
precisa **referenciar um motor**. O suporte a local é **baixa prioridade**, mas a
abstração precisa existir agora para o Agente e o Repo a consumirem.

## Decisão

1. **Abstração de motor (engine adapter).** `atlas.ia` ganha uma interface única —
   `invocar(prompt, modelo, timeout, ...)` — com **adapters** plugáveis:
   - `claude` (via `claude -p`) — **default**, comportamento atual.
   - `ollama` (local, ex.: Gemma) — **baixa prioridade**, ponto de extensão.
2. **Seleção por configuração.** O motor/modelo é escolhido por **`Agente`**
   (ADR-0024) e/ou por recurso (ex.: `Repo.spec.model`, já existente). O roteamento
   vive em `atlas.ia`, não nas rotinas.
3. **Degradação** ([ADR-0006](ADR-0006-erro-e-resiliencia.md)): motor indisponível →
   fallback configurável ou mensagem padrão de "IA indisponível"; nunca derruba o job.
4. **Observabilidade** ([ADR-0010](ADR-0010-observabilidade-claude-p.md)): o run
   registra **qual motor/modelo** foi usado, além de tokens/custo quando disponível.
5. **Segurança preservada:** modo análise single-turn, sem tools
   ([ADR-0001](ADR-0001-ia-em-dois-modos.md), [seguranca](../seguranca.md)),
   independentemente do motor.

## Alternativas consideradas

| Alternativa | Prós | Contras | Veredito |
|---|---|---|---|
| **Adapter de motor plugável (claude default + ollama local)** | provider-agnóstico; economia; base p/ Agente; local opcional | manter adapters; capabilities divergem entre motores | **escolhida** |
| Manter `claude -p` hardcoded | custo zero | não atende agnosticismo nem local; acopla o Agente | não atende |
| Abstrair só o modelo dentro do Claude | simples | não cobre motor local | insuficiente |
| Migrar tudo para local agora | custo de assinatura zero | maturidade/qualidade; field-test arm64 pendente | prematuro |

## Consequências

- **Positivas:** motor agnóstico e selecionável; caminho para reduzir consumo da
  assinatura com modelos locais; base limpa para o Kind `Agente`; observabilidade de
  qual motor rodou.
- **Negativas / custos:** manter múltiplos adapters e lidar com diferenças de
  capacidade/qualidade entre eles; testes por adapter; risco de inconsistência de
  resultado entre motores.
- **Impacto na constituição:** estende ADR-0001/0016; reforça "agnóstico e plugável" e
  "economia do recurso escasso". Nenhuma decisão anterior muda.

## Candidato testado (Ollama local)

Em 2026-06-23, validou-se um servidor Ollama na LAN do dono:
- **Endpoint:** `POST http://192.168.86.22:11434/api/chat`
- **Modelo:** `gemma4` (gera respostas em PT-BR, expõe campo `thinking`)
- **Performance:** ~38 tok/s, `load_duration` baixo (modelo residente)
- **Formato:** API padrão `/api/chat` do Ollama, retorna `{message: {content: "..."}, ...}`

É um candidato viável para o adapter `ollama` (baixa prioridade) e para o render chat do Kind `Agente` (E7 spec b).

## Pendências

- Contrato exato do adapter (timeout, streaming, formato de saída, mapeamento de modelo).
- Quais modelos locais suportar e requisitos (liga com o field-test arm64 — E1-05).
- Política de budget/limites por motor ([ADR-0005](ADR-0005-orcamento-reativo.md)).
- Integração do endpoint Ollama como adapter (`ollama` em `atlas.ia`, com fallback se indisponível).
- Estratégia de fallback entre motores (quando e para qual).
