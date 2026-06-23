---
titulo: ADR-0021 — Renomeação Rotina → Job
id: ADR-0021
status: aceito
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-23
substitui: —
substituido-por: —
---

# ADR-0021 — Renomeação Rotina → Job

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 0.1    | 2026-06-23 | Tech Lead | Proposta (brainstorm Repo, carro-chefe) | — |

---

## Status
`aceito` — aceito pelo PO/PM (2026-06-23); em implementação ágil.

## Contexto

O termo **"Rotina"/"Routine"** permeia o sistema: o Kind `Routine`, a tabela
`routine_state`, a pasta `routines/`, comandos (`/routine`, `/routines`), a API, o
front e a documentação ([ciclo-de-vida-rotina](../ciclo-de-vida-rotina.md), specs). O
PO definiu renomear para **"Job"** em tudo — alinhado com "jobs de repo" e por "job"
descrever melhor a unidade agendável/executável do motor.

É um rename de um **Kind central** e de estado persistido: exige migração cuidadosa
(o store é a fonte de verdade — [ADR-0002](ADR-0002-modelo-de-dados.md),
[ADR-0015](ADR-0015-core-api-de-objetos.md)) e uma janela de compatibilidade para não
quebrar recursos e comandos existentes.

## Decisão

1. **Termo de domínio passa a ser `Job`** ("job", minúsculo no texto): substitui
   "Rotina"/"Routine" em código, API, front, comandos e docs.
2. **Kind `Routine` → `Job`** no store, com **migração aditiva** (ADR-0002):
   reescreve `kind=Routine` para `kind=Job`. Um **alias de compatibilidade** resolve
   `Routine` durante a transição — leitura aceita ambos; escrita grava `Job`.
3. **Comandos e rotas** ganham aliases: `/routine`→`/job`, `/routines`→`/jobs`,
   `/run` inalterado. Os nomes antigos seguem funcionando, **deprecados**, por uma
   janela definida.
4. **Estado e pastas:** `routine_state` → `job_state` (migração aditiva); a pasta de
   carga `routines/` passa a `jobs/`, com **fallback de carga das duas** durante a
   transição.
5. **Documentação:** docs renomeadas (ex.: `ciclo-de-vida-rotina.md` →
   `ciclo-de-vida-job.md`); as antigas viram `obsoleto` com link para a sucessora
   (constituição: nada é apagado).

## Alternativas consideradas

| Alternativa | Prós | Contras | Veredito |
|---|---|---|---|
| **Rename completo Rotina→Job com alias de compat + migração aditiva** | terminologia coerente; sem quebra; reversível por janela | rename amplo; migração de dados; manter aliases | **escolhida** |
| Manter "Rotina" | custo zero | contraria a diretriz do PO; diverge de "jobs de repo" | não atende |
| Renomear só na UI (label "Job", Kind segue `Routine`) | barato | divergência termo↔código/API; confunde a API k8s-like | inconsistente |
| Rename sem alias (corte seco) | simples | quebra recursos/comandos/estado existentes | arriscado demais |

## Consequências

- **Positivas:** vocabulário único e coerente em todo o sistema; alinha com o domínio
  Repo ("jobs de repo"); API k8s-like com nome melhor para a unidade executável.
- **Negativas / custos:** rename transversal e de risco (código, API, front, docs,
  estado); migração de dados; janela de compatibilidade e aliases a manter e depois
  remover; testes precisam cobrir os dois nomes durante a transição.
- **Impacto na constituição:** altera terminologia central — exige atualizar a
  [constituição](../constituicao.md) e specs no aceite. Não muda nenhuma decisão
  arquitetural, só o nome.

## Pendências

- Janela de deprecação dos aliases (`Routine`, `/routine`, `routines/`) antes da remoção.
- Ordem segura da migração (store → estado → carga de pasta → docs) com testes a cada passo.
- Impacto no scheduler e em quaisquer índices/queries que referenciem `Routine`/`routine_state`.
- Coordenação com o ADR-0023 (que já usa "jobs de repo" na narrativa).
