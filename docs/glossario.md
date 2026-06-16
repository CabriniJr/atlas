---
titulo: Glossário
id: DOC-GLOSSARIO
status: aprovado
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-16
---

# Glossário

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-06-16 | Tech Lead | Criação | PO/PM        |

---

- **Atlas** — codinome do produto: motor de rotinas pessoais que roda no notebook,
  usa o Claude como motor de inteligência e fala pelo Telegram.
- **Rotina** — unidade plugável de comportamento; uma pasta sob `routines/` que o
  motor executa pelo ciclo de vida.
- **Ciclo de vida** — a sequência `trigger → collect → gate → analyze → deliver`.
- **Motor (core)** — o runtime fixo (roteador, executor, agendador, adapter,
  invocador, banco). Não muda quando se adiciona rotina.
- **Meta-loop** — o processo de criar rotinas novas a partir de conversa, via
  Claude Code agêntico. O sistema se expande a si mesmo.
- **Camada 0/1/2a/2b** — níveis de custo de execução: código puro / IA leve /
  análise single-turn / agente.
- **Análise (2a)** — chamada de IA *um prompt → uma resposta* (`claude -p`
  single-turn, sem tools). Usada pelas fases `analyze`.
- **Agente (2b)** — Claude Code completo com tools e escrita de arquivo. Só o
  meta-loop usa.
- **Gate** — predicado barato que decide se a fase de análise (IA) deve rodar.
- **Adapter** — implementação plugável de um canal de interface (Telegram, etc.).
- **CollectResult** — retorno tipado da fase `collect`: `{ data, store }`.
- **StoreOp** — operação de persistência explícita: `{ entity, fields }`.
- **ADR** — *Architecture Decision Record*: registro de uma decisão de arquitetura
  com contexto, alternativas e consequências.
- **Best-of-two** — prática de curadoria: dois agentes resolvem a mesma tarefa em
  paralelo; o Tech Lead funde o melhor das duas soluções.
- **PO/PM** — Product Owner / Product Manager (humano): define visão e prioridade,
  certifica em alto nível.
- **Tech Lead** — agente Opus que orquestra os devs, faz curadoria e valida contra
  a documentação.
- **DoR / DoD** — *Definition of Ready* / *Definition of Done*.
