# Design — Camada de linguagem natural global (Kind `Binding`)

- **Data:** 2026-07-13
- **Autor:** Claude (Opus) — PO: humano
- **ADR:** ADR-0050 (registra a decisão de arquitetura)
- **Status:** aprovado (brainstorm), em implementação

## Problema

O PO interage com o Atlas pelo Telegram e quer, em **linguagem natural** e de forma
**global** (não por recurso):

1. **`progresso`** → devolve TODOS os itens ativos que fazem sentido: torrents
   baixando, traduções traduzindo, repos sincronizando.
2. **nome solto** ("astral chain", "kubernetes", "atlas") → **busca em todos os
   kinds** relevantes e devolve os matches agrupados, cada um com a ação natural.
3. **`sync` / "sincroniza os repos"** → sincroniza **todos** os repos e devolve um
   resumo agregado, com **header = nº de commits novos** + o que mudou por repo.
4. **Tradução via Telegram**: mandar um PDF → o Atlas traduz e, ao concluir,
   **envia o PDF traduzido**; e "me manda/puxa <nome>" envia um já traduzido.
5. **Keep-awake**: a máquina não suspende **enquanto o Atlas roda**.
6. **Torrent**: um **único** cliente `qbittorrent-nox` com **fila nativa** (hoje
   sobe 1 daemon + profile + porta por download).

Princípio do PO (constituição P11): **nada disso é hardcoded por kind**. Uma
capacidade se declara por **label + selector**, e "coisa nova" vira **Kind novo**.

## Arquitetura — data-driven, resource-declarada

### Kind `Binding` (novo)

Um recurso `Binding` liga uma **mensagem** a uma **ação**. Não há verbo hardcoded
no roteador: os comportamentos são recursos `Binding` (seed criados no boot,
editáveis pela API como qualquer recurso).

```
Binding/<name>
  spec:
    gatilho:
      tipo: "verbo" | "regex" | "nome-solto"     # nome-solto = fallback de busca
      valor: "progresso" | "^sync\\b" | ...        # verbo(s) ou padrão
      aliases: ["progresso","status","como tá"]    # p/ tipo=verbo
    acao:
      tipo: "builtin" | "collect"
      nome: "progresso-global" | "buscar" | "enviar" | "repo-sync" | "traduzir-pdf"
    selector: { interface: "telegram" }            # labels dos recursos-alvo
    resposta:
      agregar: true                                # junta resultado de N alvos
      header: "commits"                            # header especial (ex. contagem)
  status: { ultimo_disparo, ultimo_resultado_resumo }
  labels: { owner, scope }
```

### Participação por label

Um recurso entra na conversa por carregar **`labels.interface = "telegram"`**. A
busca por nome e as ações de selector só enxergam recursos com esse label — o
roteador nunca conhece uma lista de kinds. Torrent, Traducao, Repo e Doc passam a
carimbar `interface=telegram` ao serem criados; recursos existentes são
retro-carimbados no boot (idempotente, como `stamp_owner`).

### Roteador genérico — `src/atlas/conversa.py`

`responder_conversa(texto, store, ctx) -> str | None`:
1. Carrega os `Binding` do dono.
2. **Casa o gatilho** na ordem: `verbo` (match exato/alias, 1ª palavra) →
   `regex` → `nome-solto` (fallback, se nada casou e há texto).
3. **Executa a ação** sobre os recursos do `selector` (via um registry de ações).
4. **Agrega** e formata a resposta (header opcional).
5. Devolve `None` se nenhum `Binding` casou → cai no roteador base (`handler`).

Interceptado em `app.processar_update` **antes** do roteador base (no lugar/junto
do `responder_torrent` atual, que é absorvido por um `Binding`).

### Registry de ações — `src/atlas/conversa/acoes.py`

Ações **built-in** e **collects** são as únicas coisas executáveis (decisão:
sem shell arbitrário). Uma ação é `fn(store, ctx, alvos, args) -> ResultadoAcao`
onde `ResultadoAcao = {texto, arquivos: [caminho], ...}`. Built-ins iniciais:

- `progresso-global` — para cada alvo, uma linha de progresso do kind (torrent:
  %/velocidade/seeds; traducao: pág x/y; repo: sincronizando). Só ativos.
- `buscar` — substring no "nome de exibição" de cada alvo; agrupa por kind; cada
  match traz a ação natural sugerida.
- `enviar` — resolve o match de Traducao pronto e devolve `arquivos=[saida]`
  (ou texto+caminho se > limite do Telegram).
- `collect:<nome>` — roda uma rotina/collect registrada (ex. `repo-sync`,
  `traduzir-pdf`) para cada alvo do selector; agrega os `_saida`.

Cada kind expõe um **descritor** (`conversa/descritores.py`) com funções puras:
`nome_exibicao(resource)`, `linha_progresso(resource) | None` (None = não ativo).
É o único ponto que conhece o formato de cada kind — pequeno e testável. Novos
kinds plugam adicionando um descritor + o label.

## Repo-sync em linguagem natural

Seed `Binding/sync`: gatilho verbo `sync`/"sincroniza (os repos)"; ação
`collect:repo-sync`; selector `{ kind: "Repo", interface: "telegram" }` (todos os
repos). Roda o collect `repo-sync` de cada Repo (reusa `rotinas/repo_sync`),
coleta os `resumo` e devolve:

