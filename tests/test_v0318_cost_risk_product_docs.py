from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from draftpaper_cli.command_registry import COMMAND_SPECS
from draftpaper_cli.install_profiles import inspect_install_profiles
from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.release_contract import build_release_manifest


def test_token_report_uses_recorded_or_estimated_tokens_without_inventing_prices(tmp_path: Path) -> None:
    from draftpaper_cli.token_report import build_token_cost_report

    project = create_project(root=tmp_path, idea="Token accounting", field="engineering").path
    rows = [
        {
            "task_id": "prepare-section-writing:results",
            "stage": "results",
            "model": "model-a",
            "recorded_at": "2026-07-18T00:00:00Z",
            "estimated_input_tokens": 1000,
            "estimated_output_tokens": 100,
        },
        {
            "task_id": "prepare-section-writing:results",
            "stage": "results",
            "model": "model-a",
            "recorded_at": "2026-07-18T01:00:00Z",
            "actual_input_tokens": 800,
            "actual_output_tokens": 80,
            "recorded_cost_usd": 0.12,
        },
        {
            "task_id": "search-literature:main",
            "stage": "references",
            "model": "model-b",
            "recorded_at": "2026-07-18T02:00:00Z",
            "estimated_input_tokens": 400,
            "estimated_output_tokens": 40,
        },
    ]
    (project / "token_ledger.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    report = build_token_cost_report(project)

    assert report["status"] == "passed"
    assert report["totals"]["input_tokens"] == 2200
    assert report["totals"]["output_tokens"] == 220
    assert report["active_manuscript"]["input_tokens"] == 800
    assert report["by_stage"]["results"]["input_tokens"] == 1800
    assert report["by_model"]["model-a"]["receipt_count"] == 2
    assert report["monetary_cost"]["recorded_usd"] == 0.12
    assert report["monetary_cost"]["status"] == "partial_recorded_values"
    assert "estimated from token counts" not in json.dumps(report)


def test_token_report_is_a_registered_read_only_cli_command(tmp_path: Path) -> None:
    project = create_project(root=tmp_path, idea="Token CLI", field="engineering").path
    completed = subprocess.run(
        [sys.executable, "-m", "draftpaper_cli.cli", "token-report", "--project", str(project)],
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["schema_version"] == "dpl.token_cost_report.v1"
    spec = COMMAND_SPECS["token-report"]
    assert spec.mutates_project is False
    assert spec.risk_level == "read"
    assert "token-report" in build_release_manifest()["required_cli_commands"]


def test_doctor_exposes_combined_research_workstation_profile() -> None:
    report = inspect_install_profiles(module_available=lambda _name: True)
    research = report["profiles"]["research"]

    assert research["status"] == "available"
    assert set(research["composed_from"]) == {"plotting", "fulltext", "mcp"}
    assert research["install_command"].endswith('[plotting,fulltext,mcp]"')


def test_generated_risk_matrix_and_product_boundaries_are_current() -> None:
    from tools.generate_product_docs import render_command_risk_matrix

    risk = Path("docs/command_risk_matrix.md")
    assert risk.read_text(encoding="utf-8") == render_command_risk_matrix()
    command_table = risk.read_text(encoding="utf-8").split("## Commands", 1)[1]
    assert sum(1 for line in command_table.splitlines() if line.startswith("| `")) == len(COMMAND_SPECS)


def test_product_boundary_stubs_are_minimal_and_point_to_readmes() -> None:
    for path in (Path("docs/commercial_overview.md"), Path("docs/commercial_overview.zh-CN.md")):
        text = path.read_text(encoding="utf-8").lower()
        assert len(text.splitlines()) <= 12
        assert "licenseref-draftpaper-noncommercial" in text
        assert "local" in text or "本地" in text
        assert "public hosted api" in text or "公网托管 api" in text
        assert "readme" in text
