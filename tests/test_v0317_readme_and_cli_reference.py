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
        "## Current Release",
        "## How a Paper Reaches `main.pdf`",
        "## Guarantees and Human Control",
        "## Completing and Revising the Final Manuscript",
        "## What It Does",
        "## Loop Model",
        "## Key Features",
        "## Project Layout",
        "## Quick Start",
        "## Implementation Status",
        "## Research-Code Mining",
        "## Third-party Skills Integration",
        "## Contributors, License, Commercial Use, And Contact",
        "## Support",
        "## Recent Updates",
    ],
    "README.zh-CN.md": [
        "## 当前版本",
        "## 论文如何到达 `main.pdf`",
        "## 系统保证与人工控制",
        "## 补全与修订最终稿",
        "## 功能概览",
        "## Loop 模型",
        "## 核心特性",
        "## 项目结构",
        "## 快速开始",
        "## 当前实现状态",
        "## 公开科研代码挖掘",
        "## 第三方 skills 集成",
        "## 贡献者、许可证、商业使用和联系方式",
        "## 打赏",
        "## 最近更新",
    ],
}


def _section(content: str, heading: str) -> str:
    start = content.index(heading)
    rest = content[start + len(heading) :]
    next_heading = re.search(r"^## ", rest, flags=re.MULTILINE)
    return rest if next_heading is None else rest[: next_heading.start()]


def _markdown_table(section: str) -> tuple[list[str], list[list[str]]]:
    table_lines = [line for line in section.splitlines() if line.startswith("|")]
    assert len(table_lines) >= 3
    header = [cell.strip() for cell in table_lines[0].strip("|").split("|")]
    rows = [[cell.strip() for cell in line.strip("|").split("|")] for line in table_lines[2:]]
    assert all(len(row) == 4 for row in rows)
    return header, rows


def test_readmes_preserve_the_detailed_project_guide_and_current_release() -> None:
    version = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    for name, headings in EXPECTED_H2.items():
        content = Path(name).read_text(encoding="utf-8")
        assert [line for line in content.splitlines() if line.startswith("## ")] == headings
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


def test_readmes_use_current_release_capability_clusters_and_minimal_first_setup() -> None:
    expected_ranges = [
        "v0.30.1-v0.30.3",
        "v0.30.4-v0.31.0",
        "v0.31.1-v0.31.5",
        "v0.31.6-v0.31.9",
        "v0.32.0",
        "v0.32.1-v0.32.2",
        "v0.33.0",
    ]
    for name, current_heading, what_heading, features_heading in (
        ("README.md", "## Current Release", "## What It Does", "## Key Features"),
        ("README.zh-CN.md", "## 当前版本", "## 功能概览", "## 核心特性"),
    ):
        content = Path(name).read_text(encoding="utf-8")
        current = _section(content, current_heading)
        clusters = re.findall(r"(?m)^- \*\*(v0\.\d[^*]+)\*\*", current)
        assert clusters == expected_ranges
        assert "python3 -m venv .venv" in content
        assert "py -3 -m venv .venv" in content
        assert "python -m pip install -e ." in content
        assert "pip install -e ." in content
        assert "commercial_overview" not in content

        overview = _section(content, what_heading)
        overview_bullets = [line for line in overview.splitlines() if line.startswith("-")]
        assert len(overview_bullets) == 8

        features = _section(content, features_heading)
        feature_bullets = [line for line in features.splitlines() if line.startswith("-")]
        assert 10 <= len(feature_bullets) <= 12


def test_readmes_bind_capability_anchors_to_truth_matrix_claims_and_evidence_columns() -> None:
    matrix = json.loads(Path("docs/capability_truth_matrix.json").read_text(encoding="utf-8"))
    for name, expected_header in (
        ("README.md", ["Capability ID", "Status / Since", "Evidence", "Boundary"]),
        ("README.zh-CN.md", ["能力 ID", "状态 / Since", "证据", "边界"]),
    ):
        content = Path(name).read_text(encoding="utf-8")
        status = _section(content, "## Implementation Status" if name == "README.md" else "## 当前实现状态")
        header, rows = _markdown_table(status)
        assert header == expected_header
        rows_by_id = {row[0].strip("`"): row for row in rows}
        assert set(rows_by_id) == {record["capability_id"] for record in matrix["capabilities"]}
        for record in matrix["capabilities"]:
            marker = f"<!-- {record['readme_anchor']} -->"
            closing = f"<!-- /{record['readme_anchor']} -->"
            assert marker in content
            assert closing in content
            bounded = content.split(marker, 1)[1].split(closing, 1)[0]
            assert re.sub(r"\s+", " ", bounded).strip()
            row = rows_by_id[record["capability_id"]]
            assert row[1] == f"{record['status']} / {record['since']}"
            boundary = record["boundary_en"] if name == "README.md" else record["boundary_zh"]
            assert row[3] == boundary


def test_readmes_fix_release_order_checkpoint_boundary_and_current_boundary_sentence() -> None:
    expected_boundaries = {
        "README.md": "The current release is v0.33.0; it adds evidence-bound author completion, Result Support v3, synchronized Agent/CLI contracts, and strict completion classification, while fixtures remain workflow-contract checks rather than scientific results.",
        "README.zh-CN.md": "当前版本为 v0.33.0；新增证据绑定的作者补全、Result Support v3、Agent/CLI 合同同步和 strict 补全分类。Fixture 继续只验证流程合同，真实论文仍以可执行学科代码、经过验证的输出和人工证据确认为准。",
    }
    route_boundaries = {
        "README.md": "The current checkpoint selects one route for the whole paper; per-claim routing is later work.",
        "README.zh-CN.md": "当前按整单 checkpoint 选择一条路线，多 claim 分治属于后续工作。",
    }
    ordered = {
        "README.md": [
            "final author completion and precise revisions",
            "final citation audit",
            "two independent blind reviewers",
            "confirm one release hash",
        ],
        "README.zh-CN.md": [
            "最终作者信息补全与定点修订",
            "最终 citation audit",
            "两位独立盲评者",
            "确认同一个 release hash",
        ],
    }
    for name, boundary in expected_boundaries.items():
        content = Path(name).read_text(encoding="utf-8")
        current_heading = "## Current Release" if name == "README.md" else "## 当前版本"
        current = _section(content, current_heading)
        first_paragraph = next(line for line in current.splitlines() if line.strip())
        assert first_paragraph == boundary
        assert route_boundaries[name] in content
        workflow_heading = "## How a Paper Reaches `main.pdf`" if name == "README.md" else "## 论文如何到达 `main.pdf`"
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
