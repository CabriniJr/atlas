---
titulo: ADR-0003 — Modelo de segurança do meta-loop
id: ADR-0003
status: aceito
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-16
substitui: —
substituido-por: —
---

# ADR-0003 — Modelo de segurança do meta-loop

## Histórico de revisão
| Versão | Data       | Autor     | Mudança          | Aprovado por |
|--------|------------|-----------|------------------|--------------|
| 1.0    | 2026-06-16 | Tech Lead | Aceito (endurecimento A3) | PO/PM |

---

## Status
`aceito`.

## Contexto
O meta-loop **gera código Python que o motor depois executa** com acesso ao banco,
e o `claude -p` agêntico roda tools na máquina. A segurança original cobria só
restrição de ID do Telegram e segredos fora do git — o caminho geração→execução
não estava no modelo de ameaça. É a maior superfície de risco do sistema.

## Decisão
Invariantes de segurança do meta-loop:

1. **Inativo por padrão:** código gerado nasce `ativa: false` e **nunca é
   auto-executado**; ativação exige `/ativar` humano + commit.
2. **Workspace restrito na geração:** o agente (2b) só escreve sob
   `routines/<nova>/`; tools limitadas.
3. **Execução contida do `collect`:** subprocess com timeout; segredos só por
   injeção explícita.
4. **Análise sem superfície:** fase `analyze` roda single-turn sem tools (2a).

## Alternativas consideradas
| Alternativa | Prós | Contras | Por que não |
|---|---|---|---|
| Confiar na revisão humana só | Simples | Sem rede de segurança técnica | Erro humano é fácil |
| Sandbox completo (container) | Forte isolamento | Complexidade alta no notebook | Fere P7; exagero p/ monousuário |

## Consequências
- **Positivas:** o ponto mais perigoso fica explicitamente contido; rastreável e
  reversível (P9).
- **Negativas:** ativar rotina sempre exige passo humano (intencional).
- **Impacto na constituição:** decisões #8 e #11; seção de segurança.

## Pendências
Avaliar uma rotina built-in futura de **revisão de segurança automática** da pasta
gerada antes do `/ativar`.
