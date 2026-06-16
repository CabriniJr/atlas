# Atlas — Motor de Rotinas Pessoais

> Documento de **arquitetura e projeto**. Não contém código — é a "constituição"
> do sistema, pensada para servir de entrada nas sessões de desenvolvimento
> (Claude Code / superpowers skill).
>
> *"Atlas" é um codinome provisório — renomeie à vontade.*

---

## 1. Propósito

Um assistente pessoal que **roda no notebook (Linux, via systemd, sempre ligado)**,
usa o **Claude como motor de inteligência** e se comunica pelo **Telegram**.

Ele serve para:

- **Trackear** evolução física, cognitiva, estudos e leitura — com entrada
  super simples (mensagem curta no Telegram).
- **Organizar metas** e mostrar progresso.
- **Rodar rotinas plugáveis** que coletam dados, decidem se vale analisar e, só
  quando necessário, invocam o Claude para gerar insights.
- **Criar novas rotinas a partir de conversa**: você descreve a rotina pelo
  Telegram, o sistema invoca o Claude Code localmente e gera o código da rotina
  seguindo os padrões do próprio projeto.

O diferencial central não é o tracking — é o **meta-loop**: o sistema se expande a
si mesmo, gerando suas próprias rotinas via Claude Code.

---

## 2. Princípios de design

Estes princípios governam todas as decisões. Quando houver dúvida, eles decidem.

1. **Economia de token acima de tudo.** A IA é o recurso caro. A maioria das
   interações deve custar **zero token**. O LLM só é invocado quando há análise
   ou geração genuína a fazer.
2. **Script primeiro, agente só quando precisa.** Toda rotina faz o trabalho
   determinístico em código (coletar, comparar, formatar) e só sobe o Claude na
   fase de análise — e somente se houver algo que justifique.
3. **Agnóstico e plugável.** O motor não sabe o que é "academia" ou "Librera".
   Ele só sabe executar o ciclo de vida de uma rotina. Todo domínio é uma rotina.
4. **O repositório é o estado do sistema.** Rotinas são pastas versionadas em git.
   Adicionar uma rotina = adicionar uma pasta. Não há painel de configuração.
5. **Dois modos que nunca se misturam.** *Operação* (bot leve no dia a dia) e
   *desenvolvimento* (gerar rotinas via Claude Code) são sessões separadas.
6. **Interface desacoplada.** Telegram hoje; o canal é um adapter substituível.
7. **Simplicidade sobre completude.** Preferir o caminho mais simples que
   funciona no notebook de um usuário só, não a solução "enterprise".

---

## 3. Arquitetura geral

```
                          ┌──────────────────────────┐
        Celular  ◄──push──┤      Telegram (bot)       │
        (você)   ──cmd───►└────────────┬─────────────┘
                                       │ (long-poll, sem domínio/NAT)
                          ┌────────────▼─────────────┐
                          │     INTERFACE ADAPTER     │  envia / recebe
                          └────────────┬─────────────┘
                                       │
        ┌──────────────────────────────▼──────────────────────────────┐
        │                          MOTOR (core)                         │
        │  ┌──────────┐   ┌──────────────┐   ┌────────────────────┐    │
        │  │ ROTEADOR │──►│ EXECUTOR DE   │──►│ AGENDADOR          │    │
        │  │ (dispatch)│   │ ROTINAS       │   │ (cron / intervalos)│    │
        │  └──────────┘   └──────┬───────┘   └────────────────────┘    │
        │                        │                                      │
        │        ┌───────────────┼────────────────┐                    │
        │        ▼               ▼                ▼                     │
        │   ciclo de vida    BANCO (SQLite)   INVOCADOR Claude Code     │
        │   das rotinas      metas/dados      (`claude -p` local)       │
        └────────┬──────────────────────────────────┬──────────────────┘
                 │                                   │
        ┌────────▼─────────┐               ┌─────────▼──────────┐
        │  routines/        │               │  Sua assinatura    │
        │  (pastas plugáveis)│               │  Claude (Pro/Max)  │
        └───────────────────┘               └────────────────────┘
```

### Componentes

