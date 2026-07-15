---
titulo: ADR-0054 — Auth do dashboard por dispositivo na Tailnet, com pareamento via Telegram
id: ADR-0054
status: aceito
versao: 0.1
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-07-14
substitui: —
substituido-por: —
---

# ADR-0054 — Auth do dashboard por dispositivo na Tailnet, com pareamento via Telegram

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 0.1    | 2026-07-14 | Tech Lead | Proposta e aceite (PO decidiu exposição e mecanismo) | PO |

---

## Status
`aceito` — parte da visão nuvem pessoal ([[atlas-nuvem-pessoal-onedrive-switch]]);
habilita o Atlas "hosteado" com Ownfoil (ADR-0052) e MCP (ADR-0053).

## Contexto

O PO quer o Atlas sempre no ar e acessível de fora, mas o **dashboard é o control
plane** (roda código, agentes, Claude Code, commita, reinicia a instância). Expor isso
no Funnel público seria perigoso — e há um agravante concreto: o Funnel entrega os
requests a partir de `127.0.0.1`, e `api.py` (retrocompat E0-05) dá **admin a qualquer
conexão de loopback** quando `ATLAS_API_TOKEN` não está setado. Ou seja, publicar o
dashboard como está daria **admin à internet inteira**.

Decisões do PO: (1) o dashboard fica **só na Tailnet** (não vai pro Funnel); (2) a auth
é **por dispositivo** — 3 aparelhos autorizados, salvos pelo Atlas; (3) o registro é por
**pareamento via Telegram** ("eu logo, você salva").

## Decisão

1. **Dashboard só na Tailnet.** Não usa `tailscale serve`/`funnel` — acesso direto por
   `http://<ip-tailscale>:8080` (o WireGuard já cifra). Isso é essencial porque o serve
   esconderia o IP do aparelho atrás do localhost e **quebraria a auth por dispositivo**.
2. **Identidade por IP Tailscale.** O identificador estável de cada aparelho é seu IP
   Tailscale (`100.64.0.0/10` v4 ou `fd7a:115c:a1e0::/48` v6), lido de `client_address`.
   `api.py` **não confia em `X-Forwarded-For`** (seria bypass).
3. **Kind `Dispositivo`** (P11): um recurso por aparelho autorizado (`spec.ip`/`nome`).
   `_identity()` concede admin quando o IP do request casa um `Dispositivo`. Teto de **3**.
4. **Pareamento via Telegram.** Aparelho da tailnet não-pareado que abre o dash recebe
   uma **página com um código de 6 dígitos** (TTL 5 min, uso único, em memória). O dono
   envia `/autorizar <código> [nome]` no Telegram e o IP é salvo. `/dispositivos` lista,
   `/revogar <ip|nome>` remove. O código vive num **singleton de processo**
   (`dispositivos._REGISTRO`) compartilhado entre o `api.py` (gera) e o handler (confirma).
5. **Retrocompat preservada.** Loopback e `ATLAS_API_TOKEN`/sessão seguem funcionando;
   o caminho de dispositivo é aditivo. Ownfoil (:443) e MCP (:8443) continuam públicos no
   Funnel — o dashboard é o único que fica restrito à tailnet.

## Alternativas consideradas
| Alternativa | Prós | Contras | Por que não |
|---|---|---|---|
| Dashboard público no Funnel + token | Acessa de qualquer navegador | Control plane exposto; token único como muro; bug de auth = comprometimento total | Risco alto demais pro que o dash faz |
| `tailscale serve` (headers de identidade) | HTTPS na tailnet | Backend vê localhost → perde o IP do aparelho; identifica usuário, não dispositivo | PO quer por dispositivo (3 aparelhos) |
| Login por senha (já existe) | Pronto | PO quer sem digitar senha; não é "por dispositivo" | Não atende o pedido |

## Consequências
- **Positivas:** control plane fora da internet pública; auth simples e por aparelho;
  pareamento aprovado por canal já confiável (Telegram); fecha o bypass de loopback ao
  não expor o dash no Funnel.
- **Negativas / custos:** exige app Tailscale nos aparelhos do PO; IP Tailscale muda se o
  aparelho sair/reentrar na tailnet (basta re-parear); pareamentos pendentes são em
  memória (somem no restart — é só recarregar a página).
- **Impacto na constituição:** novo Kind `Dispositivo` (P11); estende a auth do E0-05/
  ADR-0027 com um caminho de identidade por dispositivo. Não altera o motor.

## Pendências
- Setar `ATLAS_API_TOKEN` no `.env` como cinto-e-suspensório (mesmo sem Funnel no dash).
- Smoke real do PO: abrir o dash em cada aparelho da tailnet e parear via Telegram.
- Opcional: bloquear no `api.py` fontes fora da faixa tailnet/loopback (hoje o bind é
  `0.0.0.0`; a LAN alcança a porta mas cai em 401 por não ser dispositivo pareado).
