from __future__ import annotations

import threading
import time
from contextlib import AbstractContextManager, nullcontext
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rich.console import Console

_KIND_LABELS = {
    "thinking": "[bold]NULLAIN pensando...[/bold]",
    "tool_call": "[bold]Executando ferramenta...[/bold]",
    "confirmation": "[bold]Aguardando confirmação...[/bold]",
}


def _create_effect(kind: str):
    from agents_are_thinking import BrailleBreathe, BrailleHeartbeat, ShadeScanner

    effects = {
        "thinking": BrailleBreathe,
        "tool_call": ShadeScanner,
        "confirmation": BrailleHeartbeat,
    }
    return effects[kind]()


class _AnimatedStatus(AbstractContextManager["_AnimatedStatus"]):
    def __init__(self, console: Console, kind: str, label: str) -> None:
        self._console = console
        self._kind = kind
        self._label = label
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._live = None
        self._fallback: AbstractContextManager[object] | None = None
        self._using_fallback = False

    def __enter__(self) -> _AnimatedStatus:
        try:
            from rich.live import Live

            effect = _create_effect(self._kind)
            self._live = Live("", console=self._console, refresh_per_second=16, transient=True)
            self._live.__enter__()

            def animate() -> None:
                while not self._stop.is_set():
                    frame = effect.step()
                    self._live.update(f"{frame} {self._label}")
                    time.sleep(0.0625)

            self._thread = threading.Thread(target=animate, daemon=True)
            self._thread.start()
            return self
        except Exception:
            self._using_fallback = True
            self._fallback = self._console.status(self._label)
            self._fallback.__enter__()
            return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool | None:
        if self._using_fallback:
            if self._fallback is not None:
                return self._fallback.__exit__(exc_type, exc_val, exc_tb)
            return None

        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        if self._live is not None:
            return self._live.__exit__(exc_type, exc_val, exc_tb)
        return None


def status(
    console: Console | None,
    kind: str,
    *,
    text: str | None = None,
) -> AbstractContextManager[object]:
    if console is None:
        return nullcontext()

    label = text or _KIND_LABELS.get(kind, "[bold]NULLAIN...[/bold]")

    if kind not in _KIND_LABELS:
        return console.status(label)

    try:
        return _AnimatedStatus(console, kind, label)
    except Exception:
        return console.status(label)