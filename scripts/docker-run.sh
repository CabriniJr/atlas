#!/usr/bin/env bash
# Sobe o Atlas como container que reinicia sozinho (restart: always).
# Uso:  ./scripts/docker-run.sh
# Pré-requisitos: Docker + Docker Compose instalados e o daemon habilitado no boot.
set -euo pipefail

cd "$(dirname "$0")/.."

# 1) Precisa do .env com TELEGRAM_TOKEN e ATLAS_ALLOWED_USER_ID.
if [ ! -f .env ]; then
  echo "✗ Falta o arquivo .env na raiz."
  echo "  Crie a partir do exemplo:  cp resumo/.env.example .env  (e preencha)"
  exit 1
fi

# 2) Docker disponível?
if ! command -v docker >/dev/null 2>&1; then
  echo "✗ Docker não encontrado. Instale o Docker Engine + Compose."
  exit 1
fi

# 3) Diretório de dados persistente (SQLite).
mkdir -p data

# 4) Build + sobe em background. 'docker compose' (v2) com fallback p/ 'docker-compose'.
echo "==> build + up"
if docker compose version >/dev/null 2>&1; then
  docker compose up -d --build
  docker compose ps
else
  docker-compose up -d --build
  docker-compose ps
fi

cat <<'EOF'

✓ Atlas no ar.
  Logs ao vivo:   docker compose logs -f atlas
  Parar:          docker compose down
  Reiniciar:      docker compose restart atlas

O container reinicia sozinho após reboot (restart: always), desde que o serviço
do Docker esteja habilitado no boot:  sudo systemctl enable --now docker
EOF
