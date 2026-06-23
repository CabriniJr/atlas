---
titulo: Dossiê de contexto (diretriz)
id: PROC-DOSSIE
status: aprovado
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-23
---

# Dossiê de contexto (diretriz)

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-06-23 | Tech Lead | Criação — eleva o dossiê de contexto a diretriz do projeto | PO/PM |

---

> **Diretriz.** Todo épico (ou esforço de desenvolvimento com múltiplas tarefas) tem
> um **dossiê de contexto**: um único documento que **agrega os arquivos certos** —
> em ordem de leitura — para um modelo desenvolvedor ganhar contexto rico sem
> garimpar o repositório. **Ao despachar um dev, cole o link do dossiê no prompt.**

## Por que existe

O desenvolvimento do Atlas é feito por agentes despachados a frio (ver
[fluxo de desenvolvimento](fluxo-de-desenvolvimento.md)). Cada despacho recomeça sem
memória da conversa: re-derivar o contexto é caro, lento e fonte de divergência. O
dossiê resolve isso — é o **ponto de entrada curado** de um épico, espelhando o
"antes de qualquer tarefa, leia" do [CLAUDE.md](../../CLAUDE.md), mas focado e
acionável para quem vai codar.

## Quando criar

- Ao abrir um **épico** no [backlog](../roadmap/backlog.md), ou
- Antes de **despachar modelos desenvolvedores** num esforço de múltiplas tarefas.

Quem cria/mantém: o **Tech Lead** (Opus). O dossiê é versionado e nasce `aprovado`.

## Onde mora e como se chama

Junto dos planos do épico, em
`docs/superpowers/plans/<AAAA-MM-DD>-<epico>-dossie-contexto.md`. Linke-o **do épico
no backlog** (ponto de descoberta) e dos planos da feature.

## Estrutura obrigatória

O dossiê **não** repete o conteúdo dos arquivos — ele **aponta** para eles com "o que
extrair". Seções:

| § | Seção | Conteúdo |
|---|---|---|
| 0 | **Regras inegociáveis** | Resumo dos contratos que não se quebra (doc é fonte de verdade, TDD, contratos do domínio, store aditivo, schema-driven…), com links. |
| 1 | **ADRs — o porquê** | Os ADRs do épico, em ordem, cada um com "o que extrair". |
| 2 | **Plano e roadmap — o como** | O(s) plano(s) TDD e a entrada do épico no backlog. |
| 3 | **Código — o onde** | Os arquivos a conhecer, com papel e o que olhar em cada. |
| 4 | **Testes — as regras** | Os arquivos de teste-modelo e o padrão de mock/fixture a copiar. |
| 5 | **Modelo de dados alvo** | Referência rápida das formas (kinds/spec/status) que o épico cria. |
| 6 | **Sequência das fatias** | Ordem dos planos e dependências. |
| 7 | **Armadilhas** | O que costuma quebrar; suposições erradas comuns. |

## Como usar ao despachar um dev

1. No prompt do dev, **cole o link do dossiê** e diga: "leia este dossiê e o
   `CLAUDE.md` antes de começar".
2. O dev segue a ordem do dossiê (§0 → §1 → §2…) e pega o plano da fatia.
3. Mantenha o dossiê **atualizado** conforme o épico evolui (novos planos, ADRs,
   armadilhas) — dossiê desatualizado é bug, como qualquer doc.

## Template

Copie o esqueleto abaixo para iniciar um dossiê novo:

```markdown
---
titulo: Dossiê de contexto — Épico <ID> (<nome>)
id: CTX-<ID>
status: aprovado
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: AAAA-MM-DD
---

# Dossiê de contexto — Épico <ID> (<nome>)

## Histórico de revisão
| Versão | Data | Autor | Mudança | Aprovado por |
|--------|------|-------|---------|--------------|
| 1.0 | AAAA-MM-DD | Tech Lead | Criação | PO/PM |

---

> Ao despachar um dev neste épico, cole o link deste dossiê no prompt.

## 0. Regras inegociáveis
## 1. Leia primeiro — o porquê (ADRs)
## 2. O como — plano e roadmap
## 3. O onde — código a conhecer
## 4. As regras de teste
## 5. Modelo de dados alvo
## 6. Sequência das fatias
## 7. Armadilhas conhecidas
```

## Índice de dossiês ativos

| Épico | Dossiê |
|---|---|
| E7 — Repo como carro-chefe | [2026-06-23-repo-e7-dossie-contexto](../superpowers/plans/2026-06-23-repo-e7-dossie-contexto.md) |
