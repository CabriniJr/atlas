---
titulo: ADR-0053 — Interface MCP remota do Atlas (Streamable HTTP + OAuth 2.1) via Funnel
id: ADR-0053
status: aceito
versao: 0.1
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-07-14
substitui: —
substituido-por: —
---

# ADR-0053 — Interface MCP remota do Atlas (Streamable HTTP + OAuth 2.1) via Funnel

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 0.1    | 2026-07-14 | Tech Lead | Proposta e aceite (PO decidiu auth e superfície) | PO |

---

## Status
`aceito` — frente F da visão nuvem pessoal.

## Contexto

O PO quer conversar comigo pelo **app do Claude no celular** e, dali, acionar o Atlas
(status, torrent, sync, futuramente instalar jogo). O app adiciona **servidores MCP
remotos** como **conectores personalizados** (URL HTTPS pública + auth). É a "cara"
por chat da automação que o Atlas já faz pelo Telegram — e a interface natural da
futura Inbox mágica (frente D, parada).

Decisões do PO no brainstorm (2026-07-14): **OAuth 2.1 completo** (padrão do MCP
remoto, adequado a endpoint público); superfície v1 = **status, torrent, push,
instalar_jogo**. O endpoint público **reaproveita o Tailscale Funnel** da frente E
(ADR-0052), em porta distinta.

Design detalhado: `docs/superpowers/specs/2026-07-14-funnel-ownfoil-mcp-design.md`.

## Decisão

1. **Módulo `src/atlas/mcp/`**: servidor **MCP remoto Streamable HTTP** com **OAuth 2.1**
   (registro dinâmico de cliente). Confirmar o fluxo exato exigido pelo app na
   implementação e usar biblioteca pronta (SDK MCP Python / FastMCP). Segredos em
   `secrets/mcp.env`.
2. **Exposição** pela porta **:8443** do Funnel no nó `fedora`; endpoint `…:8443/mcp`
   adicionado no app como conector.
3. **Ferramentas v1** como wrappers finos, sem lógica de negócio nova:
   - `atlas_status` — jobs/filas/torrents/disco/último sync (core + sqlite). **Real.**
   - `enfileirar_torrent(link)` — reusa o Kind Torrent (ADR-0051). **Real.**
   - `push_nuvem` — dispara `~/bin/onedrive-push.sh`. **Real.**
   - `instalar_jogo(nome, local|nuvem)` — **stub** (responde "frente D pendente");
     assinatura reservada para plugar quando D voltar.
4. Roda no processo `python -m atlas` (rota/servidor ASGI extra na porta 8787) ou
   subprocesso supervisionado — decidir no plano conforme o web atual do Atlas.

## Alternativas consideradas
| Alternativa | Prós | Contras | Por que não |
|---|---|---|---|
| Token bearer (FastMCP) | Rápido de montar | Menos aderente ao que o app espera p/ remoto | PO escolheu OAuth 2.1 |
| Só bot Telegram (sem MCP) | Já existe | Não é chat com o Claude no app | PO quer acionar pelo app do Claude |
| MCP local (stdio) | Sem exposição | Não funciona remoto pelo celular | Precisa ser remoto/público |

## Consequências
- **Positivas:** Atlas acionável pelo app do Claude de qualquer lugar; reusa o Funnel
  da frente E; ferramentas reaproveitam código existente.
- **Negativas / custos:** OAuth 2.1 é a parte mais trabalhosa (registro dinâmico);
  conector remoto exige plano pago no app; endpoint público (mitigado por OAuth +
  porta única do Funnel); `instalar_jogo` fica stub até a frente D.
- **Impacto na constituição:** nova **interface** (P3 plugável) sobre a API de
  objetos; não altera o motor. Segredos fora do repo (regra do "NUNCA fazer").

## Pendências
- Confirmar o fluxo OAuth exato aceito pelo app do Claude (registro dinâmico) e a
  disponibilidade de conector remoto no plano do PO.
- Definir hospedagem (in-process vs subprocesso) após inspecionar `src/atlas/dashboard`.
- `instalar_jogo` real depende da frente D (Inbox mágica).
