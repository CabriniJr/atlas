#!/usr/bin/env bash
# Deploy pull-based do Atlas (CD local — ver docs/processos/politica-de-desenvolvimento.md).
#
#   scripts/deploy.sh dev    → checkout main (HEAD) → testes → restart atlas-dev
#   scripts/deploy.sh prod   → checkout última tag  → testes → restart atlas-prod
#
# Nenhum segredo sai da máquina: o notebook PUXA do GitHub e reinicia o serviço.
# Os units systemd (atlas-dev/atlas-prod) e o poller são tarefas de infra (backlog E4).
set -euo pipefail

ENV="${1:-}"
case "$ENV" in
  dev)  REF="origin/main"; SERVICE="atlas-dev" ;;
  prod) REF=""           ; SERVICE="atlas-prod" ;;
  *) echo "uso: $0 {dev|prod}" >&2; exit 2 ;;
esac

echo "==> [$ENV] buscando atualizações"
git fetch --tags --prune origin

if [ "$ENV" = "prod" ]; then
  REF="$(git describe --tags "$(git rev-list --tags --max-count=1)")"
  echo "==> [prod] última tag: $REF"
fi

echo "==> [$ENV] checkout $REF"
git checkout --quiet --detach "$REF"

echo "==> [$ENV] dependências"
if [ -f pyproject.toml ]; then
  python -m pip install --quiet -e . || true
fi

echo "==> [$ENV] smoke test"
if [ -d tests ]; then
  ATLAS_DISABLE_AI=1 pytest -q
else
  echo "    (sem testes ainda — smoke pulado)"
fi

echo "==> [$ENV] reiniciando $SERVICE"
if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files | grep -q "$SERVICE"; then
  sudo systemctl restart "$SERVICE"
  echo "==> [$ENV] OK em $REF"
else
  echo "    (serviço $SERVICE ainda não instalado — ver backlog E4)"
fi
