# Design — Refino do sistema de tradução (E9-16)

| Campo | Valor |
|---|---|
| **Autor** | Tech Lead (Claude Opus) |
| **Data** | 2026-07-08 |
| **Status** | aprovado (brainstorm) — pendente plano de implementação |
| **Épico** | E9 — Tradutor editorial |
| **ADRs afetados** | novo **ADR-0048**; supersede a *postura de fallback* de [ADR-0045](../../arquitetura/adr/ADR-0045-controle-real-e-ollama-por-padrao-na-traducao.md); refina [ADR-0040](../../arquitetura/adr/ADR-0040-fallback-motor-ia-e-agente-refino.md) e [ADR-0039](../../arquitetura/adr/ADR-0039-paralelismo-paginas-e-retry-timeout.md) |

## Histórico de revisão

| Data | Autor | Mudança |
|---|---|---|
| 2026-07-08 | Tech Lead | Versão inicial (aprovada no brainstorm com o PO). |

---

## 1. Contexto e motivação

O sistema de tradução (épico E9) está maduro: pipeline resumível, pool de execução,
paralelismo de páginas, render editorial de alta fidelidade, controle real
(pausar/recomeçar/re-refinar) e Ollama como motor padrão. Esta leva é um **passe de
refino cirúrgico**, não um redesenho: fecha gaps reais de controle e fallback, dá
ergonomia à UI, revisa o render/serialização e atualiza os docs de controle.

Pedido do PO (verbatim, resumido): revisão de todas as etapas — administração,
serialização, boa UI, **controle refinado**, ajustes finos (rolar abas, recomeçar),
**garantir tentar Ollama e cair pra Claude se precisar**, revisão geral do render, e
atualizar backlog/ADRs.

## 2. Diagnóstico (gaps reais encontrados)

1. **Bug de pausa em paralelo (controle).** `pipeline.checar_pausa` (ADR-0045) só é
   honrado no loop sequencial (`paralelismo=1`). A rotina roda em
   `paralelismo=pool_global.max_concorrente`; quando >1, o botão **⏸ Pausar é
   silenciosamente ignorado**. É o coração do "controle refinado".
2. **Fallback Ollama→Claude ausente na tradução.** ADR-0045 desligou o fallback
   (`invocar(fallback=False)`) para não misturar tom entre blocos nem queimar cota do
   Claude escondido. O PO quer "tenta Ollama, cai pra Claude se precisar" — reabre a
   decisão, exigindo uma política **deliberada e visível** (não o switch silencioso
   por chamada que o 0045 rejeitou).
3. **Abas não roláveis (UI).** `#tabbar` tem `overflow-x:auto` mas scrollbar de 2px e
   sem roda-do-mouse nem setas — na prática não dá pra alcançar abas fora da tela.
4. **Render/serialização.** `editorial_html.py` tem 1772 linhas (candidato a
   revisão + modularização onde clarear). Serialização do cache (escrita atômica) e
   recuperação de órfãos no boot precisam de uma revisão de sanidade.

## 3. Decisões (aprovadas com o PO)

- **Fallback:** escalar o **job inteiro** para Claude, de forma **visível** (novo ADR).
- **UI/Render:** refino/conserto cirúrgico — sem redesenho visual, sem migração pro app React.
- **Sequência:** uma spec única, entrega **incremental** com commits em `main`.
- **Escalada no meio do run:** default **3 falhas de conexão consecutivas**; escala
  **só o restante** (mantém no cache o que já saiu em Ollama).

## 4. Arquitetura da solução

### 4.1 Controle — pausa cooperativa nos dois modos

Unificar a checagem de pausa. Em vez de `checar_pausa` valer só no sequencial:

- Introduzir um `threading.Event` compartilhado (`pausar_evt`) no pipeline. O
  callback `checar_pausa` (que lê `status.pausar_solicitado` do store) seta o evento.
- `_processar_paginas_paralelo`: cada worker, **antes de começar** uma página, checa
  `pausar_evt.is_set()`; se setado, pula a página (não a processa) e o run encerra com
  `motivo_pausa="manual"`. Páginas já em voo terminam normalmente (checkpoint por
  página garante que o progresso persiste).
- `_processar_paginas_sequencial` passa a ler o mesmo evento (mantém o comportamento
  atual).
- A rotina (`rotinas/traduzir_pdf.py`) já traduz `motivo_pausa="manual"` → `fase="pausado"`
  sem retomada automática; nada muda ali além de deixar de passar o `checar_pausa`
  "só sequencial".

**Contrato:** pausar entre páginas é *best-effort cooperativo* — nunca mata uma
chamada de IA em andamento (evita corromper checkpoint). O usuário vê "pausando…" até
a última página em voo terminar.

