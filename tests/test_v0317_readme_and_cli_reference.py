from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from draftpaper_cli.command_registry import COMMAND_SPECS
from draftpaper_cli.toml_compat import tomllib


EXPECTED_H2 = {
    "README.md": [
        "## Project Scope and Current Release",
        "## Core Research Capabilities",
        "## Quick Start",
        "## End-to-End Research Workflow",
        "## Discipline Plugins and Capability Extension",
        "## Figures, Evidence, and Scientific Writing",
        "## Literature, Citations, and Independent Review",
        "## Final Completion, Precise Revision, and Release",
        "## Installation, Agents, and Daily Operation",
        "## Project Layout, Evidence Contracts, and Engineering Boundaries",
        "## Contributors, License, Commercial Use, And Contact",
        "## Support",
        "## Star History",
        "## Recent Updates",
    ],
    "README.zh-CN.md": [
        "## \u9879\u76ee\u5b9a\u4f4d\u4e0e\u5f53\u524d\u7248\u672c",
        "## \u6838\u5fc3\u79d1\u7814\u80fd\u529b",
        "## \u5feb\u901f\u5f00\u59cb",
        "## \u5b8c\u6574\u79d1\u7814\u5de5\u4f5c\u6d41",
        "## \u5b66\u79d1\u63d2\u4ef6\u4e0e\u79d1\u7814\u80fd\u529b\u6269\u5c55",
        "## \u56fe\u8868\u3001\u8bc1\u636e\u4e0e\u79d1\u5b66\u5199\u4f5c",
        "## \u6587\u732e\u3001\u5f15\u7528\u4e0e\u72ec\u7acb\u5ba1\u7a3f",
        "## \u6700\u7ec8\u7a3f\u8865\u5168\u3001\u5b9a\u70b9\u4fee\u8ba2\u4e0e\u53d1\u5e03",
        "## \u5b89\u88c5\u3001Agent \u4e0e\u65e5\u5e38\u64cd\u4f5c",
        "## \u9879\u76ee\u76ee\u5f55\u3001\u8bc1\u636e\u5408\u540c\u4e0e\u5de5\u7a0b\u8fb9\u754c",
        "## \u8d21\u732e\u8005\u3001\u8bb8\u53ef\u8bc1\u3001\u5546\u4e1a\u4f7f\u7528\u548c\u8054\u7cfb\u65b9\u5f0f",
        "## \u6253\u8d4f",
        "## Star History",
        "## \u6700\u8fd1\u66f4\u65b0",
    ],
}


def _h2_entries(content: str) -> list[tuple[str, int, int]]:
    entries: list[tuple[str, int, int]] = []
    offset = 0
    fenced = False
    for line in content.splitlines(keepends=True):
        if line.startswith(("```", "~~~")):
            fenced = not fenced
        elif not fenced and line.startswith("## "):
            entries.append((line.rstrip("\r\n"), offset, offset + len(line)))
        offset += len(line)
    return entries


def _h2_headings(content: str) -> list[str]:
    return [heading for heading, _, _ in _h2_entries(content)]


def _section(content: str, heading: str) -> str:
    entries = _h2_entries(content)
    for index, (candidate, _, end) in enumerate(entries):
        if candidate == heading:
            next_start = entries[index + 1][1] if index + 1 < len(entries) else len(content)
            return content[end:next_start]
    raise ValueError(f"missing H2 heading: {heading}")


def test_section_uses_real_h2_boundaries() -> None:
    content = "```text\n## Target\n```\n\n## Target\nactual section\n\n## Next\nnext section\n"
    assert _section(content, "## Target") == "actual section\n\n"


def test_readmes_preserve_the_overall_project_guide_and_current_release() -> None:
    version = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    for name, headings in EXPECTED_H2.items():
        content = Path(name).read_text(encoding="utf-8")
        assert _h2_headings(content) == headings
        assert f"v{version}" in content
        assert "prepare-manuscript-completion" in content
        assert "preview-manuscript-completion" in content
        assert "apply-manuscript-completion" in content
        assert "docs/cli_reference.md" in content
        assert "docs/command_risk_matrix.md" in content
        assert "docs/token_cost_reporting" in content
        assert 'pip install -e ".[fulltext]"' in content
        assert "pip install -e third_party\\paper-fetch-skill" not in content
        assert "python -m pytest" in content
        lines = content.splitlines()
        assert any(line.startswith("### v0.31.1-v0.32.0") for line in lines)
        for patch_version in range(1, 10):
            standalone_prefixes = (
                f"### v0.31.{patch_version} ",
                f"### v0.31.{patch_version}(",
                f"### v0.31.{patch_version}\uff08",
            )
            assert not any(line.startswith(standalone_prefixes) for line in lines)


