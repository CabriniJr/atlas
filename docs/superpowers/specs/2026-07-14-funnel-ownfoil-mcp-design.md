---
titulo: Design — Exposição pública (Tailscale Funnel), Ownfoil e MCP do Atlas
status: aprovado
versao: 0.1
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-07-14
adrs: ADR-0052 (Ownfoil/Funnel), ADR-0053 (MCP OAuth)
---

# Design — Nuvem pessoal, parte 2: Tinfoil de qualquer lugar + interface MCP

## Histórico de revisão
| Versão | Data       | Autor     | Mudança                          | Aprovado por |
|--------|------------|-----------|----------------------------------|--------------|
| 0.1    | 2026-07-14 | Tech Lead | Design inicial (E+F) aprovado    | PO           |

---

## 1. Contexto e objetivo

Continuação da visão **nuvem pessoal** ([[atlas-nuvem-pessoal-onedrive-switch]]).
As frentes A (reorg local), B (upload rclone) e a reorg da nuvem (C) estão **feitas**.
A frente **D (Inbox mágica)** foi **parada de propósito** pelo PO (ideia preservada,
fora de escopo agora). Este design cobre as duas frentes em foco:

- **E — Tinfoil de qualquer lugar:** servir os ~22 GB de `~/Games/Switch` para o
  Nintendo Switch a partir de qualquer rede, com auth forte.
- **F — Interface MCP:** o PO quer conversar comigo pelo app do Claude no celular e
  acionar o Atlas. Expor o Atlas como **servidor MCP remoto**, adicionado como
  **conector personalizado** no app.

Ambas dependem de expor serviços à internet pública com segurança. Decisão do PO
(brainstorm 2026-07-14): **Funnel público + auth forte**, **Ownfoil** como loja, e
**OAuth 2.1** para o MCP.

## 2. Fundação compartilhada — Tailscale Funnel

Um único nó, `fedora.tail25c9d8.ts.net` (100.79.40.56), expõe **dois** serviços.
O Funnel só libera as portas **443, 8443, 10000**; usamos duas delas em vez de
roteamento por caminho (evita quebrar prefixos de asset do Ownfoil e mantém as URLs
limpas):

| Porta pública (Funnel) | Serviço            | Backend local        |
|------------------------|--------------------|----------------------|
| `:443`                 | Ownfoil (Tinfoil)  | `127.0.0.1:8465`     |
| `:8443`                | MCP do Atlas       | `127.0.0.1:8787`     |

Config via `tailscale serve` (roteia porta→backend) + `tailscale funnel` (torna
público). Ex.: `tailscale funnel --bg --https=443 127.0.0.1:8465` e
`tailscale funnel --bg --https=8443 127.0.0.1:8787`.

**Pré-requisitos (ações do PO no admin console, uma vez):**
1. **DNS → Enable HTTPS certificates** (sem isso não há cert TLS; Funnel recusa —
   verificado: `HTTPS cert support is not enabled/configured for your tailnet`).
2. Habilitar o atributo **`funnel`** para o nó `fedora` na policy (Access Controls).

Um script `scripts/funnel_setup.sh` aplica a config de serve/funnel de forma
idempotente e imprime o passo-a-passo do admin console se detectar cert ausente.

## 3. Frente E — Ownfoil (ADR-0052)

Segue o padrão já provado do **Kind Torrent em container** (ADR-0051): container
**podman rootless**, com as mesmas cautelas de SELinux/userns do Fedora.

- **Imagem:** `a1ex4/ownfoil` (loja Tinfoil self-hosted).
- **Porta:** publicada só em `127.0.0.1:8465` (o Funnel faz a exposição pública).
- **Volumes** (com `:Z` p/ SELinux, como no torrent):
  - `~/Games/Switch` → `/games` (leitura; catálogo de origem)
  - `~/.local/share/atlas-ownfoil/config` → `/app/config`
  - `~/.local/share/atlas-ownfoil/data`   → `/app/data`
- **userns:** `--userns=keep-id` (ou `keep-id:uid=...` conforme o uid interno do
  Ownfoil) para ler os jogos do host com o dono correto — confirmar no smoke test.
