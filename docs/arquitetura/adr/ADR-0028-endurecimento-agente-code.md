---
titulo: ADR-0028 — Endurecimento do Agente modo `code` (workspace restrito, allow/deny de tools, concorrência, gate)
id: ADR-0028
status: proposto
versao: 0.1
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-26
substitui: —
substituido-por: —
---

# ADR-0028 — Endurecimento do Agente modo `code`

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 0.1    | 2026-06-26 | Tech Lead | Proposta — consolida as §Pendências de segurança do [ADR-0025](ADR-0025-agente-modo-code.md) (Tema 1 do hardening) | — |
| 0.2    | 2026-06-26 | Tech Lead | Implementado: workspace/tools/concorrência/gate/persistência + UI de curadoria (SPEC-CURADORIA-GATE) | — |

---

## Status
`proposto` — aguarda aceite do PO/PM. Consolida e fecha as **§Pendências de
segurança** do [ADR-0025](ADR-0025-agente-modo-code.md) (modo `code`).

## Contexto

O [ADR-0025](ADR-0025-agente-modo-code.md) abriu o **modo `code`** do Kind
`Agente`: Claude Code agêntico (Camada 2b do [ADR-0001](ADR-0001-ia-em-dois-modos.md))
rodando via `claude -p … --dangerously-skip-permissions --add-dir <raiz>`, com o
`cwd` na **raiz do repositório**. Isso foi entregue em ritmo go-horse e o próprio
ADR-0025 registrou, em §Pendências, a dívida de segurança:

- **Workspace restrito** — hoje o agente escreve **livre sob a raiz** do projeto.
- **Allow/deny de tools** por Agente (ex.: `code` sem `Bash`).
- **Limite de concorrência** simultânea de runs.
- **Persistência de runs** (sobrevivem a restart) — em memória hoje.
- **Gate de curadoria** — alinhar a [ADR-0003](ADR-0003-seguranca-meta-loop.md) /
  [ADR-0013](ADR-0013-barreira-de-entrada.md): código de modelo **nunca**
  auto-vira produção sem revisão humana ([CLAUDE.md](../../../CLAUDE.md) §6).

Com o multiusuário ([ADR-0027](ADR-0027-multiusuario-credenciais.md)) já em `main`,
a superfície agêntica passou a ser **multiusuário**: um run roda como o host, mas é
disparado por um usuário escopado. Endurecer o modo `code` é o **Tema 1** priorizado
em [`proximos-passos.md`](../../roadmap/proximos-passos.md). Mexer no contrato do
modo `code` é decisão de arquitetura → este ADR (regra de ouro do CLAUDE.md).

## Decisão

O modo `code` ganha **quatro controles schema-driven** (campos novos em
`Agente.spec`, [ADR-0017](ADR-0017-gui-por-kind-abstrai-api.md)) + **um limite global**.
Tudo é **opt-in aditivo**: Agentes `code` existentes seguem funcionando (defaults
preservam o comportamento atual), mas a documentação e os templates passam a
recomendar a configuração endurecida.

### 1. Workspace restrito (`spec.workspace`)
- Campo `workspace`: subdiretório **relativo** sob `ATLAS_PROJECT_DIR`. O run usa
  `cwd = <PROJECT_DIR>/<workspace>` e `--add-dir <cwd>` — o agente só enxerga/escreve
  ali.
- **Confinamento verificado** por função pura `resolve_workspace(project_dir, sub)`:
  resolve o caminho (`Path.resolve()`) e **recusa** se escapar de `PROJECT_DIR`
  (traversal `..`, caminho absoluto, symlink que sai da raiz) → run termina com
  evento `error` e **não** inicia o subprocess. Caminho inexistente também é erro.
- **Default** (`workspace` vazio) = raiz do projeto, como hoje (compat). A raiz é
  marcada como **escopo amplo** no evento `init` (`workspace: "<raiz>"`) para o
  front sinalizar o risco.

### 2. Allow/deny de tools (`spec.allowed_tools` / `spec.denied_tools`)
- Dois campos **csv** (ex.: `Read,Edit,Write` / `Bash`). Função pura
  `build_tool_args(allowed, denied)` monta `--allowedTools <csv>` e/ou
  `--disallowedTools <csv>` para o `claude` CLI. Vazios = sem flags (comportamento
  atual). `denied` tem precedência semântica (o CLI já trata).
