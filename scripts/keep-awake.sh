#!/usr/bin/env bash
# Keep-awake avulso (ADR-0050): impede a máquina de suspender enquanto rodar.
# Segura um inibidor systemd de sleep/idle/fechar-tampa até você dar Ctrl-C.
# NÃO bloqueia desligar de propósito — só a suspensão automática.
#
# Uso:  ./scripts/keep-awake.sh
set -euo pipefail

if ! command -v systemd-inhibit >/dev/null 2>&1; then
  echo "systemd-inhibit indisponível — nada a fazer neste sistema." >&2
  exit 1
fi

echo "🔌 suspensão inibida (sleep/idle/tampa). Ctrl-C para liberar."
exec systemd-inhibit \
  --what=sleep:idle:handle-lid-switch \
  --who=Atlas \
  --why="keep-awake avulso" \
  --mode=block \
  sleep infinity
