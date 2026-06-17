---
titulo: ADR-0016 — Chamadas de IA plugáveis via Kind Prompt
id: ADR-0016
status: aceito
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-17
substitui: —
substituido-por: —
---

# ADR-0016 — Chamadas de IA plugáveis via Kind Prompt

## Histórico de revisão
| Versão | Data       | Autor     | Mudança  | Aprovado por |
|--------|------------|-----------|----------|--------------|
| 1.0    | 2026-06-17 | Tech Lead | Proposta + aceite | PO/PM |

---

## Status
`aceito`.

## Contexto

As primeiras rotinas que usavam IA embutiam a chamada no próprio código (ex.:
`repo-sync` chamava Haiku dentro de uma função `_explicar`). Isso viola dois
princípios da [constituição](../constituicao.md):

1. **Agnóstico e plugável** — o motor não conhece domínios; tudo é rotina.
2. **Script-primeiro, agente só quando precisa** — a IA é um recurso escasso da
   assinatura (princípio econômico, [ADR-0005](ADR-0005-orcamento-reativo.md)).

Hard-codar a IA por rotina significa que **criar uma nova análise por IA exige
código**, contraria o modelo "tudo é objeto" do [ADR-0015](ADR-0015-core-api-de-objetos.md),
e espalha prompts/modelos pelo repositório sem um ponto único de configuração.

O PO pediu explicitamente: *"chamadas de IA conectáveis, qualquer rotina pode
fazer isso se configurado, não hard-code com rotinas que fazem; crie um kind
para isso."*

## Decisão

Toda chamada de IA agendada passa a ser **configuração, não código**, através de
um novo Kind e de um collect genérico.

1. **Kind `Prompt`** — representa uma chamada de IA reutilizável:
   - `spec.template` — texto do prompt, com placeholders `{dados}` e `{agora}`.
   - `spec.model` — modelo (default `claude-haiku-4-5-20251001`).
   - `spec.timeout` — segundos (default 90).
   - `spec.fonte` — como montar `{dados}`: `grupo:<g>`, `kind:<K>`, `repo:<r>`,
     `texto:<t>`, ou vazio.
   - `status.last_run` / `status.last_ok` / `status.last_output` — observados pelo motor.

2. **Collect genérico `prompt`** (`src/atlas/rotinas/prompt.py`, registrado em
   `@registrar("prompt")`) — qualquer rotina chama IA apontando para um Prompt:
   ```toml
   nome    = "resumo-ia"
   label   = "resumo-ia"      # = nome do Prompt/<label>
   coletar = "prompt"
   agenda  = "@daily 21:00"
   modelo  = "none"           # a IA roda DENTRO do collect, não pelo executor
   ```
   O collect lê `Prompt/<label>`, monta `{dados}` a partir de `spec.fonte`,
   invoca `atlas.ia.invocar` e persiste a resposta em `status.last_output`.

3. **A IA é best-effort** — falha do binário/timeout nunca derruba o loop; a
   saída sinaliza indisponibilidade ([ADR-0006](ADR-0006-erro-e-resiliencia.md)).

4. **Resolução do binário `claude`** — `atlas.ia` resolve o cliente na ordem
   `ATLAS_CLAUDE_BIN` → PATH → binário embutido da extensão Claude Code →
   fallback, para funcionar tanto no host quanto empacotado.

Consumidores específicos (ex.: `repo-sync`) podem manter sua análise própria,
mas o **mecanismo plugável é o caminho padrão** para novas análises por IA.

## Alternativas consideradas
| Alternativa | Prós | Contras | Por que não |
|---|---|---|---|
| Hard-code por rotina | simples no início | exige código por análise; espalha prompts; não-plugável | viola constituição |
| Campo `ai` na própria Routine | sem novo Kind | mistura agendamento com prompt; menos reutilizável | Prompt é objeto de 1ª classe e reusável por várias rotinas |
| Plugin externo de IA | flexível | overhead; foge do modelo "tudo é Resource" | desnecessário para o MVP |

## Consequências
- **Positivas:** nova análise por IA = um `Prompt` + uma `Routine`, sem código;
  ponto único de configuração de prompt/modelo; histórico em `status.last_output`;
  alinhado a "tudo é objeto" e ao princípio econômico (só roda quando agendado/disparado).
- **Negativas / custos:** mais um Kind no catálogo; `spec.fonte` é uma mini-linguagem
  que precisa evoluir com cuidado.
- **Impacto na constituição:** nenhum princípio muda; reforça "agnóstico e plugável".

## Pendências
- `spec.fonte` pode ganhar novas fontes (ex.: `runs:<n>`, `tracker:<nome>` com janela).
- Avaliar migrar a análise hard-coded de `repo-sync` para um `Prompt` padrão.
- Endpoint web `/_insight` (insight sob demanda) hoje monta prompts no servidor;
  pode passar a referenciar `Prompt` resources.
