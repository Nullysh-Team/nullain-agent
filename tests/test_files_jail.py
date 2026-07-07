from pathlib import Path

import pytest

from nullain.tools import files


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    monkeypatch.setattr(files, "WORKSPACE_ROOT", root)
    return root


def test_relative_path_inside_workspace(workspace: Path):
    (workspace / "hello.txt").write_text("ok", encoding="utf-8")
    (workspace / "subdir").mkdir()

    listing = files.list_files(".")
    assert "[FILE] hello.txt" in listing
    assert "[DIR] subdir" in listing

    content = files.read_file("hello.txt")
    assert content == "ok"


def test_escape_relative_path(workspace: Path):
    result = files.read_file("../escape.txt")
    assert "fora do workspace" in result

    write_result = files.write_file(
        "../escape.txt",
        "secret",
        confirm=lambda _: True,
    )
    assert "fora do workspace" in write_result
    assert not (workspace.parent / "escape.txt").exists()


def test_absolute_path_outside_workspace(workspace: Path):
    drive_root = Path(workspace.anchor)
    outside = drive_root / "outside_nullain_jail_test.txt"
    result = files.read_file(str(outside))
    assert "fora do workspace" in result


def test_read_binary_file_returns_error(workspace: Path):
    target = workspace / "binary.bin"
    target.write_bytes(b"\xff\xfe\xfd\x00")
    result = files.read_file("binary.bin")
    assert "Erro:" in result
    assert "não foi possível ler" in result


def test_write_file_confirm_true_creates_file(workspace: Path):
    result = files.write_file(
        "created.txt",
        "conteúdo",
        confirm=lambda _: True,
    )
    assert result.startswith("Arquivo gravado:")
    assert (workspace / "created.txt").read_text(encoding="utf-8") == "conteúdo"


def test_write_file_confirm_false_does_not_create(workspace: Path):
    result = files.write_file(
        "denied.txt",
        "conteúdo",
        confirm=lambda _: False,
    )
    assert result == "Operação cancelada pelo usuário."
    assert not (workspace / "denied.txt").exists()