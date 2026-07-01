"""Thread-safety do ResourceStore (regressão do bug de tradução travada).

A tradução roda numa thread daemon gravando ``status`` (progresso/log) enquanto o
servidor HTTP lê o mesmo recurso na thread principal — ambos pela mesma conexão
sqlite compartilhada. Sem serialização isso levanta ``InterfaceError`` e derruba
a tradução (ela "trava" na página em que a escrita falhou). Este teste martela o
store de várias threads e exige zero erros.
"""

from __future__ import annotations

import threading
from datetime import datetime

from atlas.core.resource import Resource
from atlas.core.store import ResourceStore


def test_store_aguenta_leitura_escrita_concorrente(tmp_path):
    store = ResourceStore(str(tmp_path / "c.sqlite"))
    store.create(Resource(kind="Traducao", name="x"), datetime.now())

    erros: list[tuple[str, str]] = []

    def escritor() -> None:
        for i in range(300):
            try:
                store.set_status(
                    "Traducao",
                    "x",
                    {"i": i, "log": [{"t": str(i)} for _ in range(20)]},
                    datetime.now(),
                )
            except Exception as exc:  # noqa: BLE001
                erros.append(("escritor", repr(exc)))
                return

    def leitor() -> None:
        for _ in range(300):
            try:
                assert store.get("Traducao", "x") is not None
            except Exception as exc:  # noqa: BLE001
                erros.append(("leitor", repr(exc)))
                return

    threads = [threading.Thread(target=escritor) for _ in range(3)]
    threads += [threading.Thread(target=leitor) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not erros, f"acesso concorrente ao store falhou: {erros[:5]}"
    # a última escrita tem de estar persistida e íntegra
    assert store.get("Traducao", "x").status.get("i") is not None
