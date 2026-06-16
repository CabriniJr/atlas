"""Testes do carregador de rotinas (E1-01).

TDD: testes escritos antes da implementação. Suíte curada (best-of-two):
descoberta, parsing+defaults, validação com erro claro, resiliência (ADR-0006),
ativa vs inativa, e detecção de collect/prompt.
"""

from __future__ import annotations

import pytest

from atlas.routines import ErroRotina, carregar_rotinas


def _escrever_config(pasta, conteudo: str) -> None:
    pasta.mkdir()
    (pasta / "routine.toml").write_text(conteudo, encoding="utf-8")


# --- Descoberta -------------------------------------------------------------


def test_descobre_multiplas_rotinas(tmp_path):
    for nome in ("alpha", "beta", "gamma"):
        _escrever_config(tmp_path / nome, f'nome = "{nome}"\ndescricao = "rotina {nome}"')

    resultado = carregar_rotinas(tmp_path)

    assert {r.nome for r in resultado.rotinas} == {"alpha", "beta", "gamma"}
    assert resultado.erros == []


def test_pasta_sem_routine_toml_e_ignorada(tmp_path):
    """Subpasta sem routine.toml não vira rotina nem erro."""
    (tmp_path / "nao_e_rotina").mkdir()
    _escrever_config(tmp_path / "valida", 'nome = "valida"\ndescricao = "ok"')

    resultado = carregar_rotinas(tmp_path)

    assert len(resultado.rotinas) == 1
    assert resultado.rotinas[0].nome == "valida"
    assert resultado.erros == []


def test_ignora_arquivos_soltos_na_raiz(tmp_path):
    (tmp_path / "leia-me.txt").write_text("não sou rotina\n", encoding="utf-8")
    _escrever_config(tmp_path / "real", 'nome = "real"\ndescricao = "única"')

    resultado = carregar_rotinas(tmp_path)

    assert len(resultado.rotinas) == 1


def test_diretorio_inexistente_retorna_vazio(tmp_path):
    resultado = carregar_rotinas(tmp_path / "nao-existe")
    assert resultado.rotinas == []
    assert resultado.erros == []


def test_diretorio_raiz_vazio_retorna_listas_vazias(tmp_path):
    resultado = carregar_rotinas(tmp_path)
    assert resultado.rotinas == []
    assert resultado.erros == []


# --- Parsing e defaults -----------------------------------------------------


def test_campos_obrigatorios_sao_mapeados(tmp_path):
    _escrever_config(tmp_path / "r", 'nome = "r"\ndescricao = "faz algo util"')
    rotina = carregar_rotinas(tmp_path).rotinas[0]
    assert rotina.nome == "r"
    assert rotina.descricao == "faz algo util"


def test_defaults_dos_campos_opcionais(tmp_path):
    """triggers=[] e catch_up=False; demais opcionais são None."""
    _escrever_config(tmp_path / "r", 'nome = "r"\ndescricao = "teste"')
    r = carregar_rotinas(tmp_path).rotinas[0]
    assert r.ativa is True
    assert r.modelo == "none"
    assert r.triggers == []
    assert r.catch_up is False
    assert r.agenda is None
    assert r.gate is None
    assert r.timeout is None
    assert r.budget_tokens is None
    assert r.store is None
    assert r.saida is None


def test_todos_os_campos_opcionais_sao_carregados(tmp_path):
    _escrever_config(
        tmp_path / "completa",
        """
nome = "completa"
descricao = "rotina completa"
triggers = ["resumo", "report"]
agenda = "0 8 * * *"
modelo = "haiku"
gate = "tem_dados"
timeout = 30
budget_tokens = 5000
catch_up = true
store = "runs"
saida = "telegram"
ativa = false
""",
    )
    r = carregar_rotinas(tmp_path).rotinas[0]
    assert r.triggers == ["resumo", "report"]
    assert r.agenda == "0 8 * * *"
    assert r.modelo == "haiku"
    assert r.gate == "tem_dados"
    assert r.timeout == 30
    assert r.budget_tokens == 5000
    assert r.catch_up is True
    assert r.store == "runs"
    assert r.saida == "telegram"
    assert r.ativa is False


# --- Validação --------------------------------------------------------------


def test_nome_ausente_gera_erro_claro(tmp_path):
    _escrever_config(tmp_path / "sem_nome", 'descricao = "falta o nome"')
    resultado = carregar_rotinas(tmp_path)
    assert resultado.rotinas == []
    assert len(resultado.erros) == 1
    assert resultado.erros[0].pasta == "sem_nome"
    assert "nome" in resultado.erros[0].mensagem


def test_descricao_ausente_gera_erro_claro(tmp_path):
    _escrever_config(tmp_path / "sem_desc", 'nome = "sem_desc"')
    resultado = carregar_rotinas(tmp_path)
    assert resultado.rotinas == []
    assert resultado.erros[0].pasta == "sem_desc"
    assert "descricao" in resultado.erros[0].mensagem


