from nullain.tools import files
from nullain.tools.shell import run_command


def test_run_command_without_confirm_returns_error(tmp_path, monkeypatch):
    monkeypatch.setattr(files, "WORKSPACE_ROOT", tmp_path.resolve())
    monkeypatch.setattr(
        "nullain.tools.shell.subprocess.run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("subprocess não deve ser chamado")
        ),
    )

    result = run_command("echo x", confirm=None)
    assert "nenhum confirmador foi fornecido" in result


def test_write_file_without_confirm_returns_error(tmp_path, monkeypatch):
    monkeypatch.setattr(files, "WORKSPACE_ROOT", tmp_path.resolve())

    result = files.write_file("blocked.txt", "x", confirm=None)
    assert "nenhum confirmador foi fornecido" in result
    assert not (tmp_path / "blocked.txt").exists()


def test_run_command_denied_by_user(tmp_path, monkeypatch):
    monkeypatch.setattr(files, "WORKSPACE_ROOT", tmp_path.resolve())
    monkeypatch.setattr(
        "nullain.tools.shell.subprocess.run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("subprocess não deve ser chamado")
        ),
    )

    result = run_command("echo x", confirm=lambda _: False)
    assert result == "Operação cancelada pelo usuário."