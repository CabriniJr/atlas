---
titulo: Índice de ADRs
id: ADR-INDEX
status: aprovado
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-23
---

# Architecture Decision Records (ADRs)

## Histórico de revisão
| Versão | Data       | Autor     | Mudança                              | Aprovado por |
|--------|------------|-----------|--------------------------------------|--------------|
| 1.0    | 2026-06-16 | Tech Lead | Criação + 10 ADRs de endurecimento   | PO/PM        |
| 1.1    | 2026-06-16 | Tech Lead | ADR-0013 (barreira) e ADR-0014 (pool) — aceitos | PO/PM |
| 1.2    | 2026-06-16 | Tech Lead | ADR-0015 (core API de objetos, K8s-like) — prioridade máxima | PO/PM |
| 1.3    | 2026-06-17 | Tech Lead | ADR-0016 (IA plugável via Kind Prompt) — aceito | PO/PM |
| 1.4    | 2026-06-17 | Tech Lead | ADR-0017 (GUI por Kind abstrai a API) — aceito | PO/PM |
| 1.5    | 2026-06-17 | Tech Lead | ADR-0018 (Manifestos declarativos e `apply -f`) — aceito | PO/PM |
| 1.6    | 2026-06-17 | Tech Lead | ADR-0019 (Interfaces são clientes da API) — aceito | PO/PM |
| 1.7    | 2026-06-23 | Tech Lead | ADR-0023 (Especialização do Kind Repo) — proposto; ADRs irmãos 0020/0021/0022/0024 reservados | — |
| 1.8    | 2026-06-23 | Tech Lead | ADRs irmãos 0020/0021/0022/0024 escritos (proposto) | — |
| 1.9    | 2026-06-23 | Tech Lead | ADR-0023 **aceito** pelo PO/PM; spec SPEC-REPO-DADOS criada | PO/PM |
| 1.10   | 2026-06-23 | Tech Lead | ADR-0025 (Agente modo `code` — Claude Code 2b no workspace) — proposto | — |
| 1.11   | 2026-06-23 | Tech Lead | ADR-0026 (Kind `LLMProvider` — config de IA reutilizável; análise de repo por Agente) — proposto | — |
| 1.12   | 2026-06-26 | Tech Lead | ADR-0027 (Multiusuário, auth e credenciais cifradas) — **aceito**; épico implementado (Fases 1–5 + UI) | PO/PM |
| 1.13   | 2026-06-26 | Tech Lead | ADR-0028 (Endurecimento do Agente modo `code` — workspace restrito, allow/deny de tools, concorrência, gate) — proposto | — |
| 1.14   | 2026-07-01 | Tech Lead | ADR-0030 (Kind `Traducao` — tradutor de PDFs de alta fidelidade via PyMuPDF) — **aceito** | PO/PM |
| 1.15   | 2026-07-01 | Tech Lead | ADR-0031 (Tradução em 2 estágios — MT bruta + refino por LLM, modular e resumível) — **aceito** | PO/PM |
| 1.16   | 2026-07-01 | Tech Lead | ADR-0032 (Export de tradução para Markdown/EPUB via pandoc) — **aceito** | PO/PM |
| 1.17   | 2026-07-01 | Tech Lead | ADR-0033 (Render editorial ipsis-litteris — híbrido por papel de bloco) — **aceito** | PO/PM |
| 1.18   | 2026-07-01 | Tech Lead | ADR-0034 (Refino em lotes maiores + comparador de consistência opt-in) — **aceito** | PO/PM |
| 1.19   | 2026-07-02 | Tech Lead | ADR-0038 (Pool de execução de traduções — concorrência, fila e escalonamento) — **aceito** | PO/PM |
| 1.20   | 2026-07-02 | Tech Lead | ADR-0039 (Paralelismo de páginas entre réplicas + retry curto persistido antes de escassez) — **aceito** | PO/PM |

---

> Um **ADR** registra uma decisão de arquitetura: contexto, alternativas e
> consequências. ADRs são **imutáveis** depois de aceitos — para mudar uma
> decisão, abra um novo ADR que **substitui** o anterior. Use o
> [template](template-adr.md).

## Como criar um ADR

