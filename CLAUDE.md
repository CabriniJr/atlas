# CLAUDE.md — Instruções operacionais para agentes Claude

> Este arquivo é o **ponto de entrada** para qualquer agente Claude que trabalhe
> neste repositório. Ele é curto de propósito: a **fonte de verdade** é a pasta
> [`docs/`](docs/README.md). Aqui ficam só as regras que todo agente precisa
> saber antes de fazer qualquer coisa.

Esta aplicação (codinome **Atlas**) é construída **100% por agentes Claude**. Não
há desenvolvimento humano direto de código — humanos atuam como PO/PM e validam
em alto nível. Por isso a documentação não é um apoio: **é o contrato**.

---

## 1. Regra de ouro

**A documentação em `docs/` é a fonte de verdade.** Se o código diverge da doc, o
código está errado — ou a doc precisa de um ADR que justifique a mudança. Nunca
"resolva" uma divergência em silêncio: ou siga a doc, ou proponha um ADR.

## 2. Antes de qualquer tarefa, leia

1. [`docs/README.md`](docs/README.md) — o mapa da documentação.
2. [`docs/visao/visao-produto.md`](docs/visao/visao-produto.md) — para que serve o
   produto e quais dores ele resolve.
3. [`docs/arquitetura/constituicao.md`](docs/arquitetura/constituicao.md) — o que
   **não muda** sem um ADR.
4. O documento específico da área que você vai tocar.
5. Os [ADRs](docs/arquitetura/adr/README.md) relevantes — eles explicam **por que**
   as coisas são como são.

## 3. Papéis (modelo operacional)

| Papel | Quem | Responsabilidade |
|---|---|---|
| **PO/PM** | Humano | Define visão, dores, prioridade. Certifica soluções em alto nível. |
| **Tech Lead** | Claude Opus | Traduz visão em ADRs/backlog/specs, orquestra os devs, faz curadoria, valida contra a doc. |
| **Dev** | Claude Sonnet (em paralelo) | Implementa a mesma tarefa em visões diferentes, em background. |
| **Curador/Revisor** | Claude Opus | Pega o melhor das soluções paralelas, funde, melhora, valida. |

Detalhe em [`docs/processos/fluxo-de-desenvolvimento.md`](docs/processos/fluxo-de-desenvolvimento.md)
e nas fichas de [`docs/agentes/`](docs/agentes/README.md).

## 4. Princípios inegociáveis (resumo — ver `docs/visao/principios.md`)

1. **Economia do recurso escasso da assinatura** — a IA só roda quando há análise
   ou geração genuína. A maioria das interações custa **zero IA**.
2. **Script-primeiro, agente só quando precisa.**
3. **Agnóstico e plugável** — o motor não conhece domínios; tudo é rotina.
4. **O repositório é o estado do sistema.**
5. **Simplicidade sobre completude.**

## 5. Como trabalhar (todo agente)

- **Siga os padrões existentes.** Leia código vizinho antes de escrever.
- **TDD quando implementar** — teste primeiro (ver `docs/processos/definicao-de-pronto.md`).
- **Não invente escopo.** Faça o que a tarefa pede; proponha o resto no backlog.
- **Toda decisão de arquitetura vira ADR** antes de virar código.
- **Atualize a doc junto com o código** — doc desatualizada é bug.
- **Header + histórico de revisão** em todo documento novo ou alterado.
- **Branch + PR + Conventional Commits.** Feature em branch curta a partir de
  `main`; commits `tipo(escopo): assunto`; PR com CI verde antes do merge. Prod só
  roda tags. Ver [`docs/processos/politica-de-desenvolvimento.md`](docs/processos/politica-de-desenvolvimento.md).

## 6. O que NUNCA fazer

- Ativar/auto-executar código gerado pelo meta-loop sem revisão humana.
- Commitar segredos (tokens do Telegram, credenciais).
- Mudar uma decisão da constituição sem ADR.
- Apagar documentação — marque como `obsoleto` e referencie o substituto.

---

> **Convenção de idioma:** documentação em PT-BR; termos técnicos consagrados
> (ADR, backlog, gate, commit, trigger) ficam em inglês.
