---
titulo: Spec — Contrato HTTP da API do Atlas
id: SPEC-API-HTTP
status: aprovado
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-17
---

# Spec — Contrato HTTP da API do Atlas

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-06-17 | Tech Lead | Criação | PO/PM |

> Implementa [ADR-0019](../arquitetura/adr/ADR-0019-interfaces-clientes-da-api.md).
> Este é o contrato que toda interface (web, Android, scripts) consome.

## Base e autenticação
- Prefixo: `/apis/atlas/v1`. Porta default `8080` (`ATLAS_API_PORT`).
- Auth: header `Authorization: Bearer <ATLAS_API_TOKEN>`. Sem token definido, a
  API aceita apenas loopback (127.0.0.1).
- CORS: `Access-Control-Allow-Origin: *`; métodos `GET,POST,PUT,DELETE,OPTIONS`.

## Endpoints
| Método | Caminho | Auth | Descrição |
|---|---|---|---|
| GET | `/health` | não | `{"status":"ok"}` |
| GET | `/` | não | landing mínima (HTML) |
| GET | `/apis/atlas/v1` | sim | `{<kind>: <count>}` |
| GET | `/apis/atlas/v1/<kind>` | sim | lista de recursos do kind |
| GET | `/apis/atlas/v1/<kind>/<name>` | sim | um recurso (ou 404) |
| PUT | `/apis/atlas/v1/<kind>/<name>` | sim | upsert; corpo `{labels, spec}` |
| DELETE | `/apis/atlas/v1/<kind>/<name>` | sim | remove (ou 404) |
| POST | `/apis/atlas/v1/_cmd` | sim | `{text}` → `{output}` (paridade Telegram) |
| POST | `/apis/atlas/v1/_run` | sim | `{routine}` → resultado da execução |
| POST | `/apis/atlas/v1/_insight` | sim | `{scope,name,model}` → insight IA |
| GET | `/apis/atlas/v1/_status` | sim | visão de status do sistema |
| GET | `/apis/atlas/v1/_complete?q=` | sim | sugestões de autocomplete |
| GET | `/apis/atlas/v1/_schema` | sim | metadata de UI por kind (forms + ações) |

## Formato do recurso
```json
{ "api_version": "atlas/v1", "kind": "...", "name": "...",
  "labels": {}, "spec": {}, "status": {},
  "criado_em": "...", "atualizado_em": "..." }
```
`status` é somente-leitura (escrito pelo motor). `PUT` aceita `labels` e `spec`.
A serialização HTTP é **flat** (não usa `metadata`).

## `/_schema`
```json
{ "kinds": { "<Kind>": { "meta": {"icon","desc"},
  "spec": [{"k","type","label","hint","opts?"}],
  "labels": [{"k","label","hint"}],
  "actions": [{"id","label","verbo","template"}] } } }
```
`verbo`: `cmd` (POST `/_cmd`), `run` (POST `/_run`), `insight` (POST `/_insight`).
