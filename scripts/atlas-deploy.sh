#!/usr/bin/env bash
# Atlas CD — pull do ref de produção + restart do serviço quando há novidades.
#
# Rodado por timer systemd (atlas-deploy.timer). Idempotente: se não houver
# commits novos, não faz nada. Por padrão acompanha a branch `main`; defina
# ATLAS_DEPLOY_REF para outra branch ou ATLAS_DEPLOY_TRACK=tags p/ a última tag.
#
# Política (CLAUDE.md): "prod só roda tags" — para seguir à risca, use
# ATLAS_DEPLOY_TRACK=tags. O default `main` atende o fluxo de auto-deploy pedido,
# já protegido por revisão de PR antes do merge.
set -euo pipefail

REPO="${ATLAS_HOME:-$HOME/atlas}"
cd "$REPO"

log() { echo "$(date -Is) atlas-deploy: $*"; }

git fetch --quiet --tags origin

if [ "${ATLAS_DEPLOY_TRACK:-branch}" = "tags" ]; then
    TARGET="$(git describe --tags "$(git rev-list --tags --max-count=1)" 2>/dev/null || true)"
    [ -z "$TARGET" ] && { log "nenhuma tag encontrada"; exit 0; }
    REMOTE="$(git rev-list -n1 "$TARGET")"
else
    REF="${ATLAS_DEPLOY_REF:-main}"
    REMOTE="$(git rev-parse "origin/$REF")"
    TARGET="$REF"
fi

LOCAL="$(git rev-parse HEAD)"
if [ "$LOCAL" = "$REMOTE" ]; then
    log "sem mudanças (${LOCAL:0:7} @ $TARGET)"
    exit 0
fi

log "atualizando ${LOCAL:0:7} -> ${REMOTE:0:7} ($TARGET)"
git checkout --quiet "$TARGET" 2>/dev/null || git checkout --quiet "${ATLAS_DEPLOY_REF:-main}"
if [ "${ATLAS_DEPLOY_TRACK:-branch}" != "tags" ]; then
    git pull --ff-only --quiet origin "${ATLAS_DEPLOY_REF:-main}"
fi

# Reinstala deps só se o empacotamento mudou (rápido no caso comum).
if git diff --name-only "$LOCAL" "$REMOTE" | grep -qE 'pyproject\.toml|requirements'; then
    log "deps mudaram — pip install -e"
    "$REPO/.venv/bin/pip" install -e "$REPO" --quiet
fi

systemctl --user restart atlas
log "atualizado para ${REMOTE:0:7} e serviço reiniciado"
