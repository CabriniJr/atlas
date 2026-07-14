"""Ownfoil — loja Tinfoil self-hosted em container, exposta por Funnel (ADR-0052).

Kind ``Ownfoil``: serve os jogos de ``~/Games/Switch`` para o Nintendo Switch (via
**Tinfoil**) a partir de qualquer rede, com **auth forte**. Segue o padrão do client
de torrent em container (ADR-0051): **podman rootless**, WebUI só em ``127.0.0.1``
(o **Tailscale Funnel** faz a exposição pública), volumes com relabel SELinux
(``:Z``) e ``--userns=keep-id`` para ler o acervo do host com o dono correto.

Zero IA — é infraestrutura/script puro (P1: economia do recurso escasso).
"""

KIND = "Ownfoil"
