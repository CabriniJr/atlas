---
titulo: Motor de IA — análise (2a) vs agente (2b)
id: ARQ-IA
status: aprovado
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-16
---

# Motor de IA — análise (2a) vs agente (2b)

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-06-16 | Tech Lead | Criação (vindo de [ADR-0001](adr/ADR-0001-ia-em-dois-modos.md)) | PO/PM |

---

Toda chamada de IA acontece **instanciando o Claude Code localmente** (`claude -p`),
autenticado pelo login do Claude (Pro/Max). Há **dois modos**, e a distinção é
arquitetural ([ADR-0001](adr/ADR-0001-ia-em-dois-modos.md)).

## Modo 2a — Análise (single-turn)

- **O que é:** um prompt → uma resposta. `claude -p --output-format json
  --max-turns 1`, **sem tools e sem acesso a arquivos**, modelo da config da rotina.
- **Quem usa:** toda fase `analyze` de rotina (resumo diário, avaliação de diff,
  revisão de leitura sob demanda).
- **Por quê:** análise não precisa de loop agêntico nem filesystem. Remove
  cold-start agêntico e superfície de execução/injeção.

## Modo 2b — Agente (Claude Code completo)

- **O que é:** Claude Code com tools e escrita de arquivo.
- **Quem usa:** **somente o meta-loop** (geração de rotinas — [seguranca](seguranca.md),
  [ADR-0003](adr/ADR-0003-seguranca-meta-loop.md)).
- **Por quê:** gerar código e escrever a pasta da rotina exige tools de verdade.

## Implicações de projeto

- **Sem billing por token de API** — o uso sai da assinatura.
- **Login precisa estar ativo** no notebook — é a credencial.
- **Concorrência limitada:** cada instância é pesada; o motor mantém fila e um teto
  de instâncias simultâneas.
- **Modelo por rotina:** `haiku` (leve), `sonnet` (análise), raramente `opus`.
- **Captura de uso:** `--output-format json` retorna `usage`, `total_cost_usd`,
  `duration_ms`. O custo em dólar é **nocional** na assinatura — tokens são a
  métrica de verdade ([ADR-0010](adr/ADR-0010-observabilidade-claude-p.md)).
- **Limite da assinatura:** rotinas pesadas podem esbarrar nos limites do Pro.
  Mitigação: fila, modelos mais baratos, fallback opcional (em aberto).

Por causa do overhead de cada instância, o princípio **script-primeiro** (P2) é o
que viabiliza esse modelo economicamente.

## Roteamento e recurso escasso

O recurso escasso não é o token, é o **limite de uso da assinatura** (P1). Por isso
o roteador resolve a maioria das mensagens sem IA (Camada 0), usa Haiku (Camada 1)
só no fallback de intenção, e reserva 2a/2b para análise e geração genuínas. Ver
[ADR-0008](adr/ADR-0008-roteamento-e-extracao.md) e
[orçamento](adr/ADR-0005-orcamento-reativo.md).
