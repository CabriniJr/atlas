"""TDD — Agente modo=code via Ollama nativo (ADR-0042)."""

from __future__ import annotations

import pytest

from atlas.agente_ollama import (
    FerramentaErro,
    OllamaIndisponivel,
    executar_tool_call,
    ferramenta_edit_file,
    ferramenta_find_files,
    ferramenta_list_dir,
    ferramenta_read_file,
    ferramenta_run_command,
    ferramenta_search_text,
    ferramenta_write_file,
    filtrar_ferramentas,
    rodar_loop,
)

# ── Ferramentas nativas ───────────────────────────────────────────────────────


def test_read_file_le_conteudo(tmp_path):
    (tmp_path / "a.txt").write_text("olá")
    assert ferramenta_read_file(str(tmp_path), "a.txt") == "olá"


def test_read_file_inexistente_levanta_ferramenta_erro(tmp_path):
    with pytest.raises(FerramentaErro, match="não encontrado"):
        ferramenta_read_file(str(tmp_path), "nao-existe.txt")


def test_read_file_recusa_escapar_do_workspace(tmp_path):
    (tmp_path / "sandbox").mkdir()
    fora = tmp_path / "segredo.txt"
    fora.write_text("nao deveria ler")
    with pytest.raises(FerramentaErro, match="escapa"):
        ferramenta_read_file(str(tmp_path / "sandbox"), "../segredo.txt")


def test_read_file_recusa_caminho_absoluto_fora(tmp_path):
    with pytest.raises(FerramentaErro, match="escapa"):
        ferramenta_read_file(str(tmp_path), "/etc/passwd")


def test_read_file_trunca_arquivo_gigante(tmp_path):
    (tmp_path / "g.txt").write_text("x" * 300_000)
    out = ferramenta_read_file(str(tmp_path), "g.txt")
    assert len(out) < 300_000
    assert "truncado" in out


def test_write_file_cria_dirs_e_escreve(tmp_path):
    msg = ferramenta_write_file(str(tmp_path), "novo/arquivo.txt", "conteúdo")
    assert (tmp_path / "novo" / "arquivo.txt").read_text() == "conteúdo"
    assert "escrito" in msg


def test_write_file_recusa_escapar_do_workspace(tmp_path):
    with pytest.raises(FerramentaErro, match="escapa"):
        ferramenta_write_file(str(tmp_path), "../fora.txt", "x")


def test_edit_file_substitui_ocorrencia_unica(tmp_path):
    p = tmp_path / "f.py"
    p.write_text("def foo():\n    return 1\n")
    ferramenta_edit_file(str(tmp_path), "f.py", "return 1", "return 2")
    assert p.read_text() == "def foo():\n    return 2\n"


def test_edit_file_old_string_ausente_levanta_erro(tmp_path):
    p = tmp_path / "f.py"
    p.write_text("x = 1\n")
    with pytest.raises(FerramentaErro, match="não encontrado"):
        ferramenta_edit_file(str(tmp_path), "f.py", "y = 2", "y = 3")


def test_edit_file_old_string_ambiguo_levanta_erro(tmp_path):
    p = tmp_path / "f.py"
    p.write_text("x = 1\nx = 1\n")
    with pytest.raises(FerramentaErro, match="único"):
        ferramenta_edit_file(str(tmp_path), "f.py", "x = 1", "x = 2")


def test_list_dir_lista_ordenado_com_barra_em_dirs(tmp_path):
    (tmp_path / "b.txt").write_text("")
    (tmp_path / "a_dir").mkdir()
    out = ferramenta_list_dir(str(tmp_path), ".")
    assert out.split("\n") == ["a_dir/", "b.txt"]


def test_list_dir_inexistente_levanta_erro(tmp_path):
    with pytest.raises(FerramentaErro, match="não encontrado"):
        ferramenta_list_dir(str(tmp_path), "nada")


def test_run_command_captura_stdout_mesmo_com_exit_nao_zero(tmp_path):
    out = ferramenta_run_command(str(tmp_path), "echo oi; exit 3")
    assert "oi" in out
    assert "(exit 3)" in out


