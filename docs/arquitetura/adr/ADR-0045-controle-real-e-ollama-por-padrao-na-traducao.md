---
titulo: ADR-0045 — Controle real (pausar/recomeçar/re-refinar) e Ollama como motor padrão na tradução
id: ADR-0045
status: aceito
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-07-02
substitui: —
substituido-por: —
---

# ADR-0045 — Controle real e Ollama como motor padrão na tradução

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-07-02 | Tech Lead | Bug de fallback silencioso p/ Claude + controles reais (pausar/recomeçar/re-refinar) + Ollama como padrão | PO/PM |

---

## Status
`aceito` — implementado.

## Contexto

A instância caiu num crash-loop por um WIP quebrado (deixado a meio, sem o
`def` de uma função) numa sessão anterior de desenvolvimento via Ollama —
revertido antes de qualquer coisa aqui (`git checkout` nos dois arquivos
afetados, sem perda: era código não commitado).

Ao investigar por que uma tradução configurada com `motor="ollama"` ficava
pausando com "tokens acabaram" (mensagem que só fazia sentido para Claude), a
causa raiz apareceu em `atlas.ia.invocar()`: o fallback bidirecional (ADR-0022)
troca de motor **silenciosamente** quando o motor pedido falha — incluindo
`ollama → claude`. Numa tradução de livro inteiro (centenas de páginas, ADR-0031),
isso significa: (1) tom/estilo inconsistente entre blocos traduzidos por motores
diferentes sem o usuário saber; (2) cota do Claude sendo queimada às escondidas
numa tarefa que o usuário deliberadamente configurou para rodar 100% local
("preciso que traduz usando ollama"); (3) quando o Claude *também* falha (users
tem plano limitado), o job pausa com uma mensagem que parece ser sobre Claude
mesmo com `spec.motor=ollama`, confundindo o diagnóstico.

Ao mesmo tempo, o PO pediu dois reforços de UX que faltavam na tela de
`Traducao`: controle real do job em andamento ("conseguir pausar, recomeçar,
re-refinar") e Ollama como escolha padrão/prioritária ("a seleção padrão e de
maior insistência precisa ser o ollama").

## Decisão

1. **`atlas.ia.invocar()` ganha `fallback: bool = True`** — `False` propaga a
   falha do motor pedido sem tentar o outro. Default `True` preserva o
   comportamento de todo o resto do sistema (ex.: `agente_ollama`/dev-agent
   continuam com a rede de segurança bidirecional do ADR-0022, que ali é
   desejada).
2. **Tradução sempre chama com `fallback=False`** — `traduzir_pdf.py` embrulha
   `invocar` em `_invocar_sem_fallback_de_motor`, usado como `invocar_fn` do
   pipeline. O motor de `Traducao.spec.motor` é respeitado à risca; falhas
   (timeout ou erro) continuam caindo no mecanismo de retry/pausa existente
   (ADR-0039), só que sem trocar de motor no meio do livro.
3. **Mensagem de pausa por escassez deixa de assumir Claude** — "pausado
   (tokens acabaram)" virou "pausado (falha em `{motor}`)", refletindo o motor
   real configurado.
4. **`ConfigTraducao.motor` e o default do spec passam de `"claude"` para
   `"ollama"`** (dataclass, UI — dropdown e select do form genérico) — Ollama
   local é grátis e é o que o PO tem em abundância; Claude continua disponível
   trocando o campo.
5. **Controle real do job em andamento (ADR-0045):**
   - **Pausar** (`POST /_traduzir_pausar`): marca `status.pausar_solicitado`;
     o loop sequencial de página (`_processar_paginas_sequencial`) checa entre
     páginas e para com `motivo_pausa="manual"` — resumível como qualquer outra
     pausa, mas **sem** `retoma_em`/`retoma_collect` (ADR-0035): não retoma
     sozinho, só o botão "Retomar agora" (mesmo `/_traduzir` de sempre).
     Pendência: só o loop `paralelismo=1` honra a pausa (o modo paralelo,
     ADR-0039, despacha todas as páginas de uma vez ao `ThreadPoolExecutor`).
   - **Recomeçar do zero** (`POST /_traduzir_recomecar`): apaga o arquivo de
     cache inteiro (MT bruta + refinado) e dispara `/_traduzir` de novo — para
     quando o resultado ficou ruim e vale pagar tudo de novo.
   - **Re-refinar** (`POST /_traduzir_rerefinar`): abre o PDF, recalcula a
     chave de cache de cada bloco e remove **só** a entrada refinada
     (`CacheTraducao.remover`), preservando a MT bruta (`raw:` — namespace
     hash separado, ADR-0031) — útil depois de trocar `agente_refino`/modelo e
     querer um refino melhor sem repagar a parte mais cara (a MT).
   - UI (`traducao.js`): botão "⏸ Pausar" no toolbar (visível só rodando) +
     "🔁 Recomeçar do zero"/"♻️ Re-refinar" nos estados pronto/parcial/pausado.

## Alternativas consideradas

| Alternativa | Prós | Contras | Veredito |
|---|---|---|---|
| Desligar o fallback bidirecional globalmente (default `False` em `invocar()`) | um só lugar pra mudar | quebra a rede de segurança que o dev-agent (`agente_ollama`) e outras chamadas genéricas de `invocar()` querem manter | rejeitada |
| "Re-refinar" apagando o cache inteiro (como "recomeçar") | mais simples de implementar | repaga a MT bruta (a parte mais lenta/cara) por nada — o pedido era só melhorar o refino | rejeitada |
| Pausa via `SIGSTOP`/cancelamento de thread | pararia instantaneamente, inclusive no meio de uma chamada de IA | mata o processo/thread sem checkpoint limpo; API não expõe isso hoje | rejeitada — pausa checada **entre páginas** (checkpoint já existe por página, ADR-0031) |

## Consequências

- **Positivas:** tradução com `motor=ollama` não queima cota do Claude nem
  mistura estilo/tom no meio do livro; usuário tem controle real de um job
  longo (pausar, recomeçar, refinar de novo) sem precisar mexer em arquivo/DB
  direto; Ollama passa a ser o caminho de menor atrito (padrão).
- **Negativas / custos:** pausa manual só funciona com `paralelismo=1` (a
  maioria dos jobs de tradução hoje); "recomeçar do zero" é destrutivo
  (irreversível) — mitigado com `confirm()` na UI antes de chamar a API.
- **Impacto na constituição:** estende ADR-0022 (fallback deixa de ser
  incondicional — agora tem uma saída), ADR-0031 (cache ganha um terceiro modo
  de invalidação seletiva, além de get/put) e ADR-0035 (pausa não-automática
  reusa o mesmo campo `fase="pausado"`, só sem os campos de retomada).

## Pendências
- Pausa manual não é honrada no loop paralelo (`paralelismo > 1`,
  `pool_global.max_concorrente`) — só no sequencial.
- Sem cancelamento de uma chamada de IA já em voo (a pausa só vale *entre*
  páginas/lotes, nunca no meio de uma chamada de rede).
- `Agente/tradutor-fidelidade` (live) tinha `provider="gemma4"` — nome que não
  bate com nenhum `LLMProvider` — corrigido para `provider="ollama-local"`
  diretamente via API (dado, não código).
