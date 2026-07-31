"""Claude Code compatibility: skill install targets, repo skill parity, MCP config format."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from draftpaper_cli import skill_sync
from draftpaper_cli.mcp_install import mcp_install

REPO_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_DIR = REPO_ROOT / "draftpaper_cli" / "resources" / "draftpaper_workflow"
REPO_SKILL_COPIES = (
    REPO_ROOT / ".claude" / "skills" / "draftpaper-workflow",
    REPO_ROOT / "codex_skills" / "draftpaper-workflow",
)


def _normalized_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")).hexdigest()


def test_repo_skill_copies_match_canonical_skill() -> None:
    canonical = _normalized_sha(CANONICAL_DIR / "SKILL.md")
    for copy_dir in REPO_SKILL_COPIES:
        copy = copy_dir / "SKILL.md"
        assert copy.is_file(), f"missing repo skill copy: {copy}"
        assert _normalized_sha(copy) == canonical, f"skill copy drifted from canonical resource: {copy}"


def test_repo_skill_contracts_match_canonical_contract() -> None:
    canonical = json.loads((CANONICAL_DIR / "contract.json").read_text(encoding="utf-8"))
    for copy_dir in REPO_SKILL_COPIES:
        copy = copy_dir / "contract.json"
        assert copy.is_file(), f"missing repo contract copy: {copy}"
        assert json.loads(copy.read_text(encoding="utf-8")) == canonical, f"contract copy drifted: {copy}"


def test_default_destination_codex_unchanged(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex_home"))
    destination = skill_sync.default_skill_destination()
    assert destination == tmp_path / "codex_home" / "skills" / skill_sync.SKILL_ID


def test_default_destination_claude(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude_home"))
    destination = skill_sync.default_skill_destination("claude")
    assert destination == tmp_path / "claude_home" / "skills" / skill_sync.SKILL_ID


def test_unsupported_agent_rejected() -> None:
    with pytest.raises(ValueError):
        skill_sync.default_skill_destination("copilot")
    with pytest.raises(ValueError):
        skill_sync.install_skill(agent="copilot")


def test_install_and_doctor_claude_agent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude_home"))
    result = skill_sync.install_skill(agent="claude")
    assert result["status"] == "installed"
    assert result["agent"] == "claude"
    installed = Path(result["destination"]) / "SKILL.md"
    assert installed.is_file()
    assert hashlib.sha256(installed.read_bytes()).hexdigest() == skill_sync.canonical_skill_hash()
    doctor = skill_sync.skill_doctor(agent="claude")
    assert doctor["status"] == "passed"
    assert doctor["agent"] == "claude"


def test_blocked_install_names_claude_repair_command(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude_home"))
    first = skill_sync.install_skill(agent="claude")
    skill_path = Path(first["destination"]) / "SKILL.md"
    skill_path.write_text("tampered", encoding="utf-8")
    blocked = skill_sync.install_skill(agent="claude")
    assert blocked["status"] == "blocked"
    assert "--agent claude" in blocked["next_command"]
    forced = skill_sync.install_skill(agent="claude", force=True)
    assert forced["status"] == "installed"


def test_canonical_description_is_agent_neutral() -> None:
    text = (CANONICAL_DIR / "SKILL.md").read_text(encoding="utf-8")
    frontmatter = text.split("---", 2)[1]
    assert "Claude Code" in frontmatter
    assert "Codex" in frontmatter


def test_mcp_install_writes_claude_compatible_config(tmp_path: Path) -> None:
    output = tmp_path / "generated_mcp.json"
    result = mcp_install(output)
    assert result["status"] == "written"
    payload = json.loads(output.read_text(encoding="utf-8"))
    server = payload["mcpServers"]["draftpaper-loop"]
    assert server["type"] == "stdio"
    assert server["command"] == "python"
    assert server["args"] == ["-m", "draftpaper_cli.mcp.server"]


def test_repo_root_mcp_json_matches_generated_shape() -> None:
    committed = json.loads((REPO_ROOT / ".mcp.json").read_text(encoding="utf-8"))
    server = committed["mcpServers"]["draftpaper-loop"]
    assert server.get("type", server.get("transport")) == "stdio"
    assert server["command"] == "python"
    assert server["args"] == ["-m", "draftpaper_cli.mcp.server"]


def test_claude_project_assets_exist() -> None:
    assert (REPO_ROOT / "CLAUDE.md").is_file()
    assert (REPO_ROOT / ".claude" / "settings.json").is_file()
    for command in ("dp-status", "dp-continue", "dp-doctor", "dp-review"):
        assert (REPO_ROOT / ".claude" / "commands" / f"{command}.md").is_file()
    settings = json.loads((REPO_ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    denied = " ".join(settings["permissions"]["deny"])
    assert "project.json" in denied
    assert "project_passport.yaml" in denied