def test_run_command_timeout_levanta_ferramenta_erro(tmp_path):
    with pytest.raises(FerramentaErro, match="timeout"):
        ferramenta_run_command(str(tmp_path), "sleep 5", timeout=0.1)


# ── search_text / find_files (equivalentes a Grep/Glob, ADR-0044) ────────────


def test_search_text_acha_padrao_com_arquivo_e_linha(tmp_path):
    (tmp_path / "a.py").write_text("def foo():\n    return 1\n")
    (tmp_path / "b.py").write_text("def bar():\n    return 2\n")
    out = ferramenta_search_text(str(tmp_path), r"return \d")
    assert "a.py:2: return 1" in out
    assert "b.py:2: return 2" in out


def test_search_text_sem_match_devolve_mensagem_vazia(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    assert ferramenta_search_text(str(tmp_path), "nao_existe") == "(nenhum resultado)"


def test_search_text_ignora_dirs_ignorados(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("achar_isto")
    (tmp_path / "real.py").write_text("achar_isto\n")
    out = ferramenta_search_text(str(tmp_path), "achar_isto")
    assert "real.py" in out
    assert ".git" not in out


def test_search_text_regex_invalido_levanta_erro(tmp_path):
    with pytest.raises(FerramentaErro, match="regex"):
        ferramenta_search_text(str(tmp_path), "(")


def test_find_files_acha_por_glob(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "mod.py").write_text("")
    (tmp_path / "readme.md").write_text("")
    out = ferramenta_find_files(str(tmp_path), "**/*.py")
    assert out == "sub/mod.py"


def test_find_files_sem_match_devolve_mensagem_vazia(tmp_path):
    assert ferramenta_find_files(str(tmp_path), "*.rs") == "(nenhum resultado)"


# ── Allow/deny (mesmo padrão de api.build_tool_args, ADR-0028) ────────────────


def test_filtrar_ferramentas_sem_filtro_devolve_catalogo_completo():
    assert len(filtrar_ferramentas(None, None)) == 7


def test_filtrar_ferramentas_allowed_restringe():
    schemas = filtrar_ferramentas("read_file,list_dir", None)
    nomes = {s["function"]["name"] for s in schemas}
    assert nomes == {"read_file", "list_dir"}


def test_filtrar_ferramentas_denied_remove():
    schemas = filtrar_ferramentas(None, "run_command")
    nomes = {s["function"]["name"] for s in schemas}
    assert "run_command" not in nomes
    assert len(nomes) == 6


# ── Dispatch de tool call ─────────────────────────────────────────────────────


def test_executar_tool_call_despacha_por_nome(tmp_path):
    (tmp_path / "x.txt").write_text("conteúdo")
    chamada = {"function": {"name": "read_file", "arguments": {"path": "x.txt"}}}
    assert executar_tool_call(str(tmp_path), chamada) == "conteúdo"


def test_executar_tool_call_aceita_arguments_como_string_json(tmp_path):
    (tmp_path / "x.txt").write_text("conteúdo")
    chamada = {"function": {"name": "read_file", "arguments": '{"path": "x.txt"}'}}
    assert executar_tool_call(str(tmp_path), chamada) == "conteúdo"


def test_executar_tool_call_ferramenta_desconhecida(tmp_path):
    chamada = {"function": {"name": "apagar_tudo", "arguments": {}}}
    with pytest.raises(FerramentaErro, match="desconhecida"):
        executar_tool_call(str(tmp_path), chamada)


def test_executar_tool_call_json_invalido(tmp_path):
    chamada = {"function": {"name": "read_file", "arguments": "{not json"}}
    with pytest.raises(FerramentaErro, match="JSON"):
        executar_tool_call(str(tmp_path), chamada)


# ── Loop de tool-calling (rodar_loop) ─────────────────────────────────────────


def test_rodar_loop_resposta_direta_sem_tools_emite_texto_e_done():
    eventos = []

    def fake_chamar(endpoint, modelo, messages, tools, timeout):
        return {"message": {"content": "Pronto, sem nada a fazer.", "tool_calls": []}}

    rodar_loop(
        "explique X",
        system_prompt="sys",
        cwd="/tmp",
        modelo="llama3.1",
        endpoint="http://x:11434",
        chamar_fn=fake_chamar,
        on_evento=eventos.append,
    )
    tipos = [e["type"] for e in eventos]
    assert tipos == ["assistant", "done"]
    assert eventos[0]["message"]["content"][0]["text"] == "Pronto, sem nada a fazer."


def test_rodar_loop_executa_tool_call_e_continua_ate_resposta_final(tmp_path):
    (tmp_path / "f.txt").write_text("olá mundo")
    eventos = []
    chamadas = {"n": 0}

    def fake_chamar(endpoint, modelo, messages, tools, timeout):
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            return {
                "message": {
                    "content": "",
                    "tool_calls": [
                        {"function": {"name": "read_file", "arguments": {"path": "f.txt"}}}
                    ],
                }
            }
        # 2º turno: já viu o resultado da tool (via messages) e responde final
        assert any(
            m.get("role") == "tool" and "olá mundo" in m.get("content", "") for m in messages
        )
        return {"message": {"content": "Lido com sucesso.", "tool_calls": []}}

    rodar_loop(
        "leia f.txt",
        system_prompt="sys",
        cwd=str(tmp_path),
        modelo="llama3.1",
        endpoint="http://x:11434",
        chamar_fn=fake_chamar,
        on_evento=eventos.append,
    )
    tipos = [e["type"] for e in eventos]
    assert tipos == ["assistant", "assistant", "done"]
    assert chamadas["n"] == 2


def test_rodar_loop_erro_de_tool_vira_warning_nao_fatal(tmp_path):
    eventos = []
    chamadas = {"n": 0}

    def fake_chamar(endpoint, modelo, messages, tools, timeout):
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            return {
                "message": {
                    "content": "",
                    "tool_calls": [
                        {"function": {"name": "read_file", "arguments": {"path": "nao-existe.txt"}}}
                    ],
                }
            }
        return {"message": {"content": "Tentei, não achei o arquivo.", "tool_calls": []}}

    rodar_loop(
        "leia nao-existe.txt",
        system_prompt="sys",
        cwd=str(tmp_path),
        modelo="llama3.1",
        endpoint="http://x:11434",
        chamar_fn=fake_chamar,
        on_evento=eventos.append,
    )
    tipos = [e["type"] for e in eventos]
    assert "warning" in tipos
    assert "error" not in tipos  # não deve terminar o run como fatal
    assert tipos[-1] == "done"


def test_rodar_loop_limite_de_turnos_encerra_com_warning_e_done():
    eventos = []

    def sempre_chama_tool(endpoint, modelo, messages, tools, timeout):
        return {
            "message": {
                "content": "",
                "tool_calls": [{"function": {"name": "list_dir", "arguments": {}}}],
            }
        }

    rodar_loop(
        "faça algo",
        system_prompt="sys",
        cwd="/tmp",
        modelo="llama3.1",
        endpoint="http://x:11434",
        chamar_fn=sempre_chama_tool,
        on_evento=eventos.append,
        max_turnos=3,
    )
    tipos = [e["type"] for e in eventos]
    assert tipos.count("done") == 1
    assert "warning" in tipos
    assert tipos[-1] == "done"


def test_rodar_loop_respeita_allowed_tools(tmp_path):
    vistos = {}

    def fake_chamar(endpoint, modelo, messages, tools, timeout):
        vistos["tools"] = tools
        return {"message": {"content": "ok", "tool_calls": []}}

    rodar_loop(
        "tarefa",
        system_prompt="sys",
        cwd=str(tmp_path),
        modelo="llama3.1",
        endpoint="http://x:11434",
        chamar_fn=fake_chamar,
        allowed_tools="read_file,list_dir",
    )
    nomes = {t["function"]["name"] for t in vistos["tools"]}
    assert nomes == {"read_file", "list_dir"}


def test_rodar_loop_falha_de_rede_propaga_fatal():
    def fake_chamar(endpoint, modelo, messages, tools, timeout):
        raise OllamaIndisponivel("ollama: connection refused")

    with pytest.raises(OllamaIndisponivel):
        rodar_loop(
            "tarefa",
            system_prompt="sys",
            cwd="/tmp",
            modelo="llama3.1",
            endpoint="http://x:11434",
            chamar_fn=fake_chamar,
        )
