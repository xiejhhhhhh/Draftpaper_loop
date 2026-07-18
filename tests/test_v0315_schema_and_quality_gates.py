from __future__ import annotations

from pathlib import Path

from draftpaper_cli.release_contract import build_release_manifest
from draftpaper_cli.schema_registry import schema_family, validate_packaged_resource_schemas


def test_release_fixtures_and_capability_packs_use_registered_schemas() -> None:
    report = validate_packaged_resource_schemas()
    assert report["status"] == "passed", report["issues"]
    assert report["release_fixture_count"] == 5
    assert report["capability_pack_count"] >= 6
    assert schema_family("dpl.release_fixture.v1") == "release_fixture"
    assert schema_family("dpl.research_capability_pack.v1") == "research_capability_pack"


def test_hot_method_and_figure_output_schemas_are_registered() -> None:
    assert schema_family("dpl.method_run_manifest.v1") == "method_run_manifest"
    assert schema_family("dpl.method_formula_manifest.v1") == "method_formula_manifest"
    assert schema_family("dpl.figure_contract_assessment.v1") == "figure_contract_assessment"
    assert schema_family("dpl.command_contract_registry.v1") == "command_contract_registry"


def test_release_manifest_binds_resource_schema_validation() -> None:
    manifest = build_release_manifest()
    assert manifest["resource_schema_status"] == "passed"


def test_ci_coverage_and_pyright_scope_include_new_control_plane() -> None:
    workflow = Path(".github/workflows/tests.yml").read_text(encoding="utf-8")
    assert "--cov-fail-under=65" in workflow

    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    for path in (
        "draftpaper_cli/command_registry.py",
        "draftpaper_cli/manuscript_completion.py",
        "draftpaper_cli/stale_sync.py",
        "draftpaper_cli/figure_contracts.py",
        "draftpaper_cli/methods/verification.py",
    ):
        assert f'"{path}"' in pyproject
