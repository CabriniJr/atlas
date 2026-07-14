---
titulo: ADR-0052 — Ownfoil (loja Tinfoil) em container Podman, exposto por Tailscale Funnel
id: ADR-0052
status: aceito
versao: 0.1
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-07-14
substitui: —
substituido-por: —
---

# ADR-0052 — Ownfoil (loja Tinfoil) em container Podman, exposto por Tailscale Funnel

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 0.1    | 2026-07-14 | Tech Lead | Proposta e aceite (PO decidiu exposição e servidor) | PO |

---

## Status
`aceito` — frente E da visão nuvem pessoal.

## Contexto

O PO quer instalar jogos no Nintendo Switch (via **Tinfoil**) **de qualquer lugar**,
servindo os ~22 GB de `~/Games/Switch`. Tinfoil não lê OneDrive nativamente e o
Switch normalmente não roda Tailscale — logo o servidor precisa de **endpoint HTTPS
público**. Decisões do PO no brainstorm (2026-07-14): exposição = **Funnel público +
auth forte**; servidor = **Ownfoil** (loja Tinfoil completa: login, catálogo com
capas, marca "já instalado").

Restrições verificadas: `podman 5.8.2` rootless OK (já roda o `atlas-qbt`, ADR-0051);
porta 8465 livre; Tailscale logado no nó `fedora.tail25c9d8.ts.net` (100.79.40.56),
mas **HTTPS/Funnel ainda não habilitado** no tailnet.

Design detalhado: `docs/superpowers/specs/2026-07-14-funnel-ownfoil-mcp-design.md`.

## Decisão

1. **Container `a1ex4/ownfoil`** (podman rootless), WebUI só em `127.0.0.1:8465`.
   Volumes com `:Z` (SELinux, como no ADR-0051): `~/Games/Switch`→`/games` (origem),
   `~/.local/share/atlas-ownfoil/{config,data}`→`/app/{config,data}`. `--userns=keep-id`
   para ler os jogos do host com dono correto.
2. **Auth forte:** admin user/senha via env de `secrets/ownfoil.env` (fora do git).
3. **Exposição pública por Tailscale Funnel** na porta **:443** do nó `fedora`
   (`tailscale serve`/`funnel`). Fonte no Tinfoil = `https://fedora.tail25c9d8.ts.net/`
   + credencial.
4. **Novo Kind `Ownfoil`** (P11) com supervisor único que garante o container e
   reporta status (up/down, nº de jogos, último acesso) ao `atlas_status` e ao Telegram.
5. Reusa as flags rootless/SELinux do `torrent/container.py` (helper comum se valer).

## Alternativas consideradas
| Alternativa | Prós | Contras | Por que não |
|---|---|---|---|
| Servidor de arquivos HTTPS simples | Leve | Sem capas/"já instalado"; auth manual; frágil p/ público | PO quer loja com auth forte |
| Só Tailnet (sem Funnel) | Nada exposto à internet | Switch não roda Tailscale → não acessa | Não atende "de qualquer lugar" |
| rclone-mount OneDrive + servir | Reusa a nuvem | Latência/cache em jogo de 14 GB; complexo | Servir o disco local é direto e rápido |

## Consequências
- **Positivas:** Tinfoil de qualquer rede com auth; reusa padrão de container do
  ADR-0051; status integrado ao Atlas via Kind.
- **Negativas / custos:** superfície pública (mitigada por auth do Ownfoil + só a
  porta do Funnel exposta); depende de o PO habilitar HTTPS/Funnel no admin console;
  jogos servidos do disco local (não libera espaço — isso é a frente D, parada).
- **Impacto na constituição:** novo Kind `Ownfoil` (P11, P3 rotina/plugável).
  Reforça P5 (reusa container já validado).

## Pendências
- Ação do PO: **DNS → Enable HTTPS certificates** e atributo **`funnel`** para o nó.
- Smoke test: subir container, logar, e instalar um jogo real no Switch de fora da rede.
- Confirmar `--userns` exato (uid interno do Ownfoil) no smoke, como no ADR-0051.
