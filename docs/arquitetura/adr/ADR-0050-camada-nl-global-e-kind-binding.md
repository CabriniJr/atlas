---
titulo: ADR-0050 — Camada de linguagem natural global e Kind Binding
id: ADR-0050
status: aceito
versao: 0.1
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-07-13
substitui: —
substituido-por: —
---

# ADR-0050 — Camada de linguagem natural global e Kind `Binding`

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 0.1    | 2026-07-13 | Tech Lead | Proposta e aceite (brainstorm com o PO) | PO |

---

## Status
`aceito` — brainstorm concluído com o PO; segue para implementação.

## Contexto

O PO interage pelo Telegram e quer comandos **globais** em linguagem natural
(`progresso` de todos os ativos; nome solto busca em todos os kinds; `sync` de
todos os repos; mandar PDF → traduzir e receber de volta). O `torrent_cmd`
resolveu isso **hardcoded por kind** — o que viola P11 (tudo é objeto; capacidade
se declara por label+selector; coisa nova vira Kind novo). Precisamos de uma
camada genérica, data-driven, em vez de mais `if kind == ...` no roteador.

Documentos afetados: `constituicao.md` (P11), ADR-0049 (Torrent/conversa),
ADR-0030/0031 (Tradução), ADR-0038 (pool). Design detalhado:
`docs/superpowers/specs/2026-07-13-camada-nl-global-design.md`.

## Decisão

1. **Kind `Binding`** liga mensagem → ação: `spec.gatilho` (verbo | regex |
   nome-solto), `spec.acao` (`builtin` | `collect`), `spec.selector` (labels dos
   alvos), `spec.resposta` (agregação/header). Comportamentos são **recursos**
   (seed no boot, editáveis pela API), não código no roteador.
2. **Participação por label**: um recurso entra na conversa por
   `labels.interface = "telegram"`. Busca e ações de selector só enxergam recursos
   com o label. Retro-carimbo idempotente no boot (padrão `stamp_owner`).
3. **Ação = built-in ou collect registrada** — nunca shell arbitrário de mensagem
   (script-primeiro, P2; auto-execução a partir de mensagem é risco, fica no
   backlog com gate).
4. **Roteador genérico** `conversa.py` casa o gatilho, roda a ação sobre o
   selector, agrega e responde; `None` cai no roteador base. Cada kind expõe um
   **descritor** puro (`nome_exibicao`, `linha_progresso`) — único ponto que
   conhece o formato do kind.
5. **Torrent → cliente único**: um `qbittorrent-nox` com **fila nativa**
   (`QueueingSystemEnabled=true`, `MaxActiveDownloads=N`), substituindo o modelo de
   1 daemon/profile/porta por download e o `TorrentPool` em memória. Um loop
   monitor único dirige progresso/conclusão/integridade por infohash.
6. **Keep-awake**: o Atlas segura um `systemd-inhibit` de sleep enquanto roda.

## Alternativas consideradas
| Alternativa | Prós | Contras | Por que não |
|---|---|---|---|
| Hardcode dos verbos no roteador (estilo `torrent_cmd`) | Simples agora | Cada capacidade nova = código; viola P11 | Não escala, contra a constituição |
| Ação = shell arbitrário | Máxima flexibilidade | Auto-exec de mensagem = risco | Fica no backlog com gate |
| Manter N daemons de torrent | Já funciona | N processos/portas/profiles; desperdício | qBittorrent enfileira nativo num cliente só |

## Consequências
- **Positivas:** comando novo = criar um `Binding` (a IA cria pela API); roteador
  não cresce; torrent mais leve (1 processo); progresso/busca globais reusam os
  mesmos dados.
- **Negativas / custos:** um motor de binding + registry de ações + descritores a
  manter; refactor do torrent (risco no caminho de download real, mitigado por TDD
  e pelo `_esta_completo` já corrigido).
- **Impacto na constituição:** reforça P11 (novo Kind + label/selector); ADR-0049
  é parcialmente revisado (o `torrent_cmd` vira um `Binding`; o pool em memória sai).

## Pendências
- **Torrent cliente-único (decisão 5): DIFERIDO.** A camada NL, progresso global,
  busca, sync, tradução via Telegram e keep-awake foram entregues e testados
  (2026-07-13/14). O refactor do torrent para um `qbittorrent-nox` com fila nativa
  reescreve a orquestração de download (daemon compartilhado + monitor único) e só
  se valida com um download real — fica para um incremento com smoke test do PO,
  para não arriscar o caminho de download recém-corrigido (commit c794e49). O
  design está na spec; o modelo atual (1 daemon por download) segue funcionando.
- Ação = shell com gate de segurança (backlog).
- Selector de grupo de repos por label nomeado (por ora: todos).
- Ampliar a busca a outros kinds além de Torrent/Traducao/Repo/Doc.
