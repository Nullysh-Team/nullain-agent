import builtins
import io

from rich.console import Console

from nullain.ui.spinner import status


def test_status_falls_back_when_agents_are_thinking_unavailable(monkeypatch):
    console = Console(file=io.StringIO(), force_terminal=True, width=120)
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "agents_are_thinking":
            raise ImportError("agents-are-thinking indisponível")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with status(console, "thinking"):
        pass