def test_modelo_invalido_gera_erro_com_pasta_e_valor(tmp_path):
    _escrever_config(
        tmp_path / "modelo_errado",
        'nome = "modelo_errado"\ndescricao = "modelo inexistente"\nmodelo = "gpt-4"',
    )
    resultado = carregar_rotinas(tmp_path)
    assert resultado.rotinas == []
    erro = resultado.erros[0]
    assert erro.pasta == "modelo_errado"
    assert "modelo" in erro.mensagem
    assert "gpt-4" in erro.mensagem


@pytest.mark.parametrize("modelo", ["none", "haiku", "sonnet", "opus"])
def test_modelos_validos_sao_aceitos(tmp_path, modelo):
    _escrever_config(
        tmp_path / f"r_{modelo}",
        f'nome = "r_{modelo}"\ndescricao = "teste"\nmodelo = "{modelo}"',
    )
    resultado = carregar_rotinas(tmp_path)
    assert resultado.erros == []
    assert resultado.rotinas[0].modelo == modelo


# --- Resiliência (ADR-0006) -------------------------------------------------


def test_rotina_malformada_nao_derruba_as_outras(tmp_path):
    _escrever_config(tmp_path / "boa", 'nome = "boa"\ndescricao = "tudo certo"')
    _escrever_config(tmp_path / "ruim", 'descricao = "falta o nome"')

    resultado = carregar_rotinas(tmp_path)

    assert len(resultado.rotinas) == 1
    assert resultado.rotinas[0].nome == "boa"
    assert len(resultado.erros) == 1
    assert resultado.erros[0].pasta == "ruim"


def test_toml_invalido_gera_erro_e_nao_derruba(tmp_path):
    _escrever_config(tmp_path / "valida", 'nome = "valida"\ndescricao = "ok"')
    invalida = tmp_path / "invalida"
    invalida.mkdir()
    (invalida / "routine.toml").write_text("nome = [chave_sem_fechar", encoding="utf-8")

    resultado = carregar_rotinas(tmp_path)

    assert len(resultado.rotinas) == 1
    assert len(resultado.erros) == 1
    assert resultado.erros[0].pasta == "invalida"


def test_multiplas_rotinas_com_erro_sao_todas_rastreadas(tmp_path):
    for i in range(3):
        _escrever_config(tmp_path / f"ruim_{i}", f'descricao = "falta nome {i}"')

    resultado = carregar_rotinas(tmp_path)

    assert resultado.rotinas == []
    assert {e.pasta for e in resultado.erros} == {"ruim_0", "ruim_1", "ruim_2"}


def test_erro_rotina_tem_pasta_e_mensagem(tmp_path):
    _escrever_config(tmp_path / "r", 'descricao = "sem nome"')
    erro = carregar_rotinas(tmp_path).erros[0]
    assert isinstance(erro, ErroRotina)
    assert isinstance(erro.pasta, str)
    assert isinstance(erro.mensagem, str)
    assert erro.mensagem


# --- Ativa vs inativa -------------------------------------------------------


def test_distingue_ativas_de_inativas(tmp_path):
    _escrever_config(tmp_path / "ligada", 'nome = "ligada"\ndescricao = "t"\nativa = true')
    _escrever_config(tmp_path / "desligada", 'nome = "desligada"\ndescricao = "t"\nativa = false')

    resultado = carregar_rotinas(tmp_path)

    assert [r.nome for r in resultado.ativas] == ["ligada"]
    assert [r.nome for r in resultado.inativas] == ["desligada"]


# --- Detecção de collect / prompt -------------------------------------------


def test_detecta_collect_e_prompt(tmp_path):
    com = tmp_path / "com-tudo"
    _escrever_config(com, 'nome = "com-tudo"\ndescricao = "tem ambos"')
    (com / "collect.py").write_text("# collect\n", encoding="utf-8")
    (com / "prompt.md").write_text("# prompt\n", encoding="utf-8")
    _escrever_config(tmp_path / "so-config", 'nome = "so-config"\ndescricao = "só config"')

    por_nome = {r.nome: r for r in carregar_rotinas(tmp_path).rotinas}

    assert por_nome["com-tudo"].tem_collect is True
    assert por_nome["com-tudo"].tem_prompt is True
    assert por_nome["so-config"].tem_collect is False
    assert por_nome["so-config"].tem_prompt is False


def test_detecta_collect_com_extensao_diferente(tmp_path):
    pasta = tmp_path / "r"
    _escrever_config(pasta, 'nome = "r"\ndescricao = "teste"')
    (pasta / "collect.sh").write_text("#!/bin/sh\n", encoding="utf-8")

    rotina = carregar_rotinas(tmp_path).rotinas[0]
    assert rotina.tem_collect is True
