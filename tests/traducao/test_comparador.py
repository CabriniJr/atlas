"""Comparador de consistência opt-in (ADR-0034): unificação de termos."""

from __future__ import annotations

import re

import fitz

from atlas.traducao.pipeline import traduzir_pdf
from atlas.traducao.traducao_ia import (
    ConfigTraducao,
    aplicar_unificacao,
    unificar_termos,
)


def test_unificar_termos_parseia_mapa_json():
    def fake(prompt, modelo=None, timeout=60, motor="claude"):
        return 'Segue: {"contêiner": "container", "K8s": "Kubernetes"}'

    mapa = unificar_termos(["um contêiner", "K8s roda"], ConfigTraducao(), invocar_fn=fake)
    assert mapa == {"contêiner": "container", "K8s": "Kubernetes"}


def test_unificar_termos_vazio_ou_lixo_nao_quebra():
    assert unificar_termos([], ConfigTraducao(), invocar_fn=lambda *a, **k: "{}") == {}
    assert unificar_termos(["x"], ConfigTraducao(), invocar_fn=lambda *a, **k: "sem json") == {}

    def explode(*a, **k):
        raise RuntimeError("tokens")

    assert unificar_termos(["x"], ConfigTraducao(), invocar_fn=explode) == {}


def test_aplicar_unificacao_substitui_palavra_inteira():
    txt = aplicar_unificacao("o K8s e o K8sX", {"K8s": "Kubernetes"})
    assert txt == "o Kubernetes e o K8sX"  # não toca K8sX (palavra inteira)


def test_comparador_desligado_por_padrao_nao_chama_ia(tmp_path):
    src = tmp_path / "s.pdf"
    doc = fitz.open(); doc.new_page().insert_text((72, 100), "Term here.", fontsize=11)
    doc.save(str(src)); doc.close()

    chamadas = []

    def invocar(prompt, modelo=None, timeout=60, motor="claude"):
        chamadas.append(prompt)
        ids = re.findall(r"\[\[(\d+)\]\]", prompt)
        return "\n".join(f"[[{i}]] termo aqui" for i in ids)

    traduzir_pdf(str(src), str(tmp_path / "o.pdf"), ConfigTraducao(),  # comparador=False
                 invocar_fn=invocar, bruto_fn=lambda ts, c: ["bruto"] * len(ts))
    # nenhum prompt de comparador (só de refino, que contém [[N]])
    assert all("objeto JSON" not in p for p in chamadas)


def test_comparador_ligado_unifica_no_pdf(tmp_path):
    src = tmp_path / "s.pdf"
    doc = fitz.open(); doc.new_page().insert_text((72, 100), "The container.", fontsize=11)
    doc.save(str(src)); doc.close()

    def invocar(prompt, modelo=None, timeout=60, motor="claude"):
        if "objeto JSON" in prompt:  # chamada do comparador
            return '{"contêiner": "container"}'
        ids = re.findall(r"\[\[(\d+)\]\]", prompt)
        return "\n".join(f"[[{i}]] um contêiner" for i in ids)

    out = tmp_path / "o.pdf"
    traduzir_pdf(str(src), str(out), ConfigTraducao(comparador=True),
                 invocar_fn=invocar, bruto_fn=lambda ts, c: ["bruto"] * len(ts))
    txt = fitz.open(str(out))[0].get_text()
    assert "container" in txt and "contêiner" not in txt
