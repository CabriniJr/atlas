---
titulo: ADR-0012 — Empacotamento e deploy via Docker
id: ADR-0012
status: aceito
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-16
substitui: —
substituido-por: —
---

# ADR-0012 — Empacotamento e deploy via Docker

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-06-16 | Tech Lead | Aceito  | PO/PM        |

---

## Status
`aceito`.

## Contexto
O bot precisa ficar **sempre ligado** e voltar sozinho após reboots. A decisão
original (§14, decisão #6) era notebook + systemd. O PO/PM pediu uma imagem
**Docker** para o bot rodar continuamente e, no futuro, migrar sem mudanças para
um host sempre ligado.

**Limite físico (registrado para evitar mal-entendido):** um container roda
enquanto a **máquina está ligada**. Não há como manter o bot no ar com o
computador desligado. Para 24/7 real, a mesma imagem roda num host sempre ligado.

**Host de produção escolhido: Raspberry Pi.** O PO/PM tem um Raspberry Pi que
ficará sempre ligado — é o destino de produção do projeto. O empacotamento Docker
existe justamente para essa migração sem fricção.

## Decisão
- **Imagem Docker** (`Dockerfile`, base `python:3.12-slim`, usuário não-root)
  rodando `python -m atlas`.
- **`docker-compose.yml`** com `restart: always`. Com o Docker habilitado no boot
  (`systemctl enable --now docker`), o bot volta sozinho a cada reinício.
- **Persistência:** o SQLite vive num **volume** (`./data:/data`), sobrevivendo a
  rebuild. `ATLAS_DB_PATH=/data/atlas.sqlite`.
- **Sem portas expostas:** long-poll é saída-pra-fora; não há inbound.
- **Segredos via `.env`** (env_file), nunca na imagem (reforçado por `.dockerignore`).
- **Portabilidade:** a mesma imagem roda no notebook (dev) e num host sempre
  ligado (prod) sem alteração — complementa, não revoga, a opção systemd.
- **ARM / Raspberry Pi:** a base `python:3.12-slim` é multi-arch (arm64/armv7); a
  imagem builda **nativamente no Pi**, sem cross-build. Guia de migração em
  [`../../../resumo/raspberry-pi.md`](../../../resumo/raspberry-pi.md).

## Alternativas consideradas
| Alternativa | Prós | Contras | Por que não (como única) |
|---|---|---|---|
| Só systemd no notebook | Simples, sem Docker | Menos portátil; deps no host | Mantida como opção; Docker é mais portátil |
| Kubernetes | Escala/auto-heal | Complexidade enorme p/ 1 usuário | Fere P7 |

## Consequências
- **Positivas:** reinício automático, ambiente reproduzível, migração trivial para
  VPS/mini-PC, dados persistentes.
- **Negativas:** exige Docker + daemon no boot; não roda com a máquina desligada
  (precisa de host sempre ligado para 24/7 real).
- **Impacto na constituição:** decisão #6 passa a citar Docker como empacotamento
  preferido (systemd permanece válido).

## Pendências
- Imagem multi-stage / healthcheck (quando houver endpoint de saúde) — backlog.
- ~~Escolha do host always-on~~ → **resolvido: Raspberry Pi.**
- **Esclarecimento importante:** os **modelos do Claude rodam na nuvem da
  Anthropic**, nunca no host. O `claude -p` é apenas um **cliente leve** (Claude
  Code/Node) que chama o modelo pela rede. Portanto o Pi **não** precisa de poder
  de compute para "rodar modelo" — precisa só rodar o cliente. Requisitos reais a
  verificar em E1-05: (1) Claude Code roda em **arm64**, (2) **login ativo** no
  Pi, (3) **rede**. Footprint de RAM/CPU é modesto (é I/O de rede, não inferência
  local).
