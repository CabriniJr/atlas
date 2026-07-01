#!/usr/bin/env bash
# Snapshot de handoff — chamado pelo hook PreCompact do Claude Code (settings.json)
# quando o contexto enche (≈ token flag perto de 90-100%). Grava o estado mecânico
# para o PO "subir o agente depois" e continuar de onde parou. Best-effort: nunca
# falha o compact (sempre sai 0).
set +e
REPO="/home/guaxinim/atlas"
OUT="$REPO/docs/processos/handoff-auto.md"
cd "$REPO" 2>/dev/null || exit 0

{
  echo "# Handoff automático — $(date -Iseconds)"
  echo
  echo "> Gerado pelo hook PreCompact (contexto cheio). Estado durável para retomar."
  echo
  echo "## Últimos commits (main)"
  git log --oneline -15
  echo
  echo "## Working tree (não commitado)"
  git status -s
  echo
  echo "## Testes de tradução"
  .venv/bin/python -m pytest tests/traducao -q 2>&1 | tail -3
  echo
  echo "## Progresso do plano E9-01 (render editorial)"
  grep -nE '^### Task|^- \[[ x]\]' docs/superpowers/plans/2026-07-01-render-editorial.md
  echo
  echo "## Como continuar"
  echo "- Spec: docs/specs/traducao-render-editorial.md · ADR: docs/arquitetura/adr/ADR-0033-render-editorial-hibrido.md"
  echo "- Plano: docs/superpowers/plans/2026-07-01-render-editorial.md (executar tarefas com [ ])"
  echo "- Épico e backlog: docs/roadmap/backlog.md (E9)"
  echo "- Handoff narrativo: docs/processos/dossie-handoff.md"
} > "$OUT" 2>&1

exit 0
