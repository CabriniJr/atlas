"""CLI do torrent — ``python -m atlas torrent <arquivo.torrent>`` (ADR-0049).

Roda o mesmo caminho do Telegram (verifica → confirma → baixa headless) sem
depender do bot. Útil para o requisito "torrent via cli". Usa um store SQLite
próprio (o mesmo ``data/atlas.sqlite``) para o job aparecer no dashboard.
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from atlas.core.store import ResourceStore
from atlas.torrent import download, servico


def cli_torrent(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="atlas torrent", description="Baixa um .torrent headless.")
    p.add_argument("arquivo", help="caminho do arquivo .torrent")
    p.add_argument("--sim", action="store_true", help="não pergunta; confirma automaticamente")
    p.add_argument("--dir", default=servico.DESTINO_DEFAULT, help="pasta de destino")
    p.add_argument("--vpn", default="", help="exige esta interface VPN (kill-switch)")
    p.add_argument("--no-vpn", action="store_true", help="permite baixar sem VPN (padrão)")
    p.add_argument("--db", default="data/atlas.sqlite", help="store SQLite")
    args = p.parse_args(argv)

    caminho = Path(args.arquivo)
    if not caminho.exists():
        print(f"✖ arquivo não encontrado: {caminho}")
        return 2

    store = ResourceStore(args.db)
    agora = datetime.now()
    # chat_id=0: sentinela p/ que as notificações de marco/término disparem e
    # sejam impressas no terminal (o notificador da CLI ignora o chat).
    res, sc = servico.criar_do_bytes(
        store, caminho.read_bytes(), caminho.name, 0, agora,
        destino=args.dir, vpn=args.vpn, permitir_sem_vpn=not args.vpn,
    )
    if res is None:
        print(f"✖ {sc.erro}")
        return 2

    print(sc.humano())
    if sc.risco >= 2 and not args.sim:
        resp = input("\n🚨 risco ALTO. Baixar mesmo assim? digite SIM: ")
        forte = resp.strip() == "SIM"
        if not forte:
            print("cancelado.")
            return 0
    elif not args.sim:
        resp = input("\nBaixar agora? [s/N] ")
        if resp.strip().lower() not in ("s", "sim", "y"):
            print("cancelado.")
            return 0

    if not download.motor_disponivel():
        print("✖ motor indisponível. Instale: sudo dnf install -y qbittorrent-nox")
        return 3

    servico._patch_status(store, res.name, {"fase": servico.BAIXANDO}, agora)

    def _print_progress(chat, msg):  # noqa: ARG001 — chat não usado na CLI
        print(msg)

    print("\n⬇️ baixando... (Ctrl+C aborta)")
    servico.executar_download(store, res.name, notificar=_print_progress)
    final = store.get(servico.KIND, res.name)
    fase = (final.status or {}).get("fase") if final else "?"
    return 0 if fase == servico.CONCLUIDO else 1