- **Auth forte:** admin user/senha via env (`USER_ADMIN_NAME` / `USER_ADMIN_PASSWORD`),
  lidos de `secrets/ownfoil.env` (fora do git). Ownfoil exige login para servir o shop.
- **No Switch:** fonte Tinfoil = `https://fedora.tail25c9d8.ts.net/` + credencial
  (Tinfoil suporta HTTP basic/URL auth na configuração de source).

**Integração Atlas — novo Kind `Ownfoil` (P11):** um recurso `Ownfoil` na API de
objetos, com um **supervisor único** (à la monitor do torrent) que: sobe/garante o
container, expõe status (up/down, nº de jogos servidos, último acesso) para o
`atlas_status`, e reporta no Telegram. Reusa `torrent/container.py::montar_run_args`
como referência de flags rootless/SELinux (extrair helper comum se valer).

## 4. Frente F — MCP do Atlas (ADR-0053)

Módulo novo `src/atlas/mcp/`. Servidor **MCP remoto Streamable HTTP** com **OAuth 2.1**
(registro dinâmico de cliente — o que o app do Claude exige para conector remoto;
confirmar o fluxo exato na implementação e usar biblioteca pronta, ex. o suporte de
auth do SDK MCP Python / FastMCP).

- **Endpoint:** `…:8443/mcp`, adicionado no app como conector personalizado.
- **Auth:** OAuth 2.1; segredos/chaves em `secrets/mcp.env` (fora do git). Só o PO
  autoriza.
- **Ferramentas v1** (wrappers finos sobre o que já existe — sem lógica de negócio nova):

  | Ferramenta            | O que faz                                            | Reusa            | Status v1 |
  |-----------------------|------------------------------------------------------|------------------|-----------|
  | `atlas_status`        | jobs/filas/torrents/disco/último sync                | core + sqlite    | ✅ real   |
  | `enfileirar_torrent`  | adiciona magnet/link ao qBittorrent e acompanha      | Kind Torrent     | ✅ real   |
  | `push_nuvem`          | dispara `~/bin/onedrive-push.sh` com status          | script pronto    | ✅ real   |
  | `instalar_jogo(local\|nuvem)` | roteia/instala jogo; se nuvem sobe e libera  | **frente D**     | ⏸️ stub   |

  `instalar_jogo` responde "frente D pendente" no v1 e pluga quando D voltar — a
  assinatura já fica definida para não quebrar o conector depois.

- **Onde roda:** dentro do processo `python -m atlas` (mesma app), numa rota/servidor
  ASGI adicional na porta 8787, ou como subprocesso supervisionado. Decidir no plano
  conforme o servidor web atual do Atlas (verificar `src/atlas/dashboard`).

## 5. Segurança

- Tudo público passa por auth própria: **Ownfoil** (basic/login) e **MCP** (OAuth 2.1).
- **Cofre Pessoal** do OneDrive permanece intocado (rclone não escreve nele).
- Segredos em `~/atlas/secrets/*.env`, nunca no git (`.gitignore` já cobre `secrets/`
  — confirmar).
- Funnel expõe **só** as portas configuradas; WebUIs continuam bind em `127.0.0.1`.

## 6. Faseamento (entrega incremental, testar antes de seguir)

1. **Fundação Funnel** — `funnel_setup.sh` + ações do PO no admin console; validar
   que `tailscale funnel status` mostra os dois serviços com HTTPS.
2. **Ownfoil (E)** — Kind + container; smoke test: subir, logar, e **instalar um jogo
   real no Switch** via Tinfoil de fora da rede.
3. **MCP (F)** — módulo + OAuth; smoke test: adicionar conector no app do celular e
   rodar `atlas_status`, `enfileirar_torrent`, `push_nuvem`.

## 7. Fora de escopo / pendências

- **Frente D (Inbox mágica):** parada; assinatura de `instalar_jogo` já reservada.
- Kill-switch de VPN dentro dos containers (backlog, herdado do ADR-0051).
- Métricas/observabilidade além do `atlas_status` básico.