- Permite o perfil **"editor sem shell"** (`allowed=Read,Edit,Write`,
  `denied=Bash`) — reduz a superfície de execução arbitrária.

### 3. Limite de concorrência (`_RUNS_CONCURRENT_MAX`)
- Teto global de runs **não-terminados** simultâneos (default **3**, env
  `ATLAS_AGENT_MAX_CONCURRENT`). `POST /_agent_run` acima do teto responde **429**
  com `{error, retry}` e **não** cria run. Protege CPU/IO da Rasp e a assinatura
  (P1 — recurso escasso).

### 4. Gate de curadoria (`spec.gate`)
- Campo booleano `gate` (default **true** para `code`). Semântica desta fase
  (mínima e verdadeira): o run é **carimbado** `gated: true` no `init` e no estado;
  o sistema **nunca** comita, ativa nem faz deploy do que o agente produz — a
  promoção é **a revisão humana do diff no working tree** + commit/PR
  (CLAUDE.md §6, ADR-0003/0013). O CD da Rasp só aplica `main`, então nada gerado
  num run chega a produção sem o gate humano de merge.
- A **UI de aprovação/rejeição** explícita (revisar diff, promover/descartar dentro
  do app) é evolução — fica em §Pendências, não bloqueia esta fatia.

### 5. Persistência de runs
- Os runs deixam de viver só em memória: ao terminar, o run é **persistido** (id,
  agente, dono, task, custo, eventos resumidos, timestamps) para sobreviver a
  restart e alimentar observabilidade/retenção. Implementação concreta (Kind oculto
  `AgentRun` no store vs. arquivo) decidida na fatia, preferindo o **store**
  (P4 — o repositório é o estado) se o custo for baixo.

### Escopo por dono (multiusuário)
- O run carimba `owner` (dono da sessão, `self._owner()`). Persistência e futura UI
  de runs respeitam o isolamento do [ADR-0027](ADR-0027-multiusuario-credenciais.md)
  (member vê só os seus; admin vê todos).

## Alternativas consideradas

| Alternativa | Prós | Contras | Por que não |
|---|---|---|---|
| **Controles schema-driven em `Agente.spec` (escolhida)** | opt-in aditivo; forms aparecem sozinhos (ADR-0017); por-Agente | mais campos no Kind | **escolhida** |
| Sandbox de SO (container/namespace/seccomp) por run | isolamento forte de verdade | pesado na Rasp; reescreve o runner; fora do go-horse | adiada (pode virar ADR futuro) |
| Gate interativo bloqueante (aprovar cada tool-call) | controle fino | não há TTY no servidor; `--dangerously-skip-permissions` é necessário; UX ruim | rejeitada |
| Manter status quo (ADR-0025 sem endurecer) | nada a fazer | escrita livre na raiz; sem teto; dívida aberta | rejeitada (este ADR) |

## Consequências
- **Positivas:** reduz drasticamente a superfície do 2b interno — escrita confinada,
  tools restringíveis, teto de concorrência, runs persistentes e escopados por dono.
  Fecha as §Pendências do ADR-0025. Mantém compatibilidade (defaults preservam o
  comportamento) e segue schema-driven (ADR-0017).
- **Negativas / custos:** mais campos no Kind `Agente`; o confinamento exige cuidado
  com path traversal/symlink (testado por função pura). O gate desta fase é uma
  **política** (revisão de diff), não um cofre técnico — a contenção forte de SO fica
  para depois.
- **Impacto na constituição / ADRs:** **fecha** as §Pendências do
  [ADR-0025](ADR-0025-agente-modo-code.md) e o reforça com os controles de segurança
  que o [ADR-0003](ADR-0003-seguranca-meta-loop.md) exigia do 2b. Não altera a
  constituição; estende o schema do Kind `Agente` (ADR-0024).

## Pendências
- ~~**UI de curadoria** do gate~~ — **entregue** (SPEC-CURADORIA-GATE: aba 🔍 Curadoria
  no Agente; `curadoria.py`; endpoints `diff`/`discard`/`approve`).
- **Isolamento por git worktree** do run (hoje a working tree é compartilhada; `approve`
  troca de branch no repo vivo → dev-time).
- **Sandbox de SO** real por run (container/namespace) — endurecimento forte futuro.
- **Retenção/limpeza** dos runs persistidos (alinhar com E1-08 observabilidade e o
  item 6.3 de [`proximos-passos.md`](../../roadmap/proximos-passos.md)).