```
🔄 sync de N repos — <total> commits novos
  • repo-a: 4 commits (main +3, feat/x +1)
  • repo-b: sem novidades
  ...
```

Header = soma de commits novos entre todos. Roda em background (thread), com uma
notificação de progresso curta e o resumo final.

## Tradução via Telegram

- `telegram.py`: **`enviar_documento(chat_id, caminho, legenda="")`** — `sendDocument`
  multipart (urllib direto, como `baixar_arquivo`). Best-effort.
- **Receber PDF** (`app._normalizar` já extrai `document`): roteia anexo por
  extensão — **`.pdf` → tradução**, **`.torrent` → torrent**. Salva em
  `data/pdfs/<nome>.pdf`, cria/atualiza `Traducao/<label>` com `spec.origem` +
  `labels.interface=telegram`, dispara o collect `traduzir-pdf`.
- **Auto-enviar ao concluir**: o dispatch de tradução (thread) no `finally` lê o
  status; `fase=="pronto"` e não `parcial` → `enviar_documento(saida)`; se
  `parcial/pausado` → avisa. Se `saida` > **49 MB** (limite do bot ~50 MB) →
  texto com o caminho local em vez do arquivo (`preparar_envio`).
- **"me manda/puxa <nome>"**: seed `Binding` ação `enviar` sobre matches Traducao.

## Keep-awake

`src/atlas/keepawake.py`: em `app.run()`, segura um inibidor
`systemd-inhibit --what=sleep:idle:handle-lid-switch --mode=block --who=Atlas
--why="jobs Atlas" sleep infinity` como subprocesso, encerrado no shutdown. Sem
`systemd-inhibit` → loga e segue (ADR-0006). Também `scripts/keep-awake.sh` avulso.
Bloqueia suspensão/idle/fechar-tampa; **não** bloqueia desligar de propósito.

## Torrent — cliente único com fila nativa (refactor)

Hoje: `pool_torrent` (slots em memória) + 1 `QBittorrentNox` por download (profile
por infohash, porta por download). Novo:

- **Um** `qbittorrent-nox` compartilhado: profile fixo (`~/.local/share/atlas-torrent/cliente`),
  uma porta WebUI. Subido sob demanda (lazy) e mantido vivo.
- Config passa a usar a **fila nativa**: `QueueingSystemEnabled=true`,
  `MaxActiveDownloads=N`, `MaxActiveTorrents=N` (N do `ATLAS_TORRENT_MAX_CONCURRENT`).
  Segurança preservada (encriptação, anônimo, no-seed, kill-switch, sem port-forward).
- Adicionar torrent = `POST /torrents/add` (multipart .torrent + savepath). O
  qBittorrent enfileira; baixa até `N`, resto = `queuedDL`.
- **Um** loop monitor (thread única): poll de `/torrents/info`, atualiza cada
  `Torrent` (progresso, estado), dispara marcos/conclusão, roda integridade nos
  recém-concluídos (usa `_esta_completo` — espera o move, já corrigido) e para o
  seed por torrent.
- `TorrentPool` (slots do Atlas) **sai**; "baixando vs fila" deriva do estado do
  cliente (`downloading/stalledDL` vs `queuedDL`). A máquina de estados do recurso
  (`aguardando→baixando→concluido`) fica.
- Encaixa no `progresso-global` (mesmo `/torrents/info`) e na `buscar`.

Compatibilidade: recursos `Torrent` existentes seguem válidos; o boot recarrega
os pendentes no cliente único (retomam do parcial em disco).

## Isolamento / módulos

- `conversa.py` — roteador (casa gatilho, executa, agrega). Puro + store.
- `conversa/acoes.py` — registry de ações built-in + collect runner.
- `conversa/descritores.py` — por-kind: nome_exibicao + linha_progresso (puro).
- `binding.py` (ou `rotinas`/serviço) — CRUD/seed dos `Binding` + carimbo de label.
- `telegram.py` — `enviar_documento`.
- `keepawake.py` — inibidor.
- `torrent/cliente.py` — cliente único (substitui o modelo N-daemons).
- `app.py` — wiring (rota de anexo, intercept do roteador, dispatch tradução).

## Testes (TDD)

- Router: gatilho verbo/regex/nome-solto; `None` em msg alheia; ordem de match.
- Descritores: nome_exibicao/linha_progresso por kind (puro).
- Ações: progresso-global agrega só ativos; buscar agrupa por kind; enviar
  arquivo vs caminho (>49 MB); collect runner agrega `_saida`.
- Binding seed idempotente; carimbo de label idempotente.
- repo-sync agregado: header de commits soma; formato por repo.
- Telegram `enviar_documento`: multipart montado (transporte fake).
- Roteamento `.pdf` vs `.torrent`.
- Torrent cliente único: add enfileira; monitor atualiza N recursos; integridade
  por hash; deriva fila/baixando do estado.
- keepawake: monta o comando certo; ausência de systemd-inhibit não quebra.

## Fora de escopo (backlog)

- Ação = shell arbitrário (precisa gate de segurança — proposto p/ depois).
- Selector de **grupo** de repos por label nomeado (por ora: todos).
- Busca em kinds além de Torrent/Traducao/Repo/Doc.
- Dividir/compactar PDF grande (por ora: avisa + caminho local).
