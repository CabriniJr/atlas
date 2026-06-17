---
titulo: Spec — Manifestos declarativos e loader `apply -f`
id: SPEC-MANIFESTOS
status: aprovado
versao: 1.0
dono: PO/PM
revisado-por: Tech Lead
atualizado-em: 2026-06-17
---

# Spec — Manifestos declarativos e loader `apply -f`

## Histórico de revisão
| Versão | Data       | Autor     | Mudança | Aprovado por |
|--------|------------|-----------|---------|--------------|
| 1.0    | 2026-06-17 | Tech Lead | Criação | PO/PM |

> Implementa [ADR-0018](../arquitetura/adr/ADR-0018-manifestos-e-apply-f.md).

## Formato
YAML multi-doc; um Resource por documento (`---`), shape flat:
```yaml
kind: Tracker        # obrigatório
name: peso           # obrigatório (slug kebab-case)
labels:              # opcional — use grupo=<g> para agrupar
  grupo: academia
spec:                # campos do kind (ver kinds.md)
  unit: kg
```
`status` é ignorado pelo loader (só o motor escreve status).

## Uso
```
python -m atlas apply -f manifests/academia.yaml \
  [--api-url http://127.0.0.1:8080] [--token T] [--dry-run]
```
- `--api-url`: default `ATLAS_API_URL` ou `http://127.0.0.1:8080`.
- `--token`: default `ATLAS_API_TOKEN`.
- `--dry-run`: valida e lista o que faria, sem chamar a API.
- Idempotente (upsert via `PUT`). Falha num objeto não interrompe os demais;
  o processo sai com código ≠0 se algum falhou.

## Manifestos seed
`manifests/{academia,saude,produtividade}.yaml` — Trackers/Goal/Timer agrupados
por `labels.grupo`. As rotinas `routines/check-<grupo>/` (coletar-por-label) fazem
o check-in diário; nascem `ativa=false` (ligue com `/ativar check-<grupo>`).