def test_readmes_front_load_framework_capabilities_and_keep_operations_later() -> None:
    capability_ranges = ("v0.1-v0.13", "v0.14-v0.20", "v0.21-v0.28", "v0.28.1-v0.33")
    settings = (
        ("README.md", "## Project Scope and Current Release", "## Core Research Capabilities", "## Quick Start", "## End-to-End Research Workflow", "## Installation, Agents, and Daily Operation"),
        ("README.zh-CN.md", "## \u9879\u76ee\u5b9a\u4f4d\u4e0e\u5f53\u524d\u7248\u672c", "## \u6838\u5fc3\u79d1\u7814\u80fd\u529b", "## \u5feb\u901f\u5f00\u59cb", "## \u5b8c\u6574\u79d1\u7814\u5de5\u4f5c\u6d41", "## \u5b89\u88c5\u3001Agent \u4e0e\u65e5\u5e38\u64cd\u4f5c"),
    )
    for name, current_heading, capabilities_heading, quick_start_heading, workflow_heading, operations_heading in settings:
        content = Path(name).read_text(encoding="utf-8")
        current = _section(content, current_heading)
        capabilities = _section(content, capabilities_heading)
        quick_start = _section(content, quick_start_heading)
        workflow = _section(content, workflow_heading)
        operations = _section(content, operations_heading)

        assert len([line for line in current.splitlines() if line.startswith("-")]) >= 8
        assert all(version_range in capabilities for version_range in capability_ranges)
        assert "python3 -m venv .venv" in quick_start
        assert "py -3 -m venv .venv" in quick_start
        assert 'pip install -e ".[plotting]"' in quick_start
        assert "run-pipeline" in quick_start
        assert "Results" in workflow
        assert "Discussion" in workflow
        assert "citation audit" in workflow
        assert "docs/cli_reference.md" in operations
        assert "docs/command_risk_matrix.md" in operations
        assert "docs/token_cost_reporting" in operations


def test_readmes_bind_capability_anchors_without_a_release_scoped_status_table() -> None:
    matrix = json.loads(Path("docs/capability_truth_matrix.json").read_text(encoding="utf-8"))
    for name in ("README.md", "README.zh-CN.md"):
        content = Path(name).read_text(encoding="utf-8")
        assert "## Implementation Status" not in content
        assert "## \u5f53\u524d\u5b9e\u73b0\u72b6\u6001" not in content
        for record in matrix["capabilities"]:
            marker = f"<!-- {record['readme_anchor']} -->"
            closing = f"<!-- /{record['readme_anchor']} -->"
            assert content.count(marker) == 1
            assert content.count(closing) == 1
            bounded = content.split(marker, 1)[1].split(closing, 1)[0]
            assert re.sub(r"\s+", " ", bounded).strip()


def test_readmes_keep_workflow_release_order_and_result_support_boundary() -> None:
    ordered = {
        "README.md": [
            "final author completion and precise revisions",
            "final citation audit",
            "two independent blind reviewers",
            "confirm one release hash",
        ],
        "README.zh-CN.md": [
            "\u6700\u7ec8\u4f5c\u8005\u8865\u5168\u548c\u5b9a\u70b9\u4fee\u8ba2",
            "\u6700\u7ec8 citation audit",
            "\u4e24\u4f4d\u72ec\u7acb\u76f2\u8bc4\u8005",
            "\u786e\u8ba4 release hash",
        ],
    }
    settings = (
        ("README.md", "## Project Scope and Current Release", "## End-to-End Research Workflow", "Current release: v", "whole result-support checkpoint"),
        ("README.zh-CN.md", "## \u9879\u76ee\u5b9a\u4f4d\u4e0e\u5f53\u524d\u7248\u672c", "## \u5b8c\u6574\u79d1\u7814\u5de5\u4f5c\u6d41", "\u5f53\u524d\u7248\u672c\uff1av", "\u6574\u4efd result-support checkpoint"),
    )
    for name, current_heading, workflow_heading, version_marker, result_support_marker in settings:
        content = Path(name).read_text(encoding="utf-8")
        assert version_marker in _section(content, current_heading)
        assert result_support_marker in content
        workflow = _section(content, workflow_heading)
        positions = [workflow.index(fragment) for fragment in ordered[name]]
        assert positions == sorted(positions)


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
    assert len(COMMAND_SPECS) == 211
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
