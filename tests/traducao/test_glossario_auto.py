"""glossario_auto + cache persistido em disco (ADR-0030)."""

from __future__ import annotations

import fitz

from atlas.traducao.extracao import BlocoTraducao
from atlas.traducao.pipeline import _mesclar_glossario, traduzir_pdf
from atlas.traducao.traducao_ia import CacheTraducao, ConfigTraducao, detectar_glossario


def _blocos(*textos):
    return [BlocoTraducao(id=i, pagina=0, bbox=(0, 0, 1, 1), texto=t) for i, t in enumerate(textos)]


def test_detectar_glossario_filtra_termos_ausentes():
    blocos = _blocos("The kubectl command scales the deployment.")
    cfg = ConfigTraducao(assunto="Kubernetes")

    # IA devolve termos válidos + um inventado (Foobar) que não está no texto.
    def fake(prompt, modelo=None, motor=None):
        return "kubectl, deployment, Foobar"

    termos = detectar_glossario(blocos, cfg, invocar_fn=fake)
    assert "kubectl" in termos
    assert "deployment" in termos
    assert "Foobar" not in termos  # não aparece no corpus ⇒ descartado


def test_detectar_glossario_sem_blocos():
    assert detectar_glossario([], ConfigTraducao(), invocar_fn=lambda *a, **k: "x") == []


def test_detectar_glossario_ia_falha_retorna_vazio():
    def boom(*a, **k):
        raise RuntimeError("sem IA")

    termos = detectar_glossario(_blocos("Hello kubectl world"), ConfigTraducao(), invocar_fn=boom)
    assert termos == []


def test_mesclar_glossario_sem_duplicar():
    assert _mesclar_glossario(["pod"], ["Pod", "deployment"]) == ["pod", "deployment"]


def test_cache_persistencia_roundtrip(tmp_path):
    cfg = ConfigTraducao()
    c = CacheTraducao()
    c.put("Hello", cfg, "Olá")
    path = tmp_path / "sub" / "c.cache.json"
    c.salvar(path)

    c2 = CacheTraducao.carregar(path)
    assert c2.get("Hello", cfg) == "Olá"


def test_cache_carregar_ausente_ou_corrompido(tmp_path):
    assert CacheTraducao.carregar(tmp_path / "nao-existe.json").to_dict() == {}
    ruim = tmp_path / "ruim.json"
    ruim.write_text("{nao eh json", encoding="utf-8")
    assert CacheTraducao.carregar(ruim).to_dict() == {}


def test_pipeline_glossario_auto_injeta_termos(tmp_path):
    src = tmp_path / "l.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((72, 100), "The kubectl command scales pods.", fontname="helv", fontsize=12)
    doc.save(str(src))
    doc.close()

    capturado = {}

    def fake(prompt, modelo=None, motor=None, timeout=60):
        if "permanecer em inglês" in prompt:
            return "kubectl, pods"  # detecção
        capturado["prompt"] = prompt  # refino
        return "[[0]] O comando kubectl escala pods."

    cfg = ConfigTraducao(assunto="Kubernetes", glossario_auto=True)
    prog = traduzir_pdf(
        str(src), str(tmp_path / "out.pdf"), cfg, invocar_fn=fake, bruto_fn=lambda ts, c: ts
    )

    assert "kubectl" in prog.glossario_auto
    assert "kubectl" in cfg.glossario  # mesclado
    assert "kubectl" in capturado["prompt"]  # entrou no prompt de refino
