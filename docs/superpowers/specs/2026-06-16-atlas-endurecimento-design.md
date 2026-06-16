# Atlas — Endurecimento da arquitetura (design)

> Spec de **endurecimento** da constituição em [`docs/atlas-arquitetura.md`](../../atlas-arquitetura.md).
> Registra as decisões que fecham os furos, tensões internas e lacunas
> encontradas na leitura crítica de 2026-06-16. A arquitetura foi atualizada
> para refletir o estado final destas decisões; este documento explica **por
> quê**.

**Data:** 2026-06-16
**Escopo:** todos os 10 pontos (A1–A3 raiz, B4–B7 lacunas, C8–C10 menores).

---

## Resumo

A arquitetura original é forte em filosofia e fraca em fundação concreta. O
endurecimento ataca três problemas de raiz — o modelo de IA conceitualmente
embaralhado, a ausência de modelo de dados, e a falta de modelo de segurança
para o meta-loop — e mais sete lacunas que tornariam o sistema frágil na
construção. Nenhuma decisão travada da §18 é revogada; elas são **refinadas**.

---

## A1 — Dois tipos de IA, não um

### Problema
O doc trata "IA" como sinônimo de "Claude Code" (`claude -p`, agente com tools e
acesso a filesystem). Mas as fases de análise das rotinas (resumo diário,
interpretar um diff, "o que revisar neste livro") são **um prompt → uma
resposta**: não precisam de loop agêntico, tools, nem acesso a arquivos. Rodar o
agente pesado para isso custa cold-start e abre superfície desnecessária.

Há também uma tensão de princípio: §2.1 diz "economia de token acima de tudo",
mas §7 diz "sem billing por token, sai da assinatura". Se o token sai da
assinatura, o recurso escasso **não é o token** — é o limite de uso/sessão da
assinatura.

### Decisão
Separar explicitamente dois mecanismos de IA, ambos na assinatura:

- **Chamada de análise (Camada 2a).** Single-turn: `claude -p` com
  `--output-format json`, `--max-turns 1`, **sem tools e sem acesso a
  arquivos**, modelo vindo da config da rotina. Usada por toda fase `analyze` de
  rotina. Remove overhead e superfície agêntica.
- **Chamada de agente (Camada 2b).** Claude Code completo, com tools e escrita
  de arquivo. **Único consumidor:** o meta-loop (geração de rotinas).

Reframe do princípio §2.1: o recurso escasso é o **limite de uso da assinatura**;
"economia de token" é o proxy operacional disso. A Camada 2 (§5) passa a ter dois
sub-níveis: **2a — análise (single-turn)** e **2b — agente (meta-loop)**.

### Trade-off considerado
Alternativa descartada: usar a Claude Messages API para análise. Reintroduziria
billing por token de API, violando a decisão travada §18. Manter tudo na
assinatura via `claude -p` single-turn preserva a decisão e ainda elimina o risco
agêntico.

---

## A2 — Modelo de dados (a fundação que faltava)

### Problema
O SQLite é citado em §9.2 (`collect` lê o banco), §12 (metas) e §13 (runs), mas o
schema nunca é definido. As entidades são a fundação real do sistema.

### Decisão
Schema mínimo (YAGNI — só o que as rotinas built-in e o sistema de metas exigem):

| Tabela | Campos (conceituais) |
|---|---|
| `activities` | `id`, `ts`, `dominio`, `rotina`, `texto_cru`, `dados_json` |
| `goals` | `id`, `titulo`, `categoria`, `horizonte`, `alvo`, `unidade`, `progresso`, `prazo`, `status` |
| `goal_links` | `id`, `activity_id`, `goal_id`, `contribuicao` |
| `books` | `id`, `titulo`, `pagina_atual`, `total_paginas`, `percentual`, `ultimo_visto_ts` |
| `runs` | `id`, `rotina`, `iniciado_em`, `terminado_em`, `status`, `camada`, `gate_passou`, `tokens_in`, `tokens_out`, `custo_usd`, `ref_saida` |
| `routine_state` | `rotina`, `chave`, `valor`, `atualizado_em` |

