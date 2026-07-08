import threading

from atlas.traducao.traducao_ia import CacheTraducao, ConfigTraducao


def test_cache_salvar_concorrente_nao_corrompe(tmp_path):
    cache = CacheTraducao()
    cfg = ConfigTraducao()
    for i in range(200):
        cache.put(f"t{i}", cfg, f"v{i}")
    path = tmp_path / "c.json"

    erros = []

    def salva():
        try:
            for _ in range(20):
                cache.salvar(path)
        except Exception as e:  # noqa: BLE001
            erros.append(e)

    ts = [threading.Thread(target=salva) for _ in range(4)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert not erros
    lido = CacheTraducao.carregar(path)
    assert lido.get("t0", cfg) == "v0"
