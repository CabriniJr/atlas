#!/usr/bin/env bash
# Rebuild + recria o container atlas-dev com Podman (sem Docker).
# Uso:  ./scripts/podman-dev.sh
# Pré-requisito: Podman instalado + .env na raiz.
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "✗ Falta .env na raiz do projeto."
  echo "  cp resumo/.env.example .env  (e preencha os valores)"
  exit 1
fi

mkdir -p data

echo "==> build da imagem"
podman build -t atlas:latest .

echo "==> parando e removendo atlas-dev (se existir)"
podman stop  atlas-dev 2>/dev/null || true
podman rm    atlas-dev 2>/dev/null || true

echo "==> subindo atlas-dev"
# Credencial git p/ repos privados via podman secret (montado legível pelo
# usuário do container em /run/secrets/git-credentials). Mais seguro que bind-mount.
CRED_ARG=()
if [ -f secrets/git-credentials ]; then
  podman secret rm atlas-git-cred 2>/dev/null || true
  podman secret create atlas-git-cred secrets/git-credentials >/dev/null
  CRED_ARG=(--secret atlas-git-cred,target=git-credentials,mode=0444)
  echo "    (credencial git via podman secret para repos privados)"
else
  echo "    (sem secrets/git-credentials — repo-sync só clona repos públicos)"
fi
podman run -d \
  --name atlas-dev \
  --restart always \
  -p 8080:8080 \
  -v "$(pwd)/data":/data:z \
  "${CRED_ARG[@]}" \
  --env-file .env \
  -e ATLAS_DB_PATH=/data/atlas.sqlite \
  -e ATLAS_API_PORT=8080 \
  -e ATLAS_ROUTINES_DIR=/app/routines \
  -e ATLAS_DOCS_DIR=/app/docs \
  localhost/atlas:latest

echo ""
sleep 3
podman logs --tail 6 atlas-dev

cat <<'EOF'

✓ atlas-dev no ar em http://127.0.0.1:8080
  Logs ao vivo:   podman logs -f atlas-dev
  Parar:          podman stop atlas-dev
  Rebuild:        ./scripts/podman-dev.sh
EOF
