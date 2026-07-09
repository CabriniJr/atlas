---
titulo: ADR-0049 — Kind Torrent (download headless) + camada de conversa stateful no Telegram
id: ADR-0049
status: aceito
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-07-09
substitui: —
substituido-por: —
---

# ADR-0049 — Kind Torrent (download headless) + camada de conversa stateful no Telegram

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 0.1    | 2026-07-09 | Tech Lead | Proposta | — |
| 1.0    | 2026-07-09 | Tech Lead | **Aprovada pelo PO** (design no brainstorm: motor `qbittorrent-nox`, sem VPN por ora, destino `~/Documents/torrent`, entrega completa) | PO/PM |
| 1.1    | 2026-07-09 | Tech Lead | **Extensão (aprovada pelo PO):** fila + concorrência (cap 3), persistência (retoma após restart) e verificação de integridade pós-download por magic header ("invalid pfs0") | PO/PM |

---

## Status
`aceito` — PO aprovou o design no brainstorm ("faça a entrega").

## Contexto
O PO quer **baixar torrents mandando o `.torrent` pelo Telegram**, com o download
acontecendo **no computador dele** (o desktop local, que tem GUI/flatpak e o
destino `~/Documents/torrent`), e ser avisado quando terminar. Requisitos
explícitos do PO:

1. Manda o `.torrent` como anexo no Telegram.
2. O Atlas **verifica** o torrent e **pergunta** se pode instalar (fluxo
   conversacional, não só um comando disparado às cegas).
3. O PO consegue **pedir o progresso** a qualquer momento.
4. Recebe uma **notificação quando o download termina**.
5. O download é **via CLI headless** — "para não depender do aplicativo abrir no
   computador".

Duas restrições da base batem de frente com isso:

- **O Atlas descarta anexos.** `app.py::_normalizar` só normaliza mensagens com
  `text`; um `document` (arquivo) é ignorado. Não há como receber o `.torrent`.
- **O handler é stateless** (P: texto entra → texto sai; `handler.responder`).
  Não há memória de "estou esperando o PO confirmar tal coisa". O fluxo
  "verifiquei → **pergunto** → espero *sim/não*" exige estado de conversa.

O PO já tinha, de uma sessão anterior, dois scripts em `~/bin/`:
`torrent-scan.py` (varredura de segurança de metadados `.torrent` em bencode
puro, devolve nível de risco 0/1/2) e `torrent-safe` (orquestra scan → kill-switch
VPN → download → não-semear → fecha). O `torrent-safe`, porém, **abre a GUI do
qBittorrent** (`flatpak run`), exatamente o que o requisito 5 proíbe.

Princípios em jogo: **P11** (tudo é objeto; novo tipo de coisa → novo Kind),
**economia do recurso escasso** (isto é **zero IA** — scan e download são script
puro), **script-primeiro** (ADR-0019: interfaces são clientes; o motor é o
script), e **ADR-0006** (resiliência: job sobrevive a restart).

## Decisão

### 1. Novo **Kind `Torrent`** (P11)
Um download é um job longo, com estado que sobrevive a restart — modelado como
recurso, igual a `Traducao`.

- **`spec`**: `arquivo` (path do `.torrent` salvo), `nome`, `infohash`,
  `destino` (default `~/Documents/torrent`), `vpn` (iface ou vazio),
  `permitir_sem_vpn` (default `true` — ver Pendências), `semear` (default
  `false`), `origem_chat` (chat_id p/ notificar).
- **`status`**: `fase`, `risco` (0/1/2), `resumo` (nome, tamanho, nº arquivos,
  alertas do scan), `progresso_pct`, `velocidade`, `seeds`, `mensagem`,
  `criado_em`, `concluido_em`.
- **Fases**: `verificando → aguardando_confirmacao → baixando → concluido |
  erro | recusado | cancelado`.
- O `name` do recurso é o `infohash` (estável, dedupe natural).