1. Copie [`template-adr.md`](template-adr.md) para `ADR-NNNN-<slug>.md` (próximo
   número livre).
2. Preencha contexto, decisão, alternativas, consequências. Status `proposto`.
3. PO/PM revisa → aceite → status `aceito`; atualize a [constituição](../constituicao.md)
   e este índice.
4. Se substitui outro ADR, marque ambos (`substitui` / `substituido-por`).

## Índice

| ADR | Título | Status | Origem |
|---|---|---|---|
| [0001](ADR-0001-ia-em-dois-modos.md) | IA em dois modos: análise (2a) vs agente (2b) | aceito | Endurecimento A1 |
| [0002](ADR-0002-modelo-de-dados.md) | Modelo de dados SQLite | aceito | Endurecimento A2 |
| [0003](ADR-0003-seguranca-meta-loop.md) | Modelo de segurança do meta-loop | aceito | Endurecimento A3 |
| [0004](ADR-0004-contrato-collect.md) | Contrato tipado do `collect` | aceito | Endurecimento B4 |
| [0005](ADR-0005-orcamento-reativo.md) | Orçamento de token reativo | aceito | Endurecimento B5 |
| [0006](ADR-0006-erro-e-resiliencia.md) | Tratamento de erro e resiliência | aceito | Endurecimento B6 |
| [0007](ADR-0007-contrato-de-teste.md) | Contrato de teste da rotina | aceito | Endurecimento B7 |
| [0008](ADR-0008-roteamento-e-extracao.md) | Roteamento e extração de parâmetros | aceito | Endurecimento C8 |
| [0009](ADR-0009-handoff-entre-modos.md) | Handoff entre modos via `SPEC.md` | aceito | Endurecimento C9 |
| [0010](ADR-0010-observabilidade-claude-p.md) | Observabilidade via `claude -p` JSON | aceito | Endurecimento C10 |
| [0011](ADR-0011-ci-cd-versionamento.md) | Política de CI/CD e versionamento | aceito | Política de desenvolvimento |
| [0012](ADR-0012-empacotamento-docker.md) | Empacotamento e deploy via Docker | aceito | Sempre-ligado |
| [0013](ADR-0013-barreira-de-entrada.md) | Barreira de entrada (registro só com intenção) | aceito | Lição de casa (item 0) |
| [0014](ADR-0014-pool-de-ideias-desenvolvimento.md) | Pool de ideias → desenvolvimento (autoimplementação, ativação humana) | aceito | Lição de casa (pool, prioridade máxima) |
| [0015](ADR-0015-core-api-de-objetos.md) | **Core como API de objetos (estilo Kubernetes)** | **aceito (prioridade máx.)** | Motor central + UI web |
| [0016](ADR-0016-ia-plugavel-kind-prompt.md) | Chamadas de IA plugáveis via Kind `Prompt` | aceito | IA conectável, não hard-coded |
| [0017](ADR-0017-gui-por-kind-abstrai-api.md) | Todo Kind tem GUI completa que abstrai a API | aceito | Ações + config visual por Kind |
| [0018](ADR-0018-manifestos-e-apply-f.md) | Manifestos declarativos e `apply -f`; interface como cliente da API | aceito | Manifestos de domínio + loader |
| [0019](ADR-0019-interfaces-clientes-da-api.md) | Interfaces são clientes da API | aceito | API pura + /_schema (sub-projeto 2) |
| [0020](ADR-0020-views-especializadas-por-kind.md) | Views especializadas por Kind (o "quadro branco") | proposto | Brainstorm Repo (carro-chefe) |
| [0021](ADR-0021-rotina-para-job.md) | Renomeação Rotina → Job | proposto | Brainstorm Repo (carro-chefe) |
| [0022](ADR-0022-motor-de-ia-plugavel.md) | Motor de IA selecionável e plugável (incl. local) | proposto | Brainstorm Repo (carro-chefe) |
| [0023](ADR-0023-especializacao-kind-repo.md) | **Especialização do Kind Repo** (multi-branch, git-graph, serialização/análise) | **aceito** | Brainstorm Repo (carro-chefe) |
| [0024](ADR-0024-kind-agente.md) | Kind `Agente` (analisador configurável) | proposto | Brainstorm Repo (carro-chefe) |
| [0025](ADR-0025-agente-modo-code.md) | **Agente modo `code`** (Claude Code agêntico 2b no workspace) | proposto | Pedido do PO ("ser um Claude Code") |
| [0026](ADR-0026-llm-provider.md) | **Kind `LLMProvider`** (config de IA reutilizável; análise de repo por Agente) | proposto | Pedido do PO ("ia provider/llm") |
| [0027](ADR-0027-multiusuario-credenciais.md) | **Multiusuário (isolamento total), auth e credenciais cifradas** (cofre Fernet, User/Credential, GitHub device flow, sessão, escopo por `labels.owner`) | **aceito** | Pedido do PO ("multiusuário + segurança") |
| [0028](ADR-0028-endurecimento-agente-code.md) | **Endurecimento do Agente modo `code`** (workspace restrito, allow/deny de tools, limite de concorrência, gate de curadoria, runs persistentes) | proposto | Hardening Tema 1 (fecha §Pendências do ADR-0025) |
| [0029](ADR-0029-web-shell-da-api.md) | **`web/` como shell gráfico principal da API** (Electron/Tauri-ready, design system DesignSync) | aceito | Pedido do PO (overhaul do front) |
| [0030](ADR-0030-kind-traducao-pdf.md) | **Kind `Traducao`** (tradutor de PDFs de alta fidelidade; in-place redaction+reinsert via PyMuPDF) | **aceito** | Pedido do PO ("traduzir PDFs preservando design") |
| [0031](ADR-0031-traducao-mt-mais-refino.md) | **Tradução em 2 estágios** (MT bruta via deep-translator + refino por LLM; modular, Haiku default, resumível) | **aceito** | Pedido do PO (timeout/tokens; refino sobre bruto) |
| [0032](ADR-0032-export-traducao-md-epub.md) | **Export `.md`/`.epub`** (serializa PDF traduzido → Markdown; EPUB via pandoc) | **aceito** | Pedido do PO ("out epub/md, reusar programa que já faz isso") |
| [0033](ADR-0033-render-editorial-hibrido.md) | **Render editorial ipsis-litteris** (híbrido por papel: prosa reflui + página extra; encaixados fit; imagens intactas; notas de rodapé) | **aceito** | Norte do PO (PDF nível editorial p/ democratizar artigos) |
| [0034](ADR-0034-refino-lotes-e-comparador.md) | **Refino em lotes maiores + comparador de consistência opt-in**: `lote_refino` 20→60; mapa de unificação de termos/nomes aplicado antes do render | **aceito** | PO: lotes maiores + comparador geral p/ consistência do documento inteiro |
| [0035](ADR-0035-job-pausavel-reagendavel.md) | **Job pausável/reagendável por escassez** (mid-run): pausa+checkpoint e retoma sozinho após a janela de quota; capacidade genérica do núcleo | **aceito** | PO: "parar por escassez e terminar sozinho daqui X horas" |
| [0038](ADR-0038-pool-execucao-traducao.md) | **Pool de execução de traduções**: teto de concorrência escalável em runtime + fila FIFO + visibilidade agregada (API/UI) | **aceito** | PO: rodar vários lotes ao mesmo tempo, com controle/ciclo de vida/escalonamento/visibilidade |
| [0039](ADR-0039-paralelismo-paginas-e-retry-timeout.md) | **Paralelismo de páginas entre réplicas** (mesmo dial do pool) + **retry curto persistido** (timeout: até 5x/5min antes de declarar escassez confirmada) | **aceito** | PO: distribuir páginas restantes entre réplicas; timeout ≠ escassez — só 5 falhas seguidas garante limite |
| [0036](ADR-0036-render-editorial-modelo-semantico.md) | **Render editorial por modelo semântico + WeasyPrint** (default): fluxo HTML/CSS justificado, estilos/imagens/código preservados; in-place (0033) vira fallback | **aceito** | PO: qualidade editorial usável — "substituir o texto respeitando estilo/elementos/normas" |
| [0040](ADR-0040-fallback-motor-ia-e-agente-refino.md) | **Fallback bidirecional claude↔ollama** em `ia.invocar` (modelo correto por motor, sem herdar do outro) + **`Traducao.spec.agente_refino`** (Agente/LLMProvider configurável, mesmo padrão do `Repo.analyze_agente`) | **aceito** | PO: tokens do Claude esgotados mid-tradução; usar o Ollama da LAN como motor de dev com fallback nos dois sentidos |
| [0041](ADR-0041-fidelidade-tipografica-e-paginacao-adaptativa.md) | **Fidelidade tipográfica real + fólio/quebras extraídos do original**: fonte embutida, ênfase inline, cor de link herdada, listas numeradas, nota de rodapé nativa, fólio via `string-set` (dinâmico), quebra de página por nível de heading extraída estatisticamente do PDF | **aceito** | PO: render ainda "muito ruim, perdendo informação"; quer ipsis litteris de verdade — fonte/quebras/numeração extraídas do original, não inventadas |
| [0042](ADR-0042-agente-code-via-ollama.md) | **Agente modo `code` via Ollama nativo** (segundo motor 2b): loop de tool-calling próprio (`agente_ollama.py`) contra `POST /api/chat`; despacho por motor resolvido com fallback pro claude se o endpoint estiver fora do ar antes do 1º turno; erro de UMA tool vira `warning` não-fatal | **aceito** | PO, prioridade máxima: "ele [Ollama] vai ser o motor de desenvolvimento... quero essa capacidade e visibilidade... como um Claude Code mas como render do Kind Agente" |
| [0043](ADR-0043-recuperacao-orfaos-boot-e-serializacao-ollama.md) | **Recuperação de jobs órfãos no boot** (Traducao presa em "traduzindo" por restart) + **serialização de chamadas Ollama** (`_OLLAMA_SEMAFORO`) — evita falso-positivo de fallback por fila do lado do servidor | **aceito** | Operacional: restart travava tradução sem saída pela UI; paralelismo de página (0039) contra Ollama sequencial estourava timeout client-side |
| [0044](ADR-0044-qualidade-e-auto-mode-agente-ollama.md) | **Qualidade/auto mode do Agente via Ollama**: `search_text`/`find_files` (grep/glob reais), CLAUDE.md injetado no system prompt (cacheado), `max_turnos` configurável, `POST /_self_restart` admin-only (commit → reinício destacado do processo local), aba 🤖 Auto na UI | **aceito** | PO: quer qualidade de sessão Claude Code só que "full ollama" pra não parar quando o limite do Claude acabar; "auto mode também é super importante"; "tem que ter capacidade de commitar, reiniciar a instância" |
| [0045](ADR-0045-controle-real-e-ollama-por-padrao-na-traducao.md) | **Fim do fallback silencioso ollama→claude na tradução** (`invocar(fallback=False)`) + Ollama como motor padrão + controle real do job (pausar entre páginas, recomeçar do zero, re-refinar sem repagar a MT bruta) | **aceito** | Bug: tradução configurada com `motor=ollama` estava caindo pro claude às escondidas, queimando cota; PO: "é para traduzir usando ollama"; "preciso de controle real... pausar, recomeçar, re-refinar"; "a seleção padrão... precisa ser o ollama" |
| [0046](ADR-0046-outline-hierarquico-por-papel.md) | **Outline hierárquico do PDF por papel estrutural**: `bookmark-level` reatribuído por Parte/Capítulo/Seção (regex de texto), desacoplado do tamanho de fonte; rótulo de parte solto suprimido; no-op em livro sem parte extraível (não regride Kubernetes) | **aceito** | PO: "os tópicos do lado esquerdo estão todos bagunçados… provavelmente o problema no sumário seja a hierarquia de h1/h2" — Parte e Capítulo caíam no mesmo nível |

## Lastro

O design completo que originou estes 10 ADRs está em
[`../../superpowers/specs/2026-06-16-atlas-endurecimento-design.md`](../../superpowers/specs/2026-06-16-atlas-endurecimento-design.md).

## ADRs retroativos a escrever (backlog)

As decisões travadas da [constituição](../constituicao.md) que ainda não têm ADR
próprio (Telegram, Claude Code na assinatura, script-primeiro, pastas plugáveis)
são candidatas a ADRs retroativos. Rastreado no [backlog](../../roadmap/backlog.md).
