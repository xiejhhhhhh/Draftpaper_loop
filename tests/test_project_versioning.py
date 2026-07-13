from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from draftpaper_cli.passport import read_jsonl, refresh_project_passport
from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.project_system_of_record import inspect_project_system_of_record
from draftpaper_cli.project_state import load_project
from draftpaper_cli.project_versioning import (
    ProjectVersioningError,
    create_project_version_from_plan,
    import_version_assets,
    plan_project_version,
    validate_project_version,
)


def _hash_tree(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _write_parent_assets(project: Path) -> None:
    (project / "data" / "raw" / "catalog.csv").write_text("id,value\n1,2\n", encoding="utf-8")
    (project / "methods" / "src" / "fit.py").write_text("print('candidate')\n", encoding="utf-8")
    (project / "results" / "figures" / "figure_1.png").write_bytes(b"baseline-figure")
    (project / "results" / "figure_metadata.json").write_text('{"legacy": true}\n', encoding="utf-8")
    (project / "results" / "plugin_sufficiency_report.json").write_text('{"legacy": true}\n', encoding="utf-8")
    (project / "results" / "project_local_capability_audit.json").write_text('{"legacy": true}\n', encoding="utf-8")
    (project / "latex" / "sections" / "results.tex").write_text("Legacy results.\n", encoding="utf-8")
    refresh_project_passport(project, event="test_parent_assets")


def test_project_version_plan_is_read_only_and_creates_clean_child(tmp_path: Path) -> None:
    parent = create_project(root=tmp_path, idea="Versioned science", field="astronomy").path
    _write_parent_assets(parent)
    before = _hash_tree(parent)
    plan_path = tmp_path / "asset_import_plan.json"

    plan = plan_project_version(parent, output=plan_path)

    assert plan["target_directory_name"].endswith("_v1")
    assert len(plan["target_directory_name"]) <= 51
    assert plan["old_project_mutated"] is False
    assert plan_path.is_file()
    assert _hash_tree(parent) == before

    created = create_project_version_from_plan(plan_path)
    child = Path(created["project_path"])
    assert child.name == plan["target_directory_name"]
    assert created["project_id"] != load_project(parent).metadata["project_id"]
    assert _hash_tree(parent) == before

    imported = import_version_assets(child, plan_path)
    assert imported["status"] == "imported"
    assert _hash_tree(parent) == before

    child_state = load_project(child)
    assert all(
        meta["status"] == "pending" and not meta["stale"]
        for stage, meta in child_state.metadata["stages"].items()
        if stage != "idea"
    )
    assert list((child / "lineage" / "locators").glob("*.json"))
    assert (child / "lineage" / "imported_code" / "methods" / "src" / "fit.py").is_file()
    assert (child / "lineage" / "baseline_assets" / "results" / "figures" / "figure_1.png").is_file()
    assert (child / "lineage" / "legacy_reports" / "results" / "figure_metadata.json").is_file()
    assert not (child / "results" / "figure_metadata.json").exists()
    assert not (child / "results" / "plugin_sufficiency_report.json").exists()
    assert not (child / "results" / "project_local_capability_audit.json").exists()
    assert validate_project_version(child)["status"] == "passed"


def test_system_of_record_exposes_managed_artifact_contracts(tmp_path: Path) -> None:
    project = create_project(root=tmp_path, idea="Artifact contracts", field="biology").path
    report = inspect_project_system_of_record(project)

    assert report["status"] == "current"
    idea = next(item for item in report["artifacts"] if item["path"] == "idea/idea.md")
    assert idea["category"] == "canonical_decision"
    required = {
        "artifact_id",
        "category",
        "owner_stage",
        "writer_command",
        "input_artifact_ids",
        "input_sha256",
        "schema_version",
        "generator_version",
        "evidence_snapshot_id",
        "run_id",
        "privacy_class",
        "rebuild_command",
    }
    assert required <= idea.keys()
    assert report["violation_count"] == 0


def test_version_creation_rejects_parent_changes_after_plan(tmp_path: Path) -> None:
    parent = create_project(root=tmp_path, idea="Immutable parent", field="geography").path
    plan_path = tmp_path / "plan.json"
    plan_project_version(parent, output=plan_path)
    (parent / "idea" / "idea.md").write_text("changed after planning\n", encoding="utf-8")

    with pytest.raises(ProjectVersioningError, match="changed after"):
        create_project_version_from_plan(plan_path)


def test_plan_output_cannot_be_written_inside_parent(tmp_path: Path) -> None:
    parent = create_project(root=tmp_path, idea="Read only parent", field="medicine").path
    with pytest.raises(ProjectVersioningError, match="cannot be written inside"):
        plan_project_version(parent, output=parent / "lineage" / "plan.json")


def test_project_version_cli_smoke(tmp_path: Path) -> None:
    parent = create_project(root=tmp_path, idea="CLI version", field="engineering").path
    plan_path = tmp_path / "cli-plan.json"
    plan = subprocess.run(
        [
            sys.executable,
            "-m",
            "draftpaper_cli.cli",
            "plan-project-version",
            "--project",
            str(parent),
            "--output",
            str(plan_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(plan.stdout)["status"] == "ready"

    create = subprocess.run(
        [sys.executable, "-m", "draftpaper_cli.cli", "create-project-version", "--plan", str(plan_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    child = Path(json.loads(create.stdout)["project_path"])
    subprocess.run(
        [
            sys.executable,
            "-m",
            "draftpaper_cli.cli",
            "import-version-assets",
            "--project",
            str(child),
            "--plan",
            str(plan_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    validate = subprocess.run(
        [sys.executable, "-m", "draftpaper_cli.cli", "validate-project-version", "--project", str(child)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(validate.stdout)["status"] == "passed"


def test_mutating_cli_blocks_preexisting_drift_and_records_transaction(tmp_path: Path) -> None:
    project = create_project(root=tmp_path, idea="Blocked transaction", field="engineering").path
    (project / "idea" / "idea.md").write_text("external change\n", encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "draftpaper_cli.cli",
            "update-stage-status",
            "--project",
            str(project),
            "--stage",
            "references",
            "--status",
            "draft",
        ],
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 3
    assert json.loads(completed.stderr)["reason"] == "preexisting_artifact_drift"
    assert load_project(project).metadata["stages"]["references"]["status"] == "pending"
    rows = read_jsonl(project / "transaction_ledger.jsonl")
    assert rows[-1]["transaction_status"] == "blocked_preexisting_drift"


def test_nonzero_scientific_command_commits_transaction_and_passport(tmp_path: Path) -> None:
    project = create_project(root=tmp_path, idea="Nonzero transaction", field="engineering").path

    completed = subprocess.run(
        [sys.executable, "-m", "draftpaper_cli.cli", "quality-check", "--project", str(project)],
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    rows = read_jsonl(project / "transaction_ledger.jsonl")
    assert rows[-1]["command"] == "quality-check"
    assert rows[-1]["transaction_status"] == "committed"
    assert rows[-1]["scientific_exit_code"] == completed.returncode


def test_nonzero_command_without_managed_writes_does_not_refresh_passport(tmp_path: Path) -> None:
    project = create_project(root=tmp_path, idea="Aborted transaction", field="engineering").path
    passport = project / "project_passport.yaml"
    before = hashlib.sha256(passport.read_bytes()).hexdigest()

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "draftpaper_cli.cli",
            "update-stage-status",
            "--project",
            str(project),
            "--stage",
            "not-a-stage",
            "--status",
            "draft",
        ],
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert hashlib.sha256(passport.read_bytes()).hexdigest() == before
    rows = read_jsonl(project / "transaction_ledger.jsonl")
    assert rows[-1]["transaction_status"] == "aborted_no_managed_writes"
