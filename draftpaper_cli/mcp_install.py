"""Portable MCP configuration generation and deterministic diagnostics."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

from .execution_policy import command_allowed_via_mcp
from .command_registry import COMMAND_SPECS
from .mcp.service import public_tool_names
from .skill_sync import skill_doctor


def mcp_install(output: str | Path) -> dict[str, Any]:
    destination = Path(output).expanduser().resolve()
    payload = {
        "mcpServers": {
            "draftpaper-loop": {
                "command": "python",
                "args": ["-m", "draftpaper_cli.mcp.server"],
                "transport": "stdio"
            }
        }
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"status": "written", "path": str(destination), "portable_cwd": True, "tool_count": len(public_tool_names())}


def mcp_doctor() -> dict[str, Any]:
    dependency = importlib.util.find_spec("mcp") is not None and importlib.util.find_spec("pydantic") is not None
    exposed = [name for name, spec in COMMAND_SPECS.items() if command_allowed_via_mcp(spec)[0]]
    protected = [name for name, spec in COMMAND_SPECS.items() if not command_allowed_via_mcp(spec)[0]]
    checks = {
        "optional_dependencies_available": dependency,
        "tool_count_in_range": 8 <= len(public_tool_names()) <= 12,
        "no_arbitrary_shell_tool": all("shell" not in name for name in public_tool_names()),
        "no_raw_write_tool": all("write_file" not in name for name in public_tool_names()),
        "no_sql_or_git_push_tool": all("sql" not in name and "git_push" not in name for name in public_tool_names()),
        "protected_commands_excluded": all(not COMMAND_SPECS[name].mcp_exposed for name in protected),
        "skill_current": skill_doctor().get("status") == "passed",
    }
    return {
        "schema_version": "dpl.mcp_doctor.v1",
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "tools": public_tool_names(),
        "mcp_eligible_command_count": len(exposed),
        "protected_command_count": len(protected),
        "next_commands": [command for command in [None if dependency else "python -m pip install -e .[mcp]", None if checks["skill_current"] else "draftpaper install-skill --force"] if command],
    }
