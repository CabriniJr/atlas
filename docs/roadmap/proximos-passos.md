---
titulo: Próximos passos — pendências priorizáveis
id: ROAD-PROXIMOS
status: aprovado
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-26
---

# Próximos passos — pendências priorizáveis

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-06-26 | Tech Lead | Criação — consolidação pós-épico multiusuário (ADR-0027) p/ o PO priorizar | — |
| 1.1    | 2026-06-26 | Tech Lead | **Ordem aprovada pelo PO.** Próxima rodada = **Tema 1 (Endurecimento)**; dossiê de contexto preparado | PO/PM |
| 1.2    | 2026-06-26 | Tech Lead | Item 1.1 parcialmente entregue (ADR-0028): workspace restrito + tools + concorrência + gate | — |

---

> **Para o PO/PM.** Estado atual: o épico **multiusuário (ADR-0027)** está concluído e
> em `main` (Fases 1–5 + UI). Este documento agrega o que sobra **pronto para entrar na
> fila**, agrupado por tema, com *por quê* e *tamanho* aproximado (P=pequeno, M=médio,
> G=grande). Fonte detalhada: [backlog](backlog.md) e [ADRs](../arquitetura/adr/README.md).

> ✅ **Ordem priorizada (aprovada pelo PO em 2026-06-26):** a ordem dos temas abaixo
> (0 → 1 → 2 → **3 (UX, inserido pelo PO "no meio")** → 4 → 5 → 6) é a fila de
> desenvolvimento. **Próxima rodada: Tema 1 — Endurecimento de segurança**, com dossiê
> de contexto pronto em
> [`2026-06-26-hardening-dossie-contexto.md`](../superpowers/plans/2026-06-26-hardening-dossie-contexto.md).
> (O Tema 0 é operacional — config na Rasp, sem código — e pode rodar em paralelo.)

## 0. Operacional imediato (fechar o multiusuário em produção)
Não é desenvolvimento — é colocar o que já existe pra rodar de verdade na Rasp.

| # | Item | Por quê | Tam. |
|---|---|---|---|
| 0.1 | **Validar na Rasp** (`http://atlas:8080`): a migração de boot carimbou `owner=admin`; testar login com token e criar um usuário admin de senha via `POST /_auth/users` | Sem um usuário criado, só o token entra; confirmar que não há lockout | P |
| 0.2 | **Criar o GitHub OAuth App** e setar `ATLAS_GITHUB_CLIENT_ID` no `.env` da Rasp | Habilita "Conectar com GitHub" (device flow); sem ele só PAT funciona | P |
| 0.3 | **Backup da chave mestra do cofre** (`secrets/secret.key` ou `ATLAS_SECRET_KEY`) | Perder a chave = perder todos os segredos cifrados | P |

## 1. Endurecimento de segurança (dívida do que entrou)
| # | Item (ref backlog) | Por quê | Tam. |
|---|---|---|---|
| 1.1 | **E7-28 — endurecer o modo `code`**: ✅ workspace restrito + allow/deny de tools + teto de concorrência + flag de gate (ADR-0028, em `feat/hardening-agente-code`); falta persistência de runs + UI de curadoria | Hoje o agente escreve livre sob a raiz do projeto — maior superfície de risco interna | G |
| 1.2 | **Persistência de sessões** (hoje em memória; perdem no restart) | UX: usuário não precisa relogar a cada deploy/restart | P |
| 1.3 | **Persistência dos runs agênticos** (hoje em memória) | Não perder histórico/estado de runs no restart | M |
| 1.4 | **Rotação da chave mestra + UX de cadastro/convite de usuários** | Operação seborosa a longo prazo; hoje só admin cria por API | M |

## 2. Loop de desenvolvimento autônomo (a visão-mãe)
> O "loop fechado" dia/noite/manhã ([[autonomous-dev-loop]]). É o maior diferencial e
> depende de peças já existentes (Agente modo `code`, pool de ideias).

