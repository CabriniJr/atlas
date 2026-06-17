#!/usr/bin/env bash
# atlasctl — CLI básica de operação do Atlas (container local).
#
# O código do bot é EMBUTIDO na imagem (Dockerfile), então "atualizar" exige
# rebuild + recriar o container — não basta um restart. O SQLite vive no volume
# `atlas-data` e sobrevive a rebuilds.
#
# Uso:
#   scripts/atlasctl.sh atualizar   # rebuild da imagem + recria o container (pega código novo)
#   scripts/atlasctl.sh build       # só rebuild da imagem
#   scripts/atlasctl.sh restart     # restart do container (NÃO pega código novo)
#   scripts/atlasctl.sh logs        # segue os logs
#   scripts/atlasctl.sh status      # estado do container
#   scripts/atlasctl.sh parar       # remove o container (volume de dados fica)
set -euo pipefail

cd "$(dirname "$0")/.."

IMG="atlas:latest"
NAME="atlas"
VOL="atlas-data"
API_PORT="${ATLAS_API_PORT:-8080}"

# Engine: prefere podman; cai para docker.
if command -v podman >/dev/null 2>&1; then
  ENGINE="podman"
elif command -v docker >/dev/null 2>&1; then
  ENGINE="docker"
else
  echo "✗ Nem podman nem docker encontrados." >&2
  exit 1
fi

_build() {
  echo "==> build ($ENGINE) $IMG"
  "$ENGINE" build -t "$IMG" .
}

_recriar() {
  [ -f .env ] || { echo "✗ Falta .env (TELEGRAM_TOKEN + ATLAS_ALLOWED_USER_ID)." >&2; exit 1; }
  echo "==> recriando container '$NAME'"
  "$ENGINE" rm -f "$NAME" >/dev/null 2>&1 || true
  # :Z corrige contexto SELinux para Podman rootless no Fedora/RHEL
  "$ENGINE" run -d --name "$NAME" --restart=always \
    --env-file .env -p "${API_PORT}:${API_PORT}" \
    -v "${VOL}:/data:Z" "$IMG" >/dev/null
  sleep 1
  "$ENGINE" ps --filter "name=$NAME" --format '{{.Names}}  {{.Status}}  {{.Image}}'
  echo "--- últimos logs ---"
  "$ENGINE" logs --tail 5 "$NAME" 2>&1 || true
}

case "${1:-}" in
  atualizar|update) _build; _recriar ;;
  build)            _build ;;
  restart)          "$ENGINE" restart "$NAME"; "$ENGINE" ps --filter "name=$NAME" ;;
  logs)             "$ENGINE" logs -f --tail 50 "$NAME" ;;
  status)           "$ENGINE" ps -a --filter "name=$NAME" ;;
  parar|stop)       "$ENGINE" rm -f "$NAME" && echo "container removido (volume $VOL preservado)" ;;
  *) echo "uso: $0 {atualizar|build|restart|logs|status|parar}" >&2; exit 2 ;;
esac
