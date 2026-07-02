---
titulo: ADR-0040 — Fallback bidirecional claude↔ollama + Agente de refino na tradução
id: ADR-0040
status: aceito
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-07-02
substitui: —
substituido-por: —
---

# ADR-0040 — Fallback bidirecional claude↔ollama + Agente de refino na tradução

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-07-02 | Tech Lead | Proposta + implementação (pedido direto do PO) | PO/PM |

---

## Status
`aceito` — implementado em ritmo ágil (pedido do PO, tokens do Claude esgotados
com uma tradução em curso).

## Contexto

Uma tradução em produção (`Traducao/observability-engineering-achieving-prod`)
pausou porque a assinatura Claude bateu o limite de sessão. O PO tem um segundo
servidor Ollama disponível na LAN (`192.168.86.38:11434`; llama3.1, gemma4,
qwen3.6) e pediu, nas próprias palavras: "ele [Ollama] vai ser o motor de
desenvolvimento, você vai ser o agente editor e orquestrador... quero que as
instâncias de tradução sejam feitas com essa API e não com o claude... porém
caso não seja possível o fallback imediato é o claude" — ou seja, **fallback
nos dois sentidos**, não uma troca manual de motor.

Isso expôs duas lacunas no adapter existente ([ADR-0022](ADR-0022-motor-de-ia-plugavel.md)):

1. `ia.invocar(motor="ollama")` sem `modelo` explícito herdava o default do
   *claude* (`_MODELO_PADRAO = "claude-haiku-..."`) — um modelo que não existe
   no servidor Ollama. Motor `ollama` nunca era, de fato, plug-and-play.
2. Falha de um motor sempre propagava erro; não havia rede de segurança para o
   outro motor.

Separadamente, o PO pediu um "agente especializado" em revisar a tradução bruta
com foco em fidelidade máxima — o que já existe como conceito no Kind `Agente`
([ADR-0024](ADR-0024-kind-agente.md) regra 2, concretizada para `Repo` via
`analyze_agente`) mas nunca foi estendido ao pipeline de tradução
([ADR-0031](ADR-0031-traducao-mt-mais-refino.md)).

## Decisão

1. **`ia.modelo_padrao(motor)`** — novo helper: `"gemma4"` para `ollama`,
   `_MODELO_PADRAO` para `claude`. Todos os call-sites de
   `atlas.traducao.traducao_ia` que resolviam `cfg.modelo or _MODELO_PADRAO`
   passam a resolver `cfg.modelo or modelo_padrao(cfg.motor)` — nunca mais
   pedem um modelo claude a um endpoint ollama (ou vice-versa).

2. **Fallback bidirecional em `ia.invocar()`** (`_chamar_claude` /
   `_chamar_ollama` internos): motor pedido falha (qualquer `InvocarErro` —
   timeout, endpoint fora do ar, limite de sessão, erro de auth) ⇒ tenta o
   outro motor uma vez, **sem herdar o modelo do motor original**. Se o motor
   pedido funciona, o fallback nunca roda (zero custo extra no caminho feliz).
   Se os dois falham, propaga o erro do fallback (a tentativa decisiva).

3. **`_OLLAMA_ENDPOINT_PADRAO` → `http://192.168.86.38:11434`** (era
   `192.168.86.22`, outra máquina do PO). Continua sobreponível por
   `ATLAS_OLLAMA_ENDPOINT`.

4. **`Traducao.spec.agente_refino`** (opcional, texto — mesmo padrão de
   `Repo.spec.analyze_agente`): nome de um `Agente`. `resolver_agente_refino()`
   em `traducao_ia.py` resolve `(motor, modelo, instrucao)` do Agente (via
   `LLMProvider`, se referenciado, com a mesma precedência de
   [ADR-0026](ADR-0026-llm-provider.md): modelo do Agente > modelo do
   provider). `instrucao` vira `cfg.instrucao_refino`, que
   `montar_prompt_refino` usa no lugar do parágrafo de persona padrão — **o
   contrato de glossário e de formato de resposta numerado é sempre mantido**
   (o parser depende dele), só a ênfase/persona é pluggable. Sem
   `agente_refino`, comportamento idêntico ao anterior (retrocompatível).

5. **Não** foi adicionado override de `endpoint` por Agente/Traducao — o
   endpoint ollama continua um único valor global (`ATLAS_OLLAMA_ENDPOINT` /
   default acima). YAGNI: o pedido era "usar essa API", não múltiplos
   endpoints simultâneos.

## Alternativas consideradas

| Alternativa | Prós | Contras | Veredito |
|---|---|---|---|
| **Fallback bidirecional dentro de `ia.invocar()`** | transparente a todos os chamadores (tradução, Agente chat, glossário); zero mudança de contrato pública | esconde qual motor realmente respondeu do chamador (mitigado: log de warning) | **escolhida** |
| Fallback só no chamador (`traduzir_pdf.py`) | explícito no ponto de uso | duplicaria a lógica em todo lugar que chama `invocar` (glossário, comparador, chat do Agente) | rejeitada |
| Motor "auto" novo (enum) em vez de fallback automático do motor pedido | explícito na spec | o PO pediu fallback do que já está configurado, não um 3º valor de motor | rejeitada |
| Endpoint por Agente/Traducao (override fino) | flexível para múltiplos servidores Ollama | não pedido; complexidade sem caso de uso agora | adiada (pendência) |

## Consequências

- **Positivas:** traduções não travam mais quando um dos dois motores está
  indisponível; motor `ollama` agora é realmente plug-and-play (modelo
  correto por default); refino de tradução ganha o mesmo mecanismo de
  Agente/Prompt configurável que o `Repo` já tinha, sem duplicar arquitetura.
- **Negativas / custos:** uma falha "silenciosa" do motor pedido agora produz
  resposta de qualidade potencialmente diferente (outro modelo) em vez de
  erro — aceitável para tradução (best-effort, ADR-0006), a observar se virar
  problema para outros consumidores de `ia.invocar`. `agente_refino` de custo
  zero global (mesmo endpoint para todos) até que surja um caso real de
  multi-endpoint.
- **Impacto na constituição:** estende ADR-0022 (fallback) e ADR-0024 regra 2
  (segundo consumidor de `Agente` referenciado por Kind, depois de `Repo`).
  Nenhuma decisão anterior é revertida.

## Pendências
- Override de `endpoint` por `LLMProvider`/`Traducao` quando houver mais de um
  servidor Ollama em uso simultâneo.
- Métrica/label no `status.log_ia` indicando **qual motor de fato respondeu**
  cada lote (hoje só loga o `modelo` pedido, não se houve fallback).
