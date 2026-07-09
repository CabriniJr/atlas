"""Ponto de entrada: ``python -m atlas`` inicia o bot.

Subcomando ``apply`` aplica manifestos via API (``python -m atlas apply -f …``).
"""

from __future__ import annotations

import sys

from atlas.app import run


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "apply":
        from atlas.apply import cli_apply

        return cli_apply(argv[1:])
    if argv and argv[0] == "torrent":
        from atlas.torrent.cli import cli_torrent

        return cli_torrent(argv[1:])
    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
