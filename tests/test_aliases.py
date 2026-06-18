"""TDD — aliases de verbo e Kind, snips."""

from __future__ import annotations

import atlas.aliases as aliases

# ── expandir ─────────────────────────────────────────────────────────────────

def test_alias_r_expande_para_get():
    assert aliases.expandir("/r Tracker peso") == "/get Tracker peso"


def test_alias_ls_expande_para_list():
    assert aliases.expandir("/ls Tracker") == "/list Tracker"


def test_alias_cat_expande_para_describe():
    assert aliases.expandir("/cat Goal meta") == "/describe Goal meta"


def test_alias_rm_expande_para_delete():
    assert aliases.expandir("/rm Tracker peso") == "/delete Tracker peso"


def test_alias_d_expande_para_describe():
    assert aliases.expandir("/d Tracker peso") == "/describe Tracker peso"


def test_kind_t_normaliza_para_tracker():
    assert aliases.expandir("/list t") == "/list Tracker"


def test_kind_g_normaliza_para_goal():
    assert aliases.expandir("/ls g") == "/list Goal"


def test_kind_al_normaliza_para_alarm():
    assert aliases.expandir("/ls al") == "/list Alarm"


def test_kind_doc_normaliza_para_doc():
    assert aliases.expandir("/describe doc backlog") == "/describe Doc backlog"


def test_alias_combinado_r_plus_t():
    assert aliases.expandir("/r t peso") == "/get Tracker peso"


def test_alias_cat_plus_g():
    assert aliases.expandir("/cat g minha-meta") == "/describe Goal minha-meta"


def test_texto_livre_nao_afetado():
    assert aliases.expandir("peso: 82.3") == "peso: 82.3"


def test_comando_desconhecido_nao_afetado():
    assert aliases.expandir("/pool") == "/pool"


def test_kind_ja_correto_nao_muda():
    assert aliases.expandir("/list Tracker") == "/list Tracker"


# ── responder_snip ─────────────────────────────────────────────────────────────

def test_snip_nao_e_comando_retorna_none():
    assert aliases.responder_snip("/help") is None
    assert aliases.responder_snip("texto livre") is None


def test_snip_sem_arg_lista_kinds():
    resp = aliases.responder_snip("/snip")
    assert resp is not None
    assert "Tracker" in resp
    assert "Goal" in resp


def test_snip_tracker():
    resp = aliases.responder_snip("/snip Tracker")
    assert resp is not None
    assert "/track new" in resp
    assert "spec.unit" in resp.lower() or "unit" in resp


def test_snip_kind_alias_t():
    resp = aliases.responder_snip("/snip t")
    assert resp is not None
    assert "Tracker" in resp


def test_snip_goal():
    resp = aliases.responder_snip("/snip Goal")
    assert resp is not None
    assert "/goal set" in resp
    assert "target" in resp


def test_snip_timer():
    resp = aliases.responder_snip("/snip timer")
    assert resp is not None
    assert "/timer start" in resp
    assert "/timer finish" in resp


def test_snip_doc():
    resp = aliases.responder_snip("/snip doc")
    assert resp is not None
    assert "/docs" in resp
    assert "/apply Doc" in resp


def test_snip_kind_inexistente():
    resp = aliases.responder_snip("/snip XyzKindInexistente")
    assert resp is not None
    assert "❓" in resp