Notas de design:
- O específico de cada domínio vive em `activities.dados_json` — mantém o motor
  agnóstico (§2.3). O domínio nunca vira coluna.
- `goal_links` resolve "uma atividade alimenta uma ou mais metas" (§12) sem
  acoplar atividade a meta.
- `routine_state` fornece os dados do "último run" que o contrato do `collect`
  exige (§9.2) e guarda checkpoints (ex.: último estado do Librera).
- `runs` é a base da observabilidade (§13). O orçamento é **derivado** de `runs`,
  não uma tabela à parte.

---

## A3 — Modelo de segurança do meta-loop

### Problema
O meta-loop **gera código Python que o motor depois executa** com acesso ao
banco, e o `claude -p` agêntico roda tools na máquina. §17 cobre só restrição de
ID do Telegram e segredos fora do git — o caminho geração→execução não está no
modelo de ameaça.

### Decisão
Invariantes de segurança do meta-loop (endurecem §17):

1. **Inativo por padrão.** Código gerado nasce com `ativa: false` e **nunca é
   auto-executado**. Ativação exige `/ativar` humano + commit. Invariante forte,
   não convenção.
2. **Workspace restrito na geração.** O `claude -p` agêntico (2b) só escreve sob
   `routines/<nova>/`; tools limitadas ao necessário para gerar a pasta.
3. **Execução contida do `collect`.** Roda em subprocess com timeout; segredos
   chegam só por injeção explícita (nunca por leitura ambiente implícita).
4. **Fronteira de confiança declarada.** O meta-loop é o único ponto onde código
   de um modelo externo entra no sistema. Mitigações: revisão humana +
   inativo-por-padrão + execução contida.

---

## B4 — Contrato tipado do `collect`

### Problema
§9.2 define o retorno do `collect` como "dicionário livre". Sem schema, o `store`
(§9.1) não tem como saber o que persistir e onde. E substituir texto externo
(diff, JSON do Librera) direto no template de prompt é superfície de prompt
injection.

### Decisão
O `collect` devolve um resultado tipado:

```
CollectResult = {
  data:  dict,            # alimenta a renderização do prompt (análise)
  store: list[StoreOp],   # mapeamento explícito de persistência
}
StoreOp = { entity: str, fields: dict }
```

Persistência deixa de ser adivinhação: cada `StoreOp` diz a entidade e os campos.
Texto externo entra no prompt em **blocos delimitados como dados** (não como
instrução). Como a análise roda single-turn sem tools (A1), o grosso do risco de
injeção já está neutralizado: mesmo texto malicioso não tem ferramentas para
acionar.

---

## B5 — `budget_tokens` honesto (reativo)

### Problema
§9.1/§13 tratam `budget_tokens` como teto pré-voo, mas o custo de uma chamada só
é conhecido **depois** que ela termina.

### Decisão
- **Pré-voo:** limita o *output* via `--max-turns 1` + teto de tokens de saída; o
  tamanho do *input* é responsabilidade da disciplina do `collect`.
- **Teto global (diário/mensal):** checado no **agendador** antes de despachar —
  se o consumo acumulado em `runs` já estourou, não despacha.
- **`budget_tokens` por rotina:** vira **disjuntor para runs futuros** (registra o
  excesso e bloqueia/avisa a próxima execução), não um cap pré-voo da execução
  atual.

---

## B6 — Tratamento de erro e resiliência (nova seção)

### Problema
Nenhum modo de falha está especificado: `collect` que lança, `claude -p` que dá
timeout, Telegram fora do ar, notebook fechado no horário do agendamento.

### Decisão
- **Por fase:** cada fase é encapsulada; falha vira run `failed` + saída segura +
  alerta opcional. O sistema nunca trava por uma rotina quebrada.
- **`claude -p`:** timeout vindo da config → mata, registra, retry opcional (1x).
- **Telegram indisponível:** fila de saída com backoff; o inbound já é pull
  (long-poll), então não perde mensagem recebida.
- **Schedule perdido (notebook off/fechado):** no boot, o agendador detecta runs
  atrasados e decide catch-up por rotina via novo campo de config `catch_up`. O
  resumo diário recupera se estiver dentro de uma janela de X horas; senão, pula
  com registro.