### 2. Recepção de anexo no Telegram (aditivo)
- `Update` ganha um campo opcional `documento` (`{file_id, file_name}`).
- `_normalizar` passa a aceitar mensagens com `document` (além de `text`).
- `TelegramAdapter` ganha `baixar_arquivo(file_id) -> bytes` (`getFile` +
  download). Só o dono (`allowed_user_id`) é atendido — como já é hoje.
- O `.torrent` é salvo em `data/torrents/<infohash>.torrent`.

### 3. Verificação = `torrent-scan.py` **vendorizado** para o repo (P4)
A lógica do scanner do PO é portada para `src/atlas/torrent/scan.py` (bencode
puro, regras de risco, infohash) como funções importáveis e testáveis — o
repositório é o estado do sistema, não `~/bin`. Devolve `ResultadoScan`
(nome, infohash, tamanho, nº arquivos, nível de risco, alertas).

### 4. Camada de **conversa stateful** (a "melhoria da interação via Telegram")
Aditiva sobre o roteador stateless. Um novo router `responder_torrent` é
consultado no `handler.responder` **antes** da barreira de comando desconhecido:

- Um texto solto (`sim`/`não`/`progresso`/`cancelar`) é resolvido contra o
  **estado pendente** — o `Torrent` do dono em `aguardando_confirmacao` (ou
  `baixando`, para `progresso`/`cancelar`). O estado vive **no recurso**, não em
  memória de processo: sobrevive a restart e aparece no dashboard.
- Risco alto (nível 2) exige confirmação forte (`SIM` maiúsculo), espelhando o
  `torrent-safe`.
- Comandos slash continuam funcionando (`/torrents` lista, `/torrent <id>`
  detalha). Nada do roteamento existente muda de comportamento.

### 5. Download **headless** via `qbittorrent-nox` (`src/atlas/torrent/download.py`)
Porta a lógica do `torrent-safe` trocando `flatpak run` por `qbittorrent-nox` —
**sem janela**. Preserva a config de segurança do PO (encriptação forçada, modo
anônimo, sem port-forward, sem semear por default, kill-switch de VPN quando uma
iface é exigida) e o **loop de progresso via WebUI API** (`/api/v2/...`), já
usado pelo script. Roda em **thread daemon** (padrão do `_disparar_traducao_thread`),
atualiza `status` a cada ~2s, e ao chegar a 100% **para o P2P, encerra o nox** e
grava `concluido_em`. Dependência de sistema: `qbittorrent-nox` (instalar uma vez
via gerenciador de pacotes).

### 6. Progresso sob demanda + notificação de término
- `progresso` / `/torrent <id>` leem `status` (zero efeito colateral).
- Ao concluir/errar, o job chama um **notificador** (callback capturado no
  disparo, análogo ao `montar_disparo` da tradução) que envia a mensagem final no
  chat de origem (`✅ baixado: <nome> em <destino>` / `❌ falhou: <motivo>`).

### 7. Paridade CLI (requisito "torrent via cli")
`python -m atlas torrent <arquivo.torrent> [--sim] [--dir <p>] [--vpn <iface> |
--no-vpn]` roda **o mesmo caminho** (scan → confirma → download) sem Telegram.

### 8. Operação
- Roda na **instância local** (o desktop do PO): é onde estão o destino, o
  flatpak e o motor. O bot do Telegram só admite **um** long-poller por token, então
  usar isto implica a instância local deter o bot ("reativar a interface").
- **Recuperação de órfão no boot** (ADR-0043): um `Torrent` preso em `baixando`
  por um restart volta para `aguardando_confirmacao` (o P2P não sobrevive ao
  processo; o PO reconfirma) — evita estado fantasma.

