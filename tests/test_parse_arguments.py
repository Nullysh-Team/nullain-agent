from nullain.tools import execute_tool, parse_tool_arguments


def test_parse_empty_arguments():
    assert parse_tool_arguments("") == {}


def test_parse_valid_json():
    assert parse_tool_arguments('{"path": "a.txt"}') == {"path": "a.txt"}


def test_parse_invalid_json_returns_parse_error():
    result = parse_tool_arguments("{invalido")
    assert "__parse_error__" in result
    assert "JSON inválidos" in result["__parse_error__"]


def test_execute_tool_with_parse_error_does_not_run_tool():
    result = execute_tool(
        "list_files",
        {"__parse_error__": "Erro: argumentos JSON inválidos: teste"},
        confirm=lambda _: True,
    )
    assert result == "Erro: argumentos JSON inválidos: teste"