---

## B7 — Contrato de teste da rotina (nova seção)

### Problema
O doc não diz como testar uma rotina antes de ativá-la.

### Decisão
Testabilidade por fase, derivada da pureza do ciclo de vida:
- **`collect`** é puro dado um contexto injetado (relógio, handle do DB,
  `routine_state` do último run) → testável com fixtures, sem rede real.
- **`gate`** é predicado puro → trivialmente testável.
- **`analyze`** → mocka o invocador de IA; testa a **renderização do prompt** a
  partir do `CollectResult.data`, não o modelo.
- O motor expõe um **harness de teste de rotina** que injeta o contexto e roda as
  fases isoladas. Rotinas podem trazer fixtures opcionais.

---

## C8 — Roteamento e extração de parâmetros

### Problema
§6 não define conflito de `triggers` entre rotinas. E §10.1 promete extrair
parâmetros de linguagem natural ("perna hoje, agachamento 80kg 4x10") **sem IA**,
o que é frágil — tensão com o ideal "0 IA na entrada".

### Decisão
- **Conflito de triggers:** o match mais **específico (palavra/alias mais longo)
  vence**; empate → o roteador pergunta; ambiguidade é logada. Rotinas podem
  declarar prioridade opcional.
- **Extração:** caminho feliz é uma **micro-sintaxe** parseável por regex
  (ex.: `treino: agachamento 80kg 4x10`) — 0 IA. Texto livre que não casa cai no
  **fallback Haiku (Camada 1)** para extração. Resolve a tensão honestamente em
  vez de fingir que regex cobre toda linguagem natural.

---

## C9 — Handoff entre os dois modos

### Problema
§2.5 diz que operação e desenvolvimento "nunca se misturam", mas o meta-loop
planeja no Telegram (operação) e dispara o desenvolvimento. O handoff não está
desenhado.

### Decisão
A comunicação entre os modos é por **arquivo**, não por estado de runtime:
- O planejamento (Telegram, operação) escreve um **`SPEC.md`** em
  `routines/<nome>/`.
- O meta-loop (desenvolvimento) **lê esse `SPEC.md`** e gera o restante da pasta.

A fronteira fica limpa: operação produz spec; desenvolvimento consome spec e
produz código. Nenhum estado compartilhado em memória entre as sessões.

---

## C10 — Observabilidade do `claude -p` (verificado)

### Problema
A §13 inteira depende de o `claude -p` expor uso de token de forma parseável.

### Decisão / verificação
`claude -p --output-format json` retorna um objeto de resultado com `usage`
(input/output/cache tokens), `total_cost_usd`, `duration_ms`, `num_turns`,
`session_id`, `is_error`. A §13 é viável.

**Ressalva registrada:** na autenticação por assinatura (não API key), o
`total_cost_usd` é **nocional** — os contadores de token são reais, o custo em
dólar não reflete cobrança. A observabilidade deve tratar tokens como a métrica
de verdade e o custo como estimativa.

> Nota: verificação feita pelo design conhecido da CLI; o binário `claude` não
> estava disponível no ambiente onde este spec foi escrito. Confirmar
> empiricamente com `claude -p "ping" --output-format json` na máquina alvo.

---

## Impacto nas decisões travadas (§18)

Nenhuma decisão travada é revogada. Refinamentos:
- **Motor de IA:** continua Claude Code na assinatura — agora explicitamente
  dividido em **análise single-turn (2a)** e **agente (2b)**.
- **Padrão de rotina:** o "script-primeiro" ganha contrato tipado de `collect` e
  contrato de teste.
- **Resumo diário:** continua a única rotina que sempre usa IA; agora roda como
  análise single-turn (2a), não como agente.

## Itens da §19 fechados por este spec
- Política de retenção de runs → derivar orçamento de `runs`; retenção fica como
  parâmetro de limpeza (a definir valor, mas o mecanismo está em `runs`).
- Formato do sync do Librera → continua em aberto (depende do setup), mas o
  contrato do `collect` (B4) e `books` (A2) já acomodam qualquer fonte.
