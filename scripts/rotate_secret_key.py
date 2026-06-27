#!/usr/bin/env python3
"""Rotação da chave mestra do cofre (ADR-0027 §Pendências / hardening 1.4).

Re-cifra **todos** os segredos (`secrets/credentials/*.enc`) com uma chave Fernet
nova, faz backup da chave antiga (`secret.key.bak-<ts>`) e imprime a nova chave.

Uso:
    python scripts/rotate_secret_key.py [--secrets-dir secrets]

Seguro (ADR-0006): decifra tudo com a chave atual antes de trocar — aborta sem
perda se algum blob falhar. **Não** funciona com `ATLAS_SECRET_KEY` no ambiente
(a env sobreporia a chave nova): remova a env, rode, e depois atualize a env/.env
com a nova chave impressa. Em produção (Rasp), reinicie o serviço após rotacionar.
"""

from __future__ import annotations

import argparse
import os
import sys

from atlas import secrets_store as sec


def run(secrets_dir: str | None) -> int:
    if secrets_dir:
        os.environ["ATLAS_SECRETS_DIR"] = secrets_dir
    sec.reset_cache()
    try:
        out = sec.rotate_key()
    except sec.SecretsError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 1
    print(f"✅ Rotação concluída: {out['rotated']} segredo(s) re-cifrado(s).")
    if out["backup"]:
        print(f"   Backup da chave antiga: {out['backup']}")
    print("\n⚠️  Guarde a NOVA chave mestra com segurança (e atualize ATLAS_SECRET_KEY")
    print("    se você a usa via ambiente). Sem ela, os segredos são irrecuperáveis:\n")
    print(f"   ATLAS_SECRET_KEY={out['new_key']}\n")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description="Rotaciona a chave mestra do cofre.")
    ap.add_argument(
        "--secrets-dir", help="Diretório do cofre (default: env ATLAS_SECRETS_DIR ou 'secrets')"
    )
    args = ap.parse_args()
    raise SystemExit(run(args.secrets_dir))


if __name__ == "__main__":
    main()
