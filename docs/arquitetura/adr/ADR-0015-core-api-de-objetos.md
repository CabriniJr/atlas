---
titulo: ADR-0015 — Core como API de objetos (estilo Kubernetes)
id: ADR-0015
status: aceito
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-16
substitui: —
substituido-por: —
---

# ADR-0015 — Core como API de objetos (estilo Kubernetes)

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-06-16 | Tech Lead | Aceito (prioridade máxima) | PO/PM |

---

## Status
`aceito` — **prioridade máxima**.

## Contexto
O Atlas cresceu com comandos **ad-hoc por domínio**: `/idea`, `/track`,
`/routines`, `/alarm`, `/run`… Cada tipo tem verbos próprios, parsing próprio e
formato de saída próprio. Isso não escala: cada novo domínio reescreve CRUD,
listagem e detalhe do zero, e a UX fica inconsistente.

O PO/PM definiu a direção (captada como ideia pelo próprio bot):

> "A api que é o backend, o motor central, quero no estilo da API do Kubernetes,
> onde tudo é objeto e posso dar **describe** em tudo, posso usar os **mesmos
> comandos** para tudo."

Além disso, o Telegram **não basta como UI**. O backend precisa virar uma **API
central** consumida por **múltiplas interfaces** (Telegram agora; uma **web app**
hospedada no Vercel depois), todas falando a mesma linguagem de objetos.

## Decisão
Adotar um **modelo de objetos uniforme** (estilo Kubernetes) como o **core** do
Atlas. Tudo é um **Resource**; verbos uniformes valem para qualquer **kind**.

### 1. Modelo de objeto (Resource)
Todo recurso tem a mesma forma:

```
apiVersion: atlas/v1
kind:       Routine | Tracker | Alarm | Idea | Goal | Activity | Run | ...
metadata:   { name, labels{}, criado_em, atualizado_em }
spec:       { ...estado desejado/config... }   # o que o usuário define
status:     { ...estado observado... }         # o que o sistema preenche
```

- `name` é único **dentro do kind** (`(kind, name)` é a chave).
- `spec` = intenção do usuário; `status` = preenchido pelo motor (P3: agnóstico —
  o store não conhece domínio, só objetos).

### 2. Verbos uniformes (valem para todo kind)
`get` · `list` · `describe` · `create` · `apply` · `patch` · `delete`.
Os **mesmos comandos** operam qualquer kind — no chat e na API HTTP.

| Verbo | Telegram (futuro unificado) | HTTP |
|---|---|---|
| list | `/get <kind>` | `GET /apis/atlas/v1/<kind>` |
| get/describe | `/describe <kind> <name>` | `GET /apis/atlas/v1/<kind>/<name>` |
| create | `/create <kind> <name> ...` | `POST /apis/atlas/v1/<kind>` |
| apply | `/apply <kind> <name> ...` | `PUT /apis/atlas/v1/<kind>/<name>` |
| delete | `/delete <kind> <name>` | `DELETE /apis/atlas/v1/<kind>/<name>` |

> Os comandos específicos atuais (`/track`, `/routines`…) **permanecem como
> atalhos** (açúcar sintático) sobre os verbos uniformes — não há ruptura de UX.

### 3. Camadas (a "cebola")
```
        Interfaces (adapters)
   ┌──────────────┬──────────────┐
   │  Telegram    │   Web (HTTP) │      ← clientes do core
   └──────┬───────┴──────┬───────┘
          │              │
   ┌──────▼──────────────▼───────┐
   │   API HTTP (motor central)  │      ← REST de objetos (atlas/v1)
   ├─────────────────────────────┤
   │  Verbos (get/apply/delete…) │      ← lógica uniforme
   ├─────────────────────────────┤
   │  ResourceStore (SQLite)     │      ← persistência genérica de objetos
   └─────────────────────────────┘
```

- **Core puro, zero dependências:** `Resource`, `ResourceStore` e os verbos são
  Python puro, testáveis sem rede (P7).
- **HTTP é um adapter** como o Telegram (P6 — plugável). MVP usa a stdlib
  (`http.server`); trocar por um framework depois **não afeta o core**.
- **Web app (Vercel)** consome a API HTTP — não fala com o banco direto.

### 4. Armazenamento
Uma tabela genérica `resources(kind, name, api_version, labels_json, spec_json,
status_json, criado_em, atualizado_em)`, PK `(kind, name)`. Domínio mora no JSON
(coerente com ADR-0002 / P3). As tabelas atuais migram para o modelo de objetos
**incrementalmente** (sem big-bang; ver Consequências).

## Alternativas consideradas
| Alternativa | Prós | Contras | Veredito |
|---|---|---|---|
| Manter comandos ad-hoc | Nada a mudar | Não escala; UX inconsistente | Rejeitada |
| ORM/REST por entidade (1 tabela+rota por tipo) | Familiar | Reescreve CRUD por tipo; acoplado | Rejeitada (fere P3) |
| **Objeto uniforme K8s-like** | 1 modelo, N kinds; describe em tudo; agnóstico | Abstração a mais; migração gradual | **Escolhida** |

## Consequências
- **Positivas:** um só CRUD para todos os tipos; UX uniforme; `describe` em tudo;
  novas features viram "um novo kind", não um novo subsistema; API pronta para web.
- **Negativas:** camada de abstração nova; migração das tabelas legadas exige
  cuidado (feita por kind, com testes, sem quebrar o bot em produção).
- **Constituição:** evolui a decisão de arquitetura — o **core é uma API de
  objetos**; interfaces (Telegram/Web) são **adapters**. Reforça P3 (agnóstico) e
  "o repositório/DB é o estado" (agora explicitamente como objetos).

## Plano incremental (não-quebra)
1. **Core de objetos** (este passo): `Resource` + `ResourceStore` + verbos (TDD),
   tabela `resources` aditiva. Não toca tabelas existentes.
2. **API HTTP** (stdlib) expondo os verbos sobre o store.
3. **Migrar kinds** um a um (Idea, Tracker, Alarm, Routine…) para o store,
   mantendo os atalhos atuais funcionando.
4. **Telegram** passa a falar com os verbos (adapter fino).
5. **Web app (Vercel)** consome a API.

## Pendências
- **Conectividade Vercel → backend doméstico** (Pi atrás de NAT): exigirá túnel
  (Cloudflare Tunnel/ngrok) ou expor a API com auth. Vira ADR de deploy próprio.
- **AuthN/Z da API** (hoje o Telegram filtra por `user_id`; a HTTP precisará de
  token). Definir antes de expor a API.
- Estratégia de **migração** das tabelas legadas para `resources` (por kind).
- Versionamento da API (`atlas/v1`) e compatibilidade.