| # | Item (ref backlog) | Por quê | Tam. |
|---|---|---|---|
| 2.1 | **E6-04 — pool → geração**: item `rotina` dispara o meta-loop (agente 2b gera inativo) | Conecta captura de ideias à autoimplementação (ativação humana) | M |
| 2.2 | **E2-02/03/04 — meta-loop**: planejamento → `SPEC.md` → geração via agente → `/ativar` + revisão/commit | Núcleo do dev noturno autônomo | G |
| 2.3 | **Agente revisor/curador** que funde e valida soluções paralelas | Fecha o loop com curadoria automática antes do gate humano | G |

## 3. UX / feedback visual (dinâmico) — *pedido do PO*
> O front precisa **dar sinal de vida**: mostrar quando algo está acontecendo e
> atualizar a tela sozinho, sem parecer travado/estático. Pedido direto do PO.

| # | Item | Por quê | Tam. |
|---|---|---|---|
| 3.1 | **E8-01 — animação de "pensando" no chat do Agente** enquanto a IA processa (modo `code`/chat) | Hoje a espera parece travada; o usuário não sabe se está rodando | P |
| 3.2 | **E8-02 — spinners/indicadores de progresso** em ações demoradas (sync de repo, insight IA, snapshot, agent run, login GitHub) | Feedback de "está acontecendo algo" — círculo de loading nos botões/cards | P-M |
| 3.3 | **E8-03 — atualização dinâmica da tela** (não-estática): listas/status/runs refletem mudanças sozinhos via **SSE/polling** (o `/_agent_run/stream` já é SSE — estender o padrão ao dashboard, status e árvore) | A tela não deve exigir refresh manual; estado vivo | M |
| 3.4 | **E8-04 — toasts/estado de erro melhores** e desabilitar botões em ação (evitar duplo-clique, mostrar "…") | Robustez percebida + clareza do que está em curso | P |

## 4. Repo (carro-chefe E7) — acabamentos
| # | Item (ref backlog) | Por quê | Tam. |
|---|---|---|---|
| 4.1 | **E7-09 — progresso vs. meta**: amarrar Repo a um `Goal` (label) e mostrar avanço | Completa a narrativa de "progresso de projeto" do dash | M |
| 4.2 | **E7-11 — Telegram do Repo**: notificações ricas, prompts stateful opt-in, digest periódico | Leva o repo-sync ao canal onde o dono já está | M |

## 5. Observabilidade e orçamento de IA
| # | Item (ref backlog) | Por quê | Tam. |
|---|---|---|---|
| 5.1 | **E1-08 — observabilidade**: gravar `usage` em `runs` + comando `/uso` | Visibilidade de gasto (base já existe no tracking por Agente, E7-44) | M |
| 5.2 | **E1-09 — orçamento**: teto global pré-despacho + disjuntor por rotina | Proteger a assinatura (P1 — recurso escasso) | M |

## 6. Maturidade de plataforma / infra
| # | Item (ref backlog) | Por quê | Tam. |
|---|---|---|---|
| 6.1 | **E0-06 — CLI SSH** consumindo a API com auth | Dev noturno/remoto agora que a auth multiusuário existe | M |
| 6.2 | **E4-06 — release automation** (release-please) + versão inicial; **E4-04** units `atlas-dev`/`atlas-prod` (tag) | Prod por tag (constituição) em vez de só `main` | M |
| 6.3 | **Retenção/limpeza de `runs`** (decisão em aberto no backlog) | Evitar crescimento ilimitado do store | P |
| 6.4 | **E1-07 — harness de teste de rotina** | Testar rotinas geradas antes de ativar (suporte ao loop autônomo) | M |

## Como usar
1. Marque os itens que entram na **próxima rodada** (e a ordem).
2. O Tech Lead abre o **dossiê de contexto** do tema escolhido e decompõe em specs.
3. Cada item segue o fluxo: ADR (se mudar arquitetura) → branch → TDD → PR/merge → CD.
