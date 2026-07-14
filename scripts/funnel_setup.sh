#!/usr/bin/env bash
# Publica os serviços do Atlas pela internet via Tailscale Funnel (ADR-0052/0053).
# Idempotente. Cada serviço numa porta Funnel distinta (Funnel só libera 443/8443/10000).
#
#   :443  -> Ownfoil (loja Tinfoil)   backend 127.0.0.1:8465   [frente E]
#   :8443 -> MCP do Atlas              backend 127.0.0.1:8787   [frente F, futuro]
#
# Pré-requisitos (uma vez, no admin console https://login.tailscale.com):
#   1) DNS  -> "Enable HTTPS certificates"
#   2) Access Controls -> atributo `funnel` para o nó `fedora`
# E, na máquina (uma vez, exige sudo) para o CLI operar sem root:
#   sudo tailscale set --operator=$USER
set -uo pipefail

# Pares "porta_publica:backend_local". MCP comentado até a frente F subir.
PARES=(
  "443:127.0.0.1:8465"    # Ownfoil
  # "8443:127.0.0.1:8787" # MCP (frente F)
)

operador_faltando() {
  echo "!! 'tailscale funnel' negou acesso (escrita)." >&2
  echo "   Rode UMA vez (precisa de sudo) e execute este script de novo:" >&2
  echo "     sudo tailscale set --operator=\$USER" >&2
  echo "   Se ainda falhar, confirme no admin console: DNS->Enable HTTPS e atributo 'funnel' no nó." >&2
  exit 1
}

echo "== Publicando serviços via Funnel =="
for par in "${PARES[@]}"; do
  porta="${par%%:*}"; backend="${par#*:}"
  echo ">> :$porta  ->  http://$backend"
  # --bg: roda em background (persiste); --https=<porta>: TLS público na porta.
  saida="$(tailscale funnel --bg --https="$porta" "http://$backend" 2>&1)"
  if grep -qi "access denied\|operator" <<<"$saida"; then operador_faltando; fi
  [ -n "$saida" ] && echo "$saida"
done

echo
echo "== Estado do Funnel =="
tailscale funnel status