**Recomeçar durante run:** `reiniciar_traducao` passa a **pausar antes de limpar** o
cache (seta pausa, espera o job sair de `traduzindo`), evitando corrida entre o worker
que escreve o cache e o apagamento.

### 4.2 Fallback escalado e visível (ADR-0048)

Motor pedido em `Traducao.spec.motor` continua respeitado; Ollama é o padrão. A
tradução **não** usa o fallback silencioso por chamada de `ia.invocar`. Em vez disso,
uma camada de política no nível do job decide escalar:

**Estado novo em `status`:**
- `motor_efetivo`: motor realmente em uso (`"ollama"` | `"claude"`); default = `spec.motor`.
- `escalonado_em` / `escalonado_motivo`: timestamp + motivo, quando escala (nota visível).

> **Reconciliação (pós-implementação):** este rascunho previa um contador
> `falhas_conexao_consecutivas` cross-batch (reset por lote OK). A implementação
> adotou, em vez disso, **retry rápido por chamada** dentro do wrapper
> (`escalonar_apos_falhas` tentativas de conexão no Ollama antes de escalar) — mais
> simples e, contra um endpoint determinísticamente fora (connection refused é
> instantâneo), escala já no 1º lote. Não há campo `falhas_conexao_consecutivas`.
> Fonte de verdade: **ADR-0048**.

**Config nova em `ConfigTraducao` / `spec`:**
- `escalonar_apos_falhas: int = 3` — nº de falhas de conexão consecutivas no Ollama
  antes de escalar o restante.
- `escalonar_para: str = "claude"` — motor de destino da escalada (default Claude).

**Classificação de falha** (estende `_classificar_erro`): três classes —
`"conexao"` (endpoint fora do ar / recusa de conexão), `"timeout"` (Ollama ocupado),
`"erro"` (outro). Só a mesma origem (`ia.invocar`/adapter) sabe distinguir "conexão":
o adapter Ollama levanta `InvocarErro("ollama: <urlerror/connrefused>")` — o
classificador casa por padrão de mensagem.

**Gatilhos de escalada:**
1. **Arranque:** a 1ª chamada de IA do run falha com classe `"conexao"` (endpoint
   down antes da 1ª página) → escala imediatamente: `motor_efetivo="claude"`, nota no
   status, o run inteiro roda em Claude.
2. **Meio do run:** `falhas_conexao_consecutivas >= escalonar_apos_falhas` → escala o
   **restante**: `motor_efetivo="claude"`. A parte já traduzida em Ollama fica no cache
   (cache key independe do motor — a chave é `origem>destino:texto`, ver
   `CacheTraducao._chave`), então não há re-tradução; só o pendente vai pra Claude.

**Composição com ADR-0039 (retry/pausa):**
- `motor=ollama` + classe `"timeout"`: mantém os retries curtos do 0039; timeouts
  **não** contam pro contador de conexão (Ollama ocupado ≠ Ollama fora).
- `motor=ollama` + classe `"conexao"`: alimenta o contador de escalada (não é
  escassez de token — esperar 5h não resolve endpoint local fora).
- `motor=claude` (pedido ou já escalado): comportamento atual do 0039 intacto
  (timeout→retry curto→escassez 5h; erro→escassez). Cota do Claude **recupera** com o
  tempo, então a pausa-reagenda continua fazendo sentido nesse motor.

**Chave de design:** a escalada é do **job** (ou do restante), persistida e visível —
nunca um flip por chamada. Dentro de cada trecho (pré e pós escalada) o tom é
consistente. Preserva o espírito do ADR-0045; entrega o pedido do PO.

**Implementação:** a política vive na rotina/pipeline (não em `ia.invocar`, que
continua com `fallback=False` para a tradução). O `invocar_fn` passado ao pipeline
resolve o motor a partir de um estado mutável de motor efetivo compartilhado; ao
escalar, atualiza esse estado e o `status`. Alternativa considerada e rejeitada:
reativar `fallback=True` no `ia.invocar` — reintroduz exatamente o switch silencioso
por chamada que o 0045 removeu.

### 4.3 UI — ajustes finos (dashboard legado)

Sem redesenho. Alvos concretos:

- **Abas roláveis (`style.css` + `main.js`):** roda-do-mouse vertical vira scroll
  horizontal no `#tabbar` (listener `wheel` que traduz `deltaY`→`scrollLeft`); afford.
  visível — scrollbar um pouco maior e/ou gradiente de "há mais abas" nas bordas.
  (Setas de scroll são opcional/nice-to-have; wheel + gradiente já resolvem.)