### 9. Fila + concorrência + persistência + integridade (v1.1)
- **Fila/concorrência** (`torrent/pool.py`, padrão do ADR-0038): até
  `ATLAS_TORRENT_MAX_CONCURRENT` (**default 3**) baixam juntos; o resto entra na
  **fase `fila`** (FIFO) e é despachado sozinho quando um slot libera
  (`ao_concluir_slot`). Cada download concorrente recebe **porta WebUI própria**
  (`alocar_porta`, a partir de 8099) e **profile por-infohash** (`profile_para`) —
  sem isso, duas instâncias do nox colidiriam na porta/sessão.
- **Persistência** (`retomar_no_boot`): o `.torrent` fica salvo e os dados
  parciais no destino, então um Torrent que estava `baixando`/`fila` **retoma
  sozinho** após restart (o nox recontinua do parcial em disco), respeitando o
  teto do pool. Substitui a postura v1.0 de "voltar para confirmação".
- **Integridade pós-download** (`torrent/integridade.py`): ao chegar a 100%,
  valida o *magic header* de cada arquivo de tipo conhecido (`.nsp`/`.nsz`→`PFS0`,
  `.xci`→`HEAD`@0x100, `.zip`→`PK`, `.pdf`→`%PDF`, `.7z`, `.iso`, `.xz`, …). O
  torrent baixa bit-a-bit conferido (hash por peça), mas isso não pega conteúdo
  **fake/corrompido na fonte** (o erro "invalid pfs0"). Falha → `status.integridade
  = falha` + notificação; **mantém os arquivos** (decisão do PO: avisar, não apagar).

## Alternativas consideradas
| Alternativa | Prós | Contras | Por que não |
|---|---|---|---|
| Manter `torrent-safe` com `flatpak run` (GUI) | Zero mudança no motor | Abre janela; inviável headless; requisito 5 proíbe | Rejeitada pelo requisito explícito |
| Motor `aria2c` | Ultraleve, headless nativo | Perde toda a config de segurança do PO (kill-switch, anônimo); mais reescrita | Descartada no brainstorm |
| Motor `transmission-daemon` | Headless, RPC de progresso | Config de segurança diferente da do PO; não reusa o script | Descartada no brainstorm |
| Conversa em memória de processo | Simples | Não sobrevive a restart; invisível no dashboard; fere P11/ADR-0006 | Estado mora no recurso |
| Ad-hoc (comando dispara e some) | Menos código | Sem verificação/confirmação, sem progresso, sem Kind — fere o pedido e P11 | Rejeitada |

## Consequências
- **Positivas:** primeiro fluxo **conversacional stateful** do Atlas, reusável por
  outros Kinds; download seguro e headless reusando o script já validado pelo PO;
  visibilidade no dashboard e sobrevivência a restart de graça (padrão `Traducao`).
- **Negativas / custos:** o Atlas passa a receber e escrever **arquivos binários
  vindos do Telegram** (novo vetor — mitigado: só o dono, tamanho limitado, e o
  scan roda antes de qualquer download); dependência de sistema nova
  (`qbittorrent-nox`); a feature só é útil na instância que tem o motor e o
  destino (local), não na Rasp headless de propósito geral.
- **Impacto na constituição:** nenhuma decisão da constituição muda. Adiciona um
  Kind e uma capacidade de anexo — ambos aditivos. Atualiza `backlog.md` e o
  `api_schema` (meta do Kind, ADR-0017).

## Pendências
- **VPN desligada por ora** (decisão do PO): `permitir_sem_vpn` default `true`. O
  kill-switch continua no código e liga quando `vpn` é preenchido; reavaliar o
  default quando o PO tiver uma VPN no desktop.
- **Antivírus opcional** no conteúdo baixado (`torrent-scan.py --clam`) fica fora
  desta entrega — sugerido como follow-up no backlog.
- **Múltiplos torrents simultâneos**: entregue na v1.1 (fila + concorrência cap 3
  + persistência). Falta apenas escalar o teto pela UI/Telegram (o pool já é
  escalável em runtime; falta o endpoint/comando).
