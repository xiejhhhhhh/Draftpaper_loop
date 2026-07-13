"""Shared command/MCP execution policy and privacy-safe diagnostics."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .command_registry import CommandSpec


RISK_LEVELS = {
    "read",
    "write_project",
    "execute_science",
    "network_external",
    "human_checkpoint",
    "destructive_admin",
}
MCP_FORBIDDEN_RISKS = {"human_checkpoint", "destructive_admin"}
_SECRET_PATTERN = re.compile(
    r"(?i)(api[_-]?key|token|password|passwd|secret|authorization|cookie)(\s*[:=]\s*)([^\s,;]+)"
)
_EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_WINDOWS_PATH = re.compile(r"(?i)(?<![\w])(?:[A-Z]:\\[^\s\"']+|\\\\[^\s\"']+)")


@dataclass(frozen=True)
class ExecutionPolicy:
    command: str
    risk_level: str
    resource_class: str
    timeout_seconds: int
    idempotency: str
    parallel_safe: bool
    confirmation_policy: str
    allowed_read_globs: tuple[str, ...]
    allowed_write_globs: tuple[str, ...]
    forbidden_globs: tuple[str, ...]
    mcp_exposed: bool

    @classmethod
    def from_spec(cls, spec: CommandSpec) -> "ExecutionPolicy":
        if spec.risk_level not in RISK_LEVELS:
            raise ValueError(f"Unknown command risk level: {spec.risk_level}")
        return cls(
            command=spec.name,
            risk_level=spec.risk_level,
            resource_class=spec.resource_class,
            timeout_seconds=max(1, int(spec.timeout_seconds)),
            idempotency=spec.idempotency,
            parallel_safe=bool(spec.parallel_safe),
            confirmation_policy=spec.confirmation_policy,
            allowed_read_globs=tuple(spec.allowed_read_globs),
            allowed_write_globs=tuple(spec.allowed_write_globs),
            forbidden_globs=tuple(spec.forbidden_globs),
            mcp_exposed=bool(spec.mcp_exposed and spec.risk_level not in MCP_FORBIDDEN_RISKS),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "risk_level": self.risk_level,
            "resource_class": self.resource_class,
            "timeout_seconds": self.timeout_seconds,
            "idempotency": self.idempotency,
            "parallel_safe": self.parallel_safe,
            "confirmation_policy": self.confirmation_policy,
            "allowed_read_globs": list(self.allowed_read_globs),
            "allowed_write_globs": list(self.allowed_write_globs),
            "forbidden_globs": list(self.forbidden_globs),
            "mcp_exposed": self.mcp_exposed,
        }


def command_allowed_via_mcp(spec: CommandSpec) -> tuple[bool, str | None]:
    policy = ExecutionPolicy.from_spec(spec)
    if not policy.mcp_exposed:
        return False, "command_not_exposed"
    if policy.risk_level in MCP_FORBIDDEN_RISKS:
        return False, "protected_human_or_admin_action"
    return True, None


def redact_sensitive(value: Any) -> Any:
    """Recursively redact credentials, private locators, email and absolute paths."""
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(token in lowered for token in ("password", "passwd", "secret", "token", "api_key", "authorization", "cookie")):
                redacted[str(key)] = "<redacted>"
            else:
                redacted[str(key)] = redact_sensitive(item)
        return redacted
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, tuple):
        return [redact_sensitive(item) for item in value]
    if not isinstance(value, str):
        return value
    text = _SECRET_PATTERN.sub(lambda match: f"{match.group(1)}{match.group(2)}<redacted>", value)
    text = _EMAIL_PATTERN.sub("<redacted-email>", text)
    text = _WINDOWS_PATH.sub("<redacted-path>", text)
    return text


def sanitized_environment(source: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return the small environment allowlist permitted for child processes."""
    env = dict(source or os.environ)
    allowed = {
        "PATH", "PYTHONPATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME", "USERPROFILE",
        "LANG", "LC_ALL", "MPLBACKEND", "CUDA_VISIBLE_DEVICES",
    }
    return {key: value for key, value in env.items() if key.upper() in allowed}
