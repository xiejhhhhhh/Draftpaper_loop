from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from draftpaper_cli.command_registry import COMMAND_SPECS
from draftpaper_cli.toml_compat import tomllib


def test_readmes_preserve_the_detailed_project_guide_and_current_release() -> None:
    version = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    required_sections = {
        "README.md": {
            "## What It Does",
            "## Loop Model",
            "## Key Features",
            "## Project Layout",
            "## Quick Start",
            "## Implementation Status",
            "## Recent Updates",
        },
        "README.zh-CN.md": {
            "## 功能概览",
            "## Loop 模型",
            "## 核心特性",
            "## 项目结构",
            "## 快速开始",
            "## 当前实现状态",
            "## 最近更新",
        },
    }
    for name, sections in required_sections.items():
        content = Path(name).read_text(encoding="utf-8")
        size = len(content.encode("utf-8"))
        assert size >= 64 * 1024, (name, size)
        assert sections <= set(content.splitlines())
        assert f"v{version}" in content
        assert "prepare-manuscript-completion" in content
        assert "preview-manuscript-completion" in content
        assert "apply-manuscript-completion" in content
        assert "docs/cli_reference.md" in content
        assert "docs/command_risk_matrix.md" in content
        assert "docs/token_cost_reporting" in content
        assert 'pip install -e ".[fulltext]"' in content
        assert "pip install -e third_party\\paper-fetch-skill" not in content
        assert "python -m pytest\n```" in content
        lines = content.splitlines()
        assert any(line.startswith("### v0.31.1-v0.32.0") for line in lines)
        for patch_version in range(1, 10):
            standalone_prefixes = (
                f"### v0.31.{patch_version} ",
                f"### v0.31.{patch_version}(",
                f"### v0.31.{patch_version}（",
            )
            assert not any(line.startswith(standalone_prefixes) for line in lines)


def test_readme_commands_are_registered() -> None:
    required = {
        "start",
        "status",
        "continue",
        "review",
        "revise",
        "doctor",
        "recover",
        "prepare-manuscript-completion",
        "preview-manuscript-completion",
        "apply-manuscript-completion",
        "review-final-manuscript",
        "confirm-final-manuscript",
    }
    assert required <= set(COMMAND_SPECS)
    for readme in ("README.md", "README.zh-CN.md"):
        text = Path(readme).read_text(encoding="utf-8")
        assert all(command in text for command in required)


def test_generated_cli_reference_matches_command_registry() -> None:
    from tools.generate_cli_reference import render_cli_reference

    expected = render_cli_reference()
    actual = Path("docs/cli_reference.md").read_text(encoding="utf-8")

    assert actual == expected
    assert expected.count("\n| `") == len(COMMAND_SPECS)
    assert len(COMMAND_SPECS) == 210
    assert "namespace adapter" in expected
    assert "human_checkpoint" in expected


def test_cli_reference_generator_uses_current_checkout(tmp_path: Path) -> None:
    output = tmp_path / "cli_reference.md"
    completed = subprocess.run(
        [sys.executable, "tools/generate_cli_reference.py", "--output", str(output)],
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert output.read_text(encoding="utf-8").count("\n| `") == len(COMMAND_SPECS)
