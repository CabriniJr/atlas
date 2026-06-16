---
titulo: Ciclo ideias → documentação → implementação
id: PROC-CICLO
status: aprovado
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-16
---

# Ciclo: Ideias → Documentação → Implementação

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-06-16 | Tech Lead | Criação | PO/PM        |

---

## O ciclo
Este é o **fluxo padrão de desenvolvimento do Atlas**: toda ideia nova passa por formalização na
documentação antes de qualquer implementação.

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. Ideia (PO/PM — informal, conversando)                        │
│    "quero conseguir configurar rotinas pelo chat"               │
└─────────────────┬───────────────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────────────┐
│ 2. Formalização (Tech Lead)                                     │
│    • ADR se decisão arquitetural                                │
│    • Backlog + specs se feature/story                           │
│    • Atualizar docs/processos se mudança de processo            │
│    • Resultado: documentação sólida, clara, fonte de verdade    │
└─────────────────┬───────────────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────────────┐
│ 3. Revisão (PO/PM)                                              │
│    "está claro? falta algo? aprovado?"                          │
│    (Se mudanças → volta a 2)                                    │
└─────────────────┬───────────────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────────────┐
│ 4. Implementação (Agentes)                                      │
│    • Agentes leem a documentação (source of truth)              │
│    • Nenhuma ambiguidade, nenhuma interpretação                 │
│    • Executam com base sólida                                   │
└─────────────────────────────────────────────────────────────────┘
```

## Papel de cada um

### PO/PM — Traz a ideia
- **O quê:** descreve a feature, necessidade ou mudança.
- **Como:** informalmente, em conversas naturais.
- **Resultado esperado:** Tech Lead entender o que precisa ser feito e por quê.

Exemplos:
- "Preciso conseguir configurar rotinas pelo chat."
- "Quero ter um barreira pra não registrar qualquer coisa que eu escrevo."
- "Preciso de um scheduler, sabe, agendar essas rotinas."

### Tech Lead — Formaliza na documentação
**Responsabilidade:** transformar ideia em documentação estruturada que guie agentes.

**Processo:**
1. **Entender** a ideia completamente (perguntas, contexto).
2. **Classificar** o tipo de mudança:
   - Decisão arquitetural? → **ADR novo** (ou atualizar ADR existente).
   - Feature/story? → **backlog** + **specs detalhadas** se complexo.
   - Processo/workflow? → **docs/processos/**.
   - Tradeoff/restrição? → **docs/visao/** ou **docs/arquitetura/**.
3. **Formalizar** respeitando os padrões:
   - **ADRs:** status, contexto, decisão, consequências, alternativas.
   - **Backlog:** épico, histórias, DoR, links para ADRs/specs.
   - **Specs:** requisitos, arquitetura, dados, tratamento de erro, testes.
4. **Commitar** a documentação com mensagem clara.
5. **Apresentar** ao PO/PM para aprovação.

**Objetivo:** documentação sólida o suficiente para que agentes não tenham dúvida.

### Agentes — Implementam com base sólida
- **Leem:** a documentação como source of truth.
- **Executam:** TDD, testes, commits Conventional Commits.
- **Nunca improvisa:** dúvida = volta ao Tech Lead, não ao PO/PM direto.
- **Resultado:** código pronto, testado, alinhado com design.

## O que entra em cada tipo de documentação

| Tipo | Quando | Onde | Conteúdo |
|------|--------|------|----------|
| **ADR** | Decisão de arquitetura / tradeoff importante | `docs/arquitetura/adr/` | Status, contexto, decisão, consequências, alternativas, ligações |
| **Backlog** | Feature nova / story / bug | `docs/roadmap/backlog.md` | Épico, ID, descrição, estado, link para ADR/doc |
| **Spec detalhada** | Feature complexa que precisa design | `docs/specs/` | Requisitos, arquitetura, dados, API, casos de erro, teste |
| **Processo** | Mudança de como trabalhar | `docs/processos/` | Passo-a-passo, papéis, responsabilidades, exemplos |
| **Visão/Princípios** | Mudança na orientação do produto | `docs/visao/` | Motivação, dores, princípios, personas |

## Exemplo: uma ideia completa

### 1. Ideia (PO/PM)
> "Quero conseguir configurar rotinas pelo chat. Tipo, `/nova` pra criar uma, `/gerar` pro Claude fazer o código, `/ativar` pra ligar. E quero conseguir listar com `/rotinas`."

### 2. Formalização (Tech Lead)
- **Cria ADR-0013** (se for decisão sobre meta-loop por chat).
- **Adiciona épico E2** (meta-loop no backlog) com histórias:
  - E2-01: `/nova` — planejamento interativo
  - E2-02: `/gerar` — geração via `claude -p` headless
  - E2-03: `/ativar` — revisar e aplicar
- **Escreve spec detalhada** em `docs/specs/meta-loop-chat.md` com requisitos, fluxo, contrato de dados, tratamento de erro.
- **Commita** com mensagem clara.
- **Apresenta** ao PO/PM.

### 3. Revisão (PO/PM)
> "Tá bom. Mas na etapa de `/gerar`, quero que ele mostre o progresso. Pode adicionar isso?"

Tech Lead volta ao passo 2, adiciona na spec e backlog, re-apresenta.

### 4. Implementação (Agentes)
Agentes recebem a spec, o backlog e os ADRs — **tudo claro, sem ambiguidade**.

## Checklist para Tech Lead

Quando formalizar uma ideia:

- [ ] **Entendi completamente** a ideia (perguntei o suficiente).
- [ ] **Classifiquei** o tipo de mudança (ADR? Backlog? Spec?).
- [ ] **Documentação estruturada** respeitando padrões (headers, frontmatter, links).
- [ ] **Ligações claras** (ADR → backlog, spec → ADR, etc.).
- [ ] **Nenhuma ambiguidade** (alguém que não sou eu consegue ler e entender).
- [ ] **Commitada** com mensagem descritiva.
- [ ] **Apresentada** ao PO/PM e aprovada.

## Por que esse ciclo

1. **Documentação é source of truth** — agentes não interpretam ideias, leem documentação.
2. **Nenhuma ambiguidade** — design é validado ANTES de implementar.
3. **Rastreabilidade** — ideia → doc → implementação é clara.
4. **Agentes independentes** — não precisam perguntar; a doc fala.
5. **Evolução do projeto** — documentação cresce junto; histórico de decisões.
6. **Qualidade** — implementação baseada em design sólido, não em suposições.

## Casos especiais

### Ideia muito simples
Mesmo que simples, passa pelo ciclo. Documentação simples é OK — pode ser uma seção no backlog, não um ADR inteiro. **Mas passa pelo ciclo.**

### Ideia muito grande
Se a ideia é múltiplos sistemas independentes, o Tech Lead **decomposição** antes de formalizar.
Exemplo: "Quero um painel, integração com Google, e relatórios."
→ Decomposição: 3 épicos independentes, cada um com seu ciclo.

### Ideia é clarificação de algo existente
Ainda assim vai para a doc — como ADR (revisa/estende ADR existente) ou como nota no backlog.
Nunca fica só na conversa.

---

**Este é o fluxo de desenvolvimento do Atlas. Toda ideia segue este ciclo.**
