---
titulo: Ciclo de vida da rotina
id: ARQ-CICLO
status: aprovado
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-16
---

# Ciclo de vida da rotina

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-06-16 | Tech Lead | Criação | PO/PM        |

---

Toda rotina é executada como uma sequência de fases. **Cada fase é opcional**: uma
rotina de log simples usa só `trigger` + `store`; uma rotina de análise usa todas.
Esse ciclo é a abstração que torna o motor **agnóstico** (P3): ele não sabe o que
a rotina faz, só orquestra as fases.

## As fases

| Fase | Função | Custo |
|---|---|---|
| **trigger** | O que dispara: palavras-chave, comando e/ou agendamento. | 0 |
| **collect** | Script determinístico que reúne os dados crus. | 0 |
| **gate** | Predicado barato que decide se vale rodar a análise. Falhou → encerra com saída padrão. | 0 |
| **analyze** | Só se o gate passar: monta o prompt e sobe a IA em **modo análise (2a)**. | IA |
| **deliver** | Formata e envia pelo Telegram; persiste o resultado. | 0 |

**Exemplo (rotina de pull):** `collect` faz git pull + diff → `gate` verifica se
houve mudança → `analyze` só roda se houve → `deliver` manda e salva o run.

## Contrato do `collect`

- **Recebe** um contexto: data/hora, config da rotina, dados do **último run**
  (de `routine_state`, [modelo-de-dados](modelo-de-dados.md)), e leitura do banco.
- **Devolve** um resultado **tipado** ([ADR-0004](adr/ADR-0004-contrato-collect.md)):

  ```
  CollectResult = { data: dict, store: list[StoreOp] }
  StoreOp       = { entity: str, fields: dict }
  ```

  `data` alimenta a renderização do prompt; `store` é o mapeamento **explícito** do
  que persistir e em qual entidade — o motor não adivinha.
- **Não usa IA.** Só Python (git, arquivo, requisição, consulta ao banco).
- Texto externo (diff, JSON) que vá ao prompt entra em **blocos delimitados como
  dados**, nunca como instrução (proteção contra injeção, reforçada por a análise
  rodar single-turn sem tools — [seguranca](seguranca.md)).

## Contrato do `prompt` (template plugável)

- É o prompt da fase de análise — a "personalidade" da rotina.
- Recebe, por substituição, os campos de `CollectResult.data`.
- O resultado renderizado é o que vai dentro do `claude -p` (modo 2a).
- Rotinas sem análise (log puro) não têm `prompt`.

## Anatomia da pasta da rotina

```
routines/<nome>/
  routine.<config>     → metadados e configuração (declarativo)
  collect.<script>     → coleta de dados (opcional; 0 IA)
  prompt.<template>    → prompt da fase de análise (opcional)
  SPEC.md              → spec de origem (meta-loop); ver ADR-0009
```

### Campos da configuração
| Campo | Descrição |
|---|---|
| `nome` | Identificador único. |
| `descricao` | O que faz (também usada como contexto no meta-loop). |
| `triggers` | Palavras-chave/aliases que disparam por mensagem. |
| `agenda` | Quando rodar automaticamente. |
| `modelo` | `none` \| `haiku` \| `sonnet` \| `opus` — modelo da fase de análise. |
| `gate` | Condição que habilita a análise. |
| `timeout` | Tempo máximo da instância de IA. |
| `budget_tokens` | Disjuntor reativo ([ADR-0005](adr/ADR-0005-orcamento-reativo.md)). |
| `catch_up` | Recupera ou pula run agendado perdido ([ADR-0006](adr/ADR-0006-erro-e-resiliencia.md)). |
| `store` | O que persistir e em qual entidade. |
| `saida` | Para onde vai o resultado. |
| `ativa` | Liga/desliga sem remover a pasta (nasce `false` no meta-loop). |

## Testabilidade

Cada fase é testável isoladamente — ver [ADR-0007](adr/ADR-0007-contrato-de-teste.md)
e [`../processos/definicao-de-pronto.md`](../processos/definicao-de-pronto.md).
