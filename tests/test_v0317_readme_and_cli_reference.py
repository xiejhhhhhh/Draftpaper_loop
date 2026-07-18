from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

from draftpaper_cli.command_registry import COMMAND_SPECS


def test_readmes_are_start_pages_not_monolithic_references() -> None:
    version = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    for name in ("README.md", "README.zh-CN.md"):
        content = Path(name).read_text(encoding="utf-8")
        size = len(content.encode("utf-8"))
        assert 8 * 1024 <= size <= 12 * 1024, (name, size)
        assert f"v{version}" in content
        assert "prepare-manuscript-completion" in content
        assert "preview-manuscript-completion" in content
        assert "apply-manuscript-completion" in content
        assert "docs/cli_reference.md" in content
        assert "python -m unittest" not in content


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