- **Painel de tradução (`kinds/traducao.js`):**
  - Badge de **motor efetivo** com a escalada visível: `ollama → claude (escalado)`
    quando `status.motor_efetivo != spec.motor`, com tooltip do motivo/hora.
  - ⏸ Pausar funcional durante run paralelo (consequência de 4.1).
  - Cluster de controle (▶ Traduzir / ⏸ Pausar / 🔁 Recomeçar / ♻️ Re-refinar) agrupado
    e com estados claros (habilitado/desabilitado por fase).

### 4.4 Render + serialização — revisão de sanidade

- **Revisão de `editorial_html.py`** caçando bugs (fidelidade tipográfica, paginação,
  colisões). Modularizar **só onde clarear**: candidatos naturais são geometria de
  página, modelo semântico e geração de CSS. Nenhuma mudança que altere a saída visual
  sem teste de regressão que a justifique.
- **Serialização:** confirmar a escrita atômica do cache (tmp+replace, já existe) sob
  os workers paralelos; confirmar que o checkpoint por página não perde blocos numa
  pausa. Revisar `recuperar_orfaos_no_boot` (ADR-0043) contra os novos estados
  (`escalonado`, `motor_efetivo`).

## 5. Componentes e arquivos tocados

| Unidade | Arquivo | Mudança |
|---|---|---|
| Pausa cooperativa paralela | `src/atlas/traducao/pipeline.py` | `pausar_evt` compartilhado nos dois loops |
| Política de escalada | `src/atlas/rotinas/traduzir_pdf.py` | motor efetivo mutável, contador, gatilhos, patch de status |
| Classificação de falha | `src/atlas/traducao/traducao_ia.py` | `_classificar_erro` → 3 classes (`conexao`/`timeout`/`erro`) |
| Config de escalada | `src/atlas/traducao/traducao_ia.py` (`ConfigTraducao`) | `escalonar_apos_falhas`, `escalonar_para` |
| Adapter (sinal de conexão) | `src/atlas/ia.py` | garantir mensagem distinguível de erro de conexão |
| Recomeçar seguro | `src/atlas/rotinas/traduzir_pdf.py` | pausar antes de limpar cache |
| Abas roláveis | `src/atlas/dashboard/style.css`, `main.js` | wheel→scrollLeft + afford. |
| Badge motor efetivo / controle | `src/atlas/dashboard/kinds/traducao.js` | badge escalada, cluster de controle |
| Revisão render | `src/atlas/traducao/editorial_html.py` (+ possíveis módulos novos) | bugs + modularização cirúrgica |
| ADR | `docs/arquitetura/adr/ADR-0048-*.md` | fallback escalado + pausa paralela |
| Backlog/specs | `docs/roadmap/backlog.md`, `docs/specs/traducao-*.md` | E9-16 + fecha gaps E9-11/E9-15 |

## 6. Tratamento de erro

- Pausar nunca mata chamada em voo (evita checkpoint corrompido).
- Escalada é best-effort e **sempre** deixa o job progredir: se Claude também falhar
  pós-escalada, cai no fluxo de escassez existente (ADR-0039) sobre o motor Claude.
- Toda escrita de status é best-effort (ADR-0006): logging não derruba a tradução.

## 7. Testes (TDD)

- **Pausa paralela:** worker vê `pausar_evt` setado entre páginas → run encerra
  `motivo_pausa="manual"`, páginas não iniciadas não são traduzidas, checkpoint íntegro.
- **Escalada arranque:** 1ª chamada Ollama levanta erro de conexão → `motor_efetivo`
  vira Claude, invocações seguintes vão pra Claude.
- **Escalada meio-do-run:** N falhas de conexão consecutivas → restante em Claude;
  blocos já cacheados (Ollama) não são re-traduzidos.
- **Timeout não escala:** timeouts consecutivos no Ollama seguem o retry do 0039, sem
  escalar (contador de conexão fica zero).
- **Recomeçar durante run:** pausa antes de limpar; sem corrida de escrita/apagamento.
- **UI:** wheel no tabbar rola horizontalmente (teste leve/JSDOM se viável).

## 8. Fora de escopo (YAGNI / backlog)

- Redesenho visual do painel de tradução.
- Migração da tela de tradução para o app React (`web/`) — épico à parte.
- Pausa que mata chamada de IA em andamento (cancelamento hard).
- Escalada configurável por estágio (só job-level nesta leva).

## 9. Sequência de entrega (incremental, commits em `main`)

1. Pausa cooperativa em paralelo (+ testes) — fecha o bug de controle.
2. Fallback escalado e visível (+ ADR-0048 + testes).
3. Ajustes de UI (abas roláveis + badge/controle).
4. Revisão de render + serialização.
5. Atualização de backlog/specs.
