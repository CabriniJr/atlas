---
titulo: Spec — Interface de configuração via chat
id: SPEC-INTERFACE-CHAT
status: em-revisao
versao: 0.1
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-16
---

# Spec — Interface de configuração via chat

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 0.1    | 2026-06-16 | Tech Lead | Criação (lição de casa, item 4) | — |

---

> Implementa o épico **E5** (parte de comandos). O bot do Telegram é a
> **interface de configuração total** do motor: listar, inspecionar, ligar/desligar
> e rodar rotinas, e editar config — **tudo por chat, 0 IA** salvo geração de
> rotina (meta-loop, [spec própria](meta-loop-chat.md)).

## Objetivo
Definir o conjunto de comandos da Camada 0 que permite configurar e operar o Atlas
sem tocar em arquivos manualmente. Todos os comandos respondem só ao ID do dono
(monousuário, [seguranca](../arquitetura/seguranca.md)).

## Princípios aplicados
- **0 IA** (P1): todos os comandos abaixo são determinísticos. Só `/gerar`
  (meta-loop) sobe IA (modo 2b).
- **O repositório é o estado** (P4): comandos que mudam config **escrevem na pasta
  da rotina** (`routine.toml`) e/ou no banco, de forma versionável — não há estado
  oculto de runtime.
- **Interface desacoplada** (P6): a lógica vive no handler; o Telegram só entrega
  texto. Um futuro frontend (app) usa os mesmos comandos/contratos.

## Comandos

### Listagem e inspeção (0 IA)
| Comando | Efeito |
|---|---|
| `/rotinas` | Lista rotinas: nome, estado (ativa/inativa), modelo, agenda. |
| `/rotina <nome>` | Detalhe de uma rotina: descrição, triggers, agenda, gate, modelo, último run. |
| `/status` | Resumo do dia (evolui o atual: registros de hoje + próximos disparos). |
| `/uso` | Consumo de IA agregado de `runs` (ver [ADR-0010](../arquitetura/adr/ADR-0010-observabilidade-claude-p.md)). |
| `/ajuda` | Lista **dinâmica** dos comandos disponíveis (gerada do registro de comandos, não hardcoded). |

### Ciclo de vida (0 IA)
| Comando | Efeito |
|---|---|
| `/ativar <nome>` | Seta `ativa=true` no `routine.toml`; recarrega. |
| `/desativar <nome>` | Seta `ativa=false`; a pasta permanece. |
| `/rodar <nome>` | Execução manual via [executor](executor-e-notificacao.md); notifica resultado. |

### Criação (meta-loop — IA modo 2b)
| Comando | Efeito |
|---|---|
| `/nova` | Inicia conversa de planejamento → `SPEC.md` ([meta-loop-chat](meta-loop-chat.md)). |
| `/gerar <nome>` | Gera a rotina via agente 2b; nasce **inativa**. |

### Registro explícito (0 IA)
| Comando | Efeito |
|---|---|
| `/reg <texto>` | Nota livre (ver [barreira-entrada](barreira-entrada.md)). |

## Edição de config interativa
- `/rotina <nome> set <campo> <valor>` edita um campo declarativo da config
  (`agenda`, `modelo`, `gate`, `triggers`, `timeout`, `budget_tokens`, `catch_up`,
  `saida`).
- Campos validados com as **mesmas regras** de [`routines.py`](../../src/atlas/routines.py)
  (ex.: `modelo` ∈ {none, haiku, sonnet, opus}); valor inválido → erro claro, nada
  é gravado.
- A escrita é feita no `routine.toml` da pasta (P4). Após gravar, o motor recarrega
  a rotina e confirma o novo valor.
- Edição multi-passo (ex.: editar `triggers` como lista) usa um mini-fluxo
  conversacional (estado em `routine_state` ou em memória da sessão de comando).

## Registro de comandos (para `/ajuda` dinâmico)
Cada comando é declarado em uma tabela/registro central (nome, descrição curta,
se é destrutivo, se exige confirmação). `/ajuda` é renderizado desse registro, de
modo que **adicionar comando = adicionar entrada** (não editar texto solto). Isso
prepara o terreno para um futuro frontend que liste capacidades via a mesma fonte.

## Confirmações e segurança
- Comandos que mudam estado de forma relevante (`/desativar`, `set` em rotina ativa)
  confirmam com resumo do antes→depois.
- `/gerar` deixa explícito que a rotina nasce **inativa** e precisa de revisão
  ([ADR-0003](../arquitetura/adr/ADR-0003-seguranca-meta-loop.md)).
- Todos exigem que o remetente seja o dono; mensagem de outro ID é ignorada.

## Casos de erro
| Caso | Resposta |
|---|---|
| `/rotina <nome>` inexistente | "Rotina `<nome>` não encontrada. Veja `/rotinas`." |
| `set` com campo inválido | lista os campos válidos; nada gravado |
| `set` com valor inválido | regra violada + exemplo válido; nada gravado |
| `/rodar` em rotina inativa | pergunta se quer rodar mesmo assim (não ativa) |

## Testes (TDD)
- `/rotinas` com 2 rotinas (1 inativa) → lista com estados corretos.
- `/ativar treino` → `routine.toml` passa a `ativa=true`; recarrega; confirma.
- `/rotina treino set modelo banana` → erro; arquivo inalterado.
- `/rotina treino set modelo sonnet` → arquivo atualizado; confirma.
- `/ajuda` → inclui um comando recém-registrado sem edição de texto manual.
- Mensagem de ID estranho → ignorada.

## Pendências
- Formato exato de `/rotina <nome> set triggers ...` (lista) — definir na execução.
- Onde guardar estado de fluxos conversacionais multi-passo (memória vs
  `routine_state`).
- `/uso` depende de E1-08 (gravação de `usage` em `runs`).
