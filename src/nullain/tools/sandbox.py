"""Política de sandbox para run_command (deny-list + allowlist opcional)."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SandboxDecision:
    allowed: bool
    reason: str = ""


# Padrões perigosos (case-insensitive). Sempre bloqueados em modo sandbox.
DEFAULT_DENY_PATTERNS: tuple[str, ...] = (
    r"rm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+)?/\s*$",
    r"rm\s+-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*.*/\s*",
    r"rm\s+-rf\s+/",
    r"rmdir\s+/s\s+/q\s+[a-z]:\\",
    r"del\s+/[sfq]+\s+[a-z]:\\",
    r"format\s+[a-z]:",
    r"mkfs\.",
    r"dd\s+if=",
    r":\(\)\s*\{\s*:\|:\s*&\s*\}\s*;",  # fork bomb
    r"shutdown\b",
    r"reboot\b",
    r"init\s+0",
    r"diskpart\b",
    r"Remove-Item\s+.*-Recurse.*[A-Z]:\\",
    r"Invoke-Expression\s*\(?\s*\$",
    r"iex\s*\(?\s*\(",
    r"curl\s+.*\|\s*(ba)?sh",
    r"wget\s+.*\|\s*(ba)?sh",
    r"chmod\s+-R\s+777\s+/",
    r"chown\s+-R\s+.*\s+/",
    r">\s*/dev/sd",
    r"reg\s+delete\s+",
    r"net\s+user\s+\w+\s+/add",
)


def _compile_patterns(patterns: list[str] | tuple[str, ...]) -> list[re.Pattern[str]]:
    compiled: list[re.Pattern[str]] = []
    for pattern in patterns:
        try:
            compiled.append(re.compile(pattern, re.IGNORECASE))
        except re.error:
            continue
    return compiled


def evaluate_command(
    cmd: str,
    *,
    deny_patterns: list[str] | tuple[str, ...] | None = None,
    allowlist: list[str] | tuple[str, ...] | None = None,
    enabled: bool = True,
) -> SandboxDecision:
    """Avalia se o comando pode rodar sob a política de sandbox."""
    if not enabled:
        return SandboxDecision(True, "sandbox desligado")

    text = (cmd or "").strip()
    if not text:
        return SandboxDecision(False, "comando vazio")

    deny = _compile_patterns(deny_patterns or DEFAULT_DENY_PATTERNS)
    for pattern in deny:
        if pattern.search(text):
            return SandboxDecision(
                False,
                f"bloqueado pela deny-list do sandbox (padrão: {pattern.pattern})",
            )

    # Allowlist opcional: se configurada, o comando deve casar com ao menos um prefixo/regex
    if allowlist:
        allowed_hit = False
        for rule in allowlist:
            rule = rule.strip()
            if not rule:
                continue
            if rule.startswith("re:"):
                try:
                    if re.search(rule[3:], text, re.IGNORECASE):
                        allowed_hit = True
                        break
                except re.error:
                    continue
            else:
                # Prefixo literal (case-insensitive)
                if text.lower().startswith(rule.lower()):
                    allowed_hit = True
                    break
        if not allowed_hit:
            return SandboxDecision(
                False,
                "comando fora da allowlist do sandbox (NULLAIN_SHELL_ALLOWLIST)",
            )

    return SandboxDecision(True, "ok")
