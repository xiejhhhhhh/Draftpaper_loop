"""Install and diagnose the canonical Draftpaper-loop workflow skill for coding agents."""

from __future__ import annotations

import hashlib
import json
import os
from importlib import resources
from pathlib import Path
from typing import Any


SKILL_ID = "draftpaper-workflow"
DEFAULT_AGENT = "codex"
SUPPORTED_AGENTS = ("codex", "claude")


def _resource_root():
    return resources.files("draftpaper_cli").joinpath("resources", "draftpaper_workflow")


def canonical_skill_bytes() -> bytes:
    return _resource_root().joinpath("SKILL.md").read_bytes()


def canonical_contract() -> dict[str, Any]:
    return json.loads(_resource_root().joinpath("contract.json").read_text(encoding="utf-8"))


def canonical_skill_hash() -> str:
    return hashlib.sha256(canonical_skill_bytes()).hexdigest()


def _normalize_agent(agent: str | None) -> str:
    value = (agent or DEFAULT_AGENT).strip().lower()
    if value not in SUPPORTED_AGENTS:
        raise ValueError(f"Unsupported agent '{agent}'. Supported agents: {', '.join(SUPPORTED_AGENTS)}.")
    return value


def default_skill_destination(agent: str | None = None) -> Path:
    resolved = _normalize_agent(agent)
    if resolved == "claude":
        claude_home = Path(os.environ.get("CLAUDE_CONFIG_DIR") or (Path.home() / ".claude"))
        return claude_home / "skills" / SKILL_ID
    codex_home = Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))
    return codex_home / "skills" / SKILL_ID


def _repair_flag(agent: str) -> str:
    return "" if agent == DEFAULT_AGENT else f" --agent {agent}"


def install_skill(destination: str | Path | None = None, *, force: bool = False, agent: str | None = None) -> dict[str, Any]:
    resolved_agent = _normalize_agent(agent)
    target = Path(destination).expanduser() if destination else default_skill_destination(resolved_agent)
    target = target.resolve()
    target.mkdir(parents=True, exist_ok=True)
    skill_path = target / "SKILL.md"
    contract_path = target / "contract.json"
    expected = canonical_skill_hash()
    existing = hashlib.sha256(skill_path.read_bytes()).hexdigest() if skill_path.is_file() else None
    if existing and existing != expected and not force:
        return {
            "schema_version": "dpl.skill_install.v1",
            "status": "blocked",
            "reason": "installed_skill_differs",
            "agent": resolved_agent,
            "destination": str(target),
            "installed_sha256": existing,
            "canonical_sha256": expected,
            "next_command": f'draftpaper install-skill{_repair_flag(resolved_agent)} --destination "{target}" --force',
        }
    skill_path.write_bytes(canonical_skill_bytes())
    contract_path.write_text(json.dumps(canonical_contract(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "schema_version": "dpl.skill_install.v1",
        "status": "installed",
        "skill_id": SKILL_ID,
        "skill_version": canonical_contract()["skill_version"],
        "agent": resolved_agent,
        "destination": str(target),
        "sha256": expected,
    }


def skill_doctor(destination: str | Path | None = None, agent: str | None = None) -> dict[str, Any]:
    resolved_agent = _normalize_agent(agent)
    target = Path(destination).expanduser().resolve() if destination else default_skill_destination(resolved_agent).resolve()
    skill_path = target / "SKILL.md"
    expected = canonical_skill_hash()
    actual = hashlib.sha256(skill_path.read_bytes()).hexdigest() if skill_path.is_file() else None
    contract = canonical_contract()
    status = "passed" if actual == expected else "failed"
    reason = None if status == "passed" else ("skill_missing" if actual is None else "skill_hash_mismatch")
    return {
        "schema_version": "dpl.skill_doctor.v1",
        "status": status,
        "skill_id": SKILL_ID,
        "agent": resolved_agent,
        "canonical_version": contract["skill_version"],
        "canonical_sha256": expected,
        "installed_path": str(skill_path),
        "installed_sha256": actual,
        "reason": reason,
        "next_command": None if status == "passed" else f'draftpaper install-skill{_repair_flag(resolved_agent)} --destination "{target}" --force',
    }
