---
titulo: ADR-0026 — Kind LLMProvider (config de IA reutilizável)
id: ADR-0026
status: proposto
versao: 0.1
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-23
substitui: —
substituido-por: —
---

# ADR-0026 — Kind `LLMProvider` (configuração de IA reutilizável)

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 0.1    | 2026-06-23 | Tech Lead | Proposta — provider de IA como objeto; Agente referencia por label | — |

---

## Status
`proposto` — implementado em ritmo ágil. Aplica o princípio
[P11](../../visao/principios.md) (tudo é objeto; relacionar por referência) sobre a
configuração de motor de IA do [ADR-0022](ADR-0022-motor-de-ia-plugavel.md).

## Contexto

Hoje cada `Agente` ([ADR-0024](ADR-0024-kind-agente.md)) carrega seus próprios
campos `motor` + `modelo` + `endpoint` + `timeout`. Isso espalha a configuração de
IA por todos os agentes: trocar o modelo padrão, apontar para outro endpoint Ollama
ou ajustar timeout exige editar cada Agente. O PO pediu um objeto único — "ia
provider, ou llm" — para **configurar qual API/modelo usar**, e que **dite o modelo
no agente**.

Isso é exatamente a mentalidade da arquitetura de objetos (P11): a configuração de
motor é uma **coisa** e merece ser um Kind, referenciado pelos agentes — em vez de
campos duplicados.

## Decisão

1. **Kind `LLMProvider`** (schema-driven, [ADR-0017](ADR-0017-gui-por-kind-abstrai-api.md)).
   `spec`: `motor` (claude|ollama — adapter do ADR-0022), `modelo` (modelo padrão
   servido), `endpoint` (ollama/custom), `token_env` (**nome** da env var com o
   token — nunca o segredo), `timeout`.
2. **`Agente.spec.provider`** referencia um `LLMProvider` por nome. O provider
   **dita** motor/endpoint/timeout e o **modelo padrão**.
3. **Resolução de engine** (`_resolve_engine`): se `provider` aponta para um
   `LLMProvider` existente, ele governa; `Agente.spec.modelo` (se houver) **sobrepõe**
   o modelo do provider (override por agente). Sem provider, usa os campos próprios
   do Agente — **retrocompatível**.
4. **Consumido em todos os caminhos de IA do Agente**: chat (`_agente_chat`), modo
   `code` (`_run_agent_bg`, [ADR-0025](ADR-0025-agente-modo-code.md)) e a análise de
   repo (manual e automática — ver abaixo).
5. **Segredos fora do objeto.** O provider guarda só o **nome** da env var
   (`token_env`); o token vive no ambiente (CLAUDE.md: nunca commitar segredos).

### Relação com a análise de repositório (pedido do PO)
A análise de repo deixa de ser hard-coded e passa a ser feita por um **Agente
configurado**: `Repo.spec.analyze_agente` (default `repo-analyzer`) aponta para um
Agente, que via `LLMProvider` dita o modelo e via `prompt` dita a persona. Vale para
o **insight manual** (botão no render) e para a **análise automática no sync**
(`repo_sync/analyze.py`). Concretiza a regra 2 do [ADR-0024](ADR-0024-kind-agente.md).

## Alternativas consideradas

| Alternativa | Prós | Contras | Veredito |
|---|---|---|---|
| **Kind `LLMProvider` referenciado pelo Agente** | config única e reutilizável; agentes magros; alinha P11/ADR-0022 | +1 Kind; resolução com fallback | **escolhida** |
| Manter motor/modelo/endpoint em cada Agente (status quo) | nada a criar | config duplicada; trocar modelo = editar N agentes | rejeitada |
| Variáveis de ambiente / arquivo de config global | simples | invisível na UI; não é objeto; foge do P11 | rejeitada |

## Consequências

- **Positivas:** trocar de modelo/endpoint num lugar afeta todos os agentes que
  usam o provider; análise de repo configurável por Agente; base p/ multi-provider
  (Anthropic API, outros) sem tocar nos agentes.
- **Negativas / custos:** +1 Kind; lógica de resolução com precedência (provider ×
  override do agente) a manter; um Agente pode referenciar um provider inexistente
  (degrada para os campos próprios / defaults).
- **Impacto:** estende ADR-0022 (motor plugável vira objeto) e ADR-0024 (Agente
  referencia provider; regra 2 concretizada). Aplica P11. Nenhuma decisão anterior é
  revertida.

## Pendências
- Suporte a `token_env` de fato nos adapters (hoje claude=assinatura, ollama=local
  sem token). Necessário quando entrar um provider de API paga.
- UI dedicada para escolher provider num dropdown (hoje é campo de texto com o nome).
- Validação de provider inexistente com aviso na UI.
