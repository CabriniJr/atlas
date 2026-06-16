---
titulo: Segurança e privacidade
id: ARQ-SEGURANCA
status: aprovado
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-16
---

# Segurança e privacidade

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-06-16 | Tech Lead | Criação | PO/PM        |

---

## Modelo de confiança

Sistema **monousuário** rodando no notebook do dono. A maior superfície de risco
não é externa — é o **meta-loop**, único ponto onde código gerado por um modelo
entra no sistema e acaba executado.

## Controles base

- **Acesso restrito:** o bot só responde ao seu próprio ID no Telegram; qualquer
  outro remetente é ignorado.
- **Dados locais:** o SQLite e o repositório ficam no notebook.
- **Segredos fora do versionamento:** tokens (Telegram) e credenciais nunca em git.
- **IA:** o conteúdo das fases de análise vai para o Claude para processamento —
  relevante se uma rotina lidar com dados sensíveis.

## Segurança do meta-loop (a superfície de execução de código)

Decisão completa em [ADR-0003](adr/ADR-0003-seguranca-meta-loop.md). Invariantes:

1. **Inativo por padrão.** Código gerado nasce `ativa: false` e **nunca é
   auto-executado**; ativação exige `/ativar` humano + commit. Invariante, não
   convenção.
2. **Workspace restrito na geração.** O agente (2b) só escreve sob `routines/<nova>/`;
   tools limitadas ao necessário.
3. **Execução contida do `collect`.** Subprocess com timeout; segredos só por
   injeção explícita, nunca por leitura de ambiente implícita.
4. **Análise sem superfície.** Toda fase `analyze` roda single-turn sem tools (2a):
   texto externo malicioso não tem ferramenta para acionar.

## Proteção contra prompt injection

Texto externo (diff, JSON do Librera, mensagens) que vá a um prompt entra em
**blocos delimitados como dados**, nunca como instrução. Reforçado pelo modo 2a
ser tool-less. Ver [ciclo-de-vida-rotina](ciclo-de-vida-rotina.md) e
[ADR-0004](adr/ADR-0004-contrato-collect.md).

## Pendências

- Política de retenção do `texto_cru` em `activities` (dados sensíveis) — backlog.
- Revisão de segurança automatizada de rotinas geradas antes do `/ativar` — a
  avaliar como rotina built-in futura.