| Componente | Responsabilidade |
|---|---|
| **Interface Adapter** | Abstrai o canal. Implementa apenas `enviar` e `receber`. Telegram via long-poll. |
| **Roteador** | Recebe a mensagem e decide qual rotina/ação atende. Tenta casar por palavra-chave (0 IA) antes de qualquer coisa. |
| **Executor de Rotinas** | Roda o ciclo de vida de uma rotina (ver §8). |
| **Agendador** | Dispara rotinas por horário/intervalo (resumo diário, checkups, lembretes). |
| **Banco (SQLite)** | Estado persistente: atividades, metas, livros, histórico de execuções, orçamento de token. |
| **Invocador Claude Code** | Sobe instâncias `claude -p` locais com o prompt da rotina e captura a saída. |
| **routines/** | As rotinas, cada uma uma pasta plugável. É o estado expansível do sistema. |

---

## 4. Os dois loops do sistema

### Loop 1 — Operação (o bot no dia a dia)

Fluxo típico: você manda uma mensagem curta → o roteador identifica a rotina →
o executor roda o ciclo de vida → resposta/notificação volta pelo Telegram.

A maioria das interações de operação é **0 IA** (registrar treino, registrar
estudo, consultar status). A exceção é o **resumo diário**, a única rotina que
*sempre* usa o modelo.

### Loop 2 — Meta-loop (o sistema se expande)

O diferencial. Tem duas fases, em sessões separadas:

- **Planejamento (no Telegram):** você descreve em conversa a rotina nova — o que
  faz, frequência, gatilho, modelo, o que coleta. O bot pode fazer perguntas de
  esclarecimento até ter o spec completo.
- **Desenvolvimento (Claude Code no notebook):** o sistema invoca o `claude -p`
  passando (a) este documento / os contratos, (b) rotinas existentes como
  exemplo e (c) a descrição da rotina nova. O Claude Code gera a pasta completa
  seguindo os padrões do projeto. O bot notifica para você revisar e ativar.

Detalhe em §11.

---

## 5. Camadas de execução (o coração da economia de token)

Toda mensagem é resolvida pela camada mais barata capaz de atendê-la.

| Camada | Custo | Quando | Exemplos |
|---|---|---|---|
| **0 — código puro** | 0 token | Registrar, consultar, formatar, comparar | "fui na academia", "/status", resumo de metas, ler JSON do Librera |
| **1 — IA leve** | baixo (Haiku) | Quando a intenção é ambígua e palavra-chave não basta | "o que rolou essa semana?" sem comando claro |
| **2 — agente (Claude Code)** | alto | Quando a rotina precisa *agir* ou *analisar a fundo* | pull + avaliação do diff, resumo diário, geração de rotina |

**Meta de design:** ~80% das interações diárias resolvem na Camada 0. A Camada 2
é reservada e, sempre que possível, explícita ou agendada.

---

## 6. O roteador

Ordem de tentativa ao receber uma mensagem:

1. **Comando explícito** (`/status`, `/uso`, `/ativar X`) → ação direta. 0 IA.
2. **Gatilho de rotina por palavra-chave/alias** (cada rotina declara os seus) →
   dispara a rotina. 0 IA.
3. **Fallback de intenção (Camada 1):** se nada casou, uma chamada leve decide a
   qual rotina a mensagem se refere e extrai parâmetros.
4. **Sem correspondência:** resposta padrão pedindo esclarecimento.

O roteamento ser majoritariamente determinístico é o que mantém o custo baixo:
o LLM caro nunca é gasto só para entender "registra meu treino".

---

## 7. Motor de IA — Claude Code na assinatura

Toda chamada de IA acontece **instanciando o Claude Code localmente** (`claude -p`),
autenticado pelo seu login do Claude (Pro/Max). Implicações de projeto:

- **Sem billing por token de API** — o uso sai da assinatura (créditos de uso
  programático / Agent SDK).
- **Login precisa estar ativo** no notebook — é a credencial usada.
- **Concorrência limitada:** cada instância é pesada; o motor mantém uma fila e
  um teto de instâncias simultâneas.
- **Modelo por rotina:** cada rotina declara o modelo (`haiku` para tarefas
  leves, `sonnet` para análise, raramente `opus`).
- **Captura de uso:** a invocação registra tokens/custo retornados, para
  observabilidade e orçamento (§13).
- **Limite da assinatura:** rotinas pesadas demais podem esbarrar nos limites do
  Pro. Mitigação prevista: fila, modelos mais baratos, e fallback opcional.

Por causa do overhead de cada instância, o princípio **script-primeiro** é o que
viabiliza esse modelo economicamente.

---

## 8. O contrato da rotina — ciclo de vida

Toda rotina, sem exceção, é executada como uma sequência de fases. **Cada fase é
opcional.** Uma rotina de log simples usa só `trigger` + `store`; uma rotina de
análise usa todas.

| Fase | Função | Custo |
|---|---|---|
| **trigger** | O que dispara: palavras-chave, comando, e/ou agendamento. | 0 |
| **collect** | Script determinístico que reúne os dados crus (faz o pull e o diff, lê o JSON do Librera, lê o banco). | 0 |
| **gate** | Predicado barato que decide se vale prosseguir para a análise (ex.: "o diff está vazio?", "houve progresso?"). Se falhar, encerra com saída padrão. | 0 |
| **analyze** | Só se o gate passar: monta o prompt da rotina com os dados coletados e sobe o Claude Code. Única fase com custo de IA. | IA |
| **deliver** | Formata e envia pelo Telegram; persiste o resultado no banco. | 0 |

**Exemplo (rotina de pull):** `collect` faz git pull + calcula o diff → `gate`
verifica se houve mudança → `analyze` só roda se houve, gerando o insight →
`deliver` manda no Telegram e salva o run.

Esse ciclo é a abstração que torna o motor **agnóstico**: ele não sabe o que a
rotina faz, só sabe orquestrar as fases.

---

## 9. Anatomia de uma rotina (a pasta plugável)

Cada rotina é uma pasta auto-descoberta sob `routines/`. Estrutura conceitual:

```
routines/
  <nome-da-rotina>/
    routine.<config>     → metadados e configuração (declarativo)
    collect.<script>     → coleta de dados (opcional; 0 IA)
    prompt.<template>    → o prompt plugável da fase de análise (opcional)
```

### 9.1 Configuração da rotina (campos)

O arquivo de configuração descreve a rotina ao motor. Campos previstos:

| Campo | Descrição |
|---|---|
| `nome` | Identificador único da rotina. |
| `descricao` | O que ela faz (também usada como contexto no meta-loop). |
| `triggers` | Lista de palavras-chave/aliases que disparam por mensagem. |
| `agenda` | Quando rodar automaticamente (ex.: diário 21:00, sexta 18:00, a cada N min). |
| `modelo` | `none` \| `haiku` \| `sonnet` \| `opus` — qual modelo a fase de análise usa. |
| `gate` | Condição que habilita a análise (ex.: "houve mudança", "sempre"). |
| `timeout` | Tempo máximo da instância do Claude Code. |
| `budget_tokens` | Teto de tokens por execução (estoura → enfileira/avisa). |
| `store` | O que persistir no banco e em qual entidade. |
| `saida` | Para onde vai o resultado (Telegram, silencioso, etc.). |
| `ativa` | Liga/desliga sem remover a pasta. |

### 9.2 Contrato do `collect`

Fase determinística. Conceitualmente:

- **Recebe** um *contexto* com: data/hora atual, configuração da rotina, dados do
  **último run** dessa rotina, e acesso de leitura ao banco.
- **Devolve** um dicionário livre de dados crus. Esse dicionário (a) alimenta o
  template de prompt na fase de análise e (b) pode ser persistido.
- **Não usa IA.** É só Python (git, leitura de arquivo, requisição, consulta ao
  banco).

### 9.3 Contrato do `prompt` (template plugável)

- É o **prompt da fase de análise** — a "personalidade" da rotina.
- Recebe, por substituição, os campos devolvidos pelo `collect` (ex.: o diff, os
  commits, o progresso de leitura).
- O resultado renderizado é o que vai dentro do `claude -p`.
- Rotinas sem análise (log puro) não têm `prompt`.

**Resumo:** o motor é genérico; o que diferencia cada rotina vive no
`collect` (como obtém os dados) e no `prompt` (como os interpreta).

---

## 10. Domínios de tracking (rotinas built-in e suas UX)

Os domínios são apenas rotinas — mas são os de maior valor, então têm UX pensada.

### 10.1 Físico
- **Entrada:** mensagem curta — "perna hoje, agachamento 80kg 4x10".
- **Coleta:** extrai parâmetros por script (exercício, carga, séries); sem IA.
- **Saída imediata:** confirmação de uma linha.
- **Rotina semanal:** evolução de carga/volume/peso/sono (gráfico como imagem).

### 10.2 Cognitivo / Estudos
- **Entrada:** "estudei álgebra linear 1h30".
- **Coleta:** matéria + duração; sem IA.
- **Rotina semanal:** horas por área vs. meta.

### 10.3 Leitura (Librera)
- **Fonte:** o Librera sincroniza o estado da biblioteca em JSON (Drive/Dropbox).
- **Coleta:** lê o JSON do sync, compara com a última checagem, calcula página
  atual e % concluído por livro; **sem IA**.
- **Gate:** "houve progresso?" — se não, não notifica.
- **Saída automática:** "+X páginas em [livro] hoje" — você nem fala com o bot.
- **Análise opcional (sob demanda):** "o que revisar antes de seguir neste livro"
  sobe o Claude.

### 10.4 Metas (camada transversal — ver §12)

### 10.5 Resumo diário (a âncora — a única rotina que sempre usa IA)
- **Agenda:** fim do dia.
- **Coleta:** tudo que aconteceu hoje (treinos, estudo, leitura, metas, rotinas
  que rodaram).
- **Análise (Sonnet):** o que você fez, o que ficou pra trás, um insight sobre
  padrões, e a prévia de amanhã.
- **Saída:** notificação no Telegram.

### 10.6 Meta-loop (criação de rotinas — ver §11)

---

## 11. O meta-loop em detalhe (o diferencial)

### Fase 1 — Planejamento (Telegram)
Você conversa descrevendo a rotina: objetivo, frequência, gatilho, modelo, fontes
de dados. O bot esclarece dúvidas até ter um **spec da rotina** completo. Ao seu
comando ("cria"), passa para a fase 2.

### Fase 2 — Desenvolvimento (Claude Code local)
O motor invoca `claude -p` montando um prompt que contém **todo o contexto que o
Claude Code precisa para gerar código no padrão do projeto**:

1. **Os contratos** (este documento / a parte relevante): o ciclo de vida, os
   campos da config, os contratos de `collect` e `prompt`.
2. **Exemplos concretos:** 2–3 rotinas existentes bem-feitas. O Claude Code
   aprende o padrão vendo o que já existe.
3. **O esquema do banco:** o que pode ser consultado dentro de um `collect`.
4. **O spec da rotina nova** vindo da fase 1.

O Claude Code gera a pasta completa da rotina seguindo os contratos.

### Fase 3 — Revisão e ativação
O bot notifica: "rotina `X` gerada em `routines/X/` — revise e ative com
`/ativar X`". Você revisa no computador, ajusta se quiser, faz o commit, ativa.

### Efeito bola de neve
Quanto mais rotinas boas existirem, mais exemplos o Claude Code tem, e mais
rápido/preciso ele gera as próximas. O sistema fica **mais fácil de expandir com
o tempo**.

---

## 12. Sistema de metas (camada transversal)

Metas **não são uma rotina** — são a camada que dá significado às atividades.

- Cada registro de atividade (treino, estudo, página lida) pode alimentar uma ou
  mais metas.
- Uma meta tem: título, categoria, horizonte (curto/longo), alvo mensurável,
  progresso, prazo, status.
- O **checkup semanal** (rotina, montada por script, 0 IA) consolida tudo numa
  visão única: dias de academia vs. meta, horas de estudo vs. meta, progresso de
  leitura, e o quanto cada meta de prazo avançou.
- A IA só entra se você pedir interpretação ("estou no ritmo de bater a meta?").

---

## 13. Observabilidade e orçamento de token

Como economizar é objetivo explícito, vira parte do sistema:

- **Registro por execução:** cada run grava qual rotina, quando, resultado, e
  tokens/custo consumidos.
- **Teto por rotina:** `budget_tokens` na config; estouro enfileira ou pede
  confirmação.
- **Teto global:** limite diário/mensal de uso de IA.
- **Comando `/uso`:** relatório de consumo (hoje, semana, por rotina).
- **Transparência de camada:** o sistema sabe (e pode mostrar) quantas interações
  foram Camada 0 vs. 1 vs. 2.

---

## 14. Infraestrutura — notebook sempre ligado

- **Execução:** o motor roda como serviço `systemd` com reinício automático.
- **Nunca dormir:** mascarar os alvos de suspensão/hibernação do systemd.
- **Tampa fechada não suspende:** configurar o `logind` para ignorar o lid switch
  (na tomada e na bateria) e reiniciar o serviço de login.
- **Energia:** desativar suspensão automática nas configurações do ambiente.
- **Interface sem infra:** o Telegram via long-poll dispensa domínio, IP público,
  webhook e túnel — o notebook puxa as mensagens de dentro pra fora.
- **Evolução futura:** se o uso crescer, migrar o motor para um mini-PC ou VPS
  sempre ligado — sem mudar nada do desenho (a interface e as rotinas são iguais).

---

## 15. O repositório como fonte da verdade

- Todo o sistema vive num repositório git no notebook.
- **Rotinas = pastas versionadas.** Ativar/desativar, ajustar prompt, evoluir uma
  rotina é um commit.
- O banco (SQLite) é o estado *dinâmico* (dados); o repositório é o estado
  *estrutural* (o que o sistema é capaz de fazer).
- O meta-loop escreve novas pastas nesse repositório — por isso o sistema "se
  expande a si mesmo" de forma rastreável e reversível.

---

## 16. Interface plugável (não só as rotinas)

O canal de comunicação é um adapter, exatamente como as rotinas. Hoje: Telegram.
Trocar ou adicionar (ntfy, web dashboard local, etc.) é implementar `enviar` e
`receber` — o núcleo (roteador, ciclo de vida, Claude Code) não muda. Isso deixa
a porta aberta para, por exemplo, um painel web local com gráficos no futuro, sem
refazer nada.

---

## 17. Privacidade e segurança

- **Acesso restrito:** o bot só responde ao seu próprio ID no Telegram; qualquer
  outro remetente é ignorado.
- **Dados locais:** o SQLite e o repositório ficam no notebook.
- **IA:** o conteúdo enviado nas fases de análise vai para o Claude (via Claude
  Code) para processamento — relevante se alguma rotina lidar com dados sensíveis.
- **Segredos:** tokens (Telegram) e credenciais ficam fora do versionamento.

---

## 18. Decisões travadas

| Tema | Decisão |
|---|---|
| Interface | Bot do **Telegram** (long-poll, sem domínio), como adapter plugável. |
| Motor de IA | **Claude Code local** na assinatura (sem billing por token de API). |
| Padrão de rotina | **Script-primeiro, agente só quando precisa** (ciclo de vida §8). |
| Rotinas | **Pastas plugáveis** auto-descobertas; o repositório é o estado. |
| Modos | **Operação** e **desenvolvimento** (meta-loop) em sessões separadas. |
| Hospedagem | **Notebook Linux**, systemd, sem sleep. |
| Resumo diário | Rotina built-in, **única que sempre usa IA** (Sonnet). |
| Criação de rotina | **Meta-loop:** descrição no Telegram → geração via Claude Code. |

## 19. Em aberto (a decidir antes/durante o desenvolvimento)

- Teto de uso da assinatura Pro para rotinas pesadas (e se vale fallback).
- Formato exato do sync do Librera disponível no seu setup (Drive vs. Dropbox vs.
  arquivo local) — define o `collect` da rotina de leitura.
- Quais rotinas entram como built-in no core além do resumo diário e do meta-loop.
- Política de retenção/limpeza do histórico de runs no banco.

---

## 20. Ordem de construção sugerida

1. **O spec dos contratos** (este documento é a base) — a constituição que o
   Claude Code obedece ao gerar rotinas.
2. **O motor mínimo** — carregar rotinas, agendador, adapter do Telegram,
   invocador do Claude Code, banco.
3. **As duas rotinas built-in essenciais** — o **resumo diário** e o
   **meta-loop de criação de rotinas**.
4. **As rotinas de tracking** — físico, estudos, leitura (Librera), metas.
5. **Tudo o mais** — via meta-loop, a partir daqui.

---

## 21. Glossário

- **Rotina:** unidade plugável de comportamento; uma pasta sob `routines/` que o
  motor executa pelo ciclo de vida.
- **Ciclo de vida:** trigger → collect → gate → analyze → deliver.
- **Motor (core):** o runtime fixo (roteador, executor, agendador, adapter,
  invocador, banco). Não muda quando você adiciona rotinas.
- **Meta-loop:** o processo de criar rotinas novas a partir de conversa, via
  Claude Code.
- **Camada 0/1/2:** níveis de custo de execução (código puro / IA leve / agente).
- **Adapter:** implementação plugável de um canal de interface (Telegram, etc.).
- **Gate:** o predicado barato que decide se a fase de análise (IA) deve rodar.
