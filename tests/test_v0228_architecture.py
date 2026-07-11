from __future__ import annotations

import argparse
import inspect

import pytest

from draftpaper_cli.artifact_repository import ArtifactRepository, ArtifactRepositoryError
from draftpaper_cli.cli import build_parser
from draftpaper_cli.command_registry import COMMAND_SPECS, dispatch_registered_command
from draftpaper_cli import orchestrator, quality_gate
from draftpaper_cli.orchestrator import _next_action
from draftpaper_cli.project_scaffold import create_project


def test_artifact_repository_enforces_containment_and_atomic_structured_io(tmp_path) -> None:
    project = create_project(root=tmp_path, idea="Repository boundary", field="engineering").path
    repo = ArtifactRepository(project)
    repo.write_json("writing/example.json", {"status": "written", "value": 3})
    assert repo.read_mapping("writing/example.json")["value"] == 3
    with pytest.raises(ArtifactRepositoryError):
        repo.write_json("../escape.json", {"unsafe": True})


def test_formal_command_registry_matches_cli_parser() -> None:
    parser = build_parser()
    subparsers = next(action for action in parser._actions if hasattr(action, "choices") and action.choices)
    assert set(COMMAND_SPECS) <= set(subparsers.choices)


def test_cli_root_help_renders_all_registered_command_descriptions() -> None:
    help_text = build_parser().format_help()
    assert "prepare-blind-quality-evaluation" in help_text
    assert "quality-check" in help_text


def test_formal_command_registry_executes_declared_handler(tmp_path) -> None:
    project = create_project(root=tmp_path, idea="Registry dispatch", field="engineering").path
    dispatched = dispatch_registered_command(argparse.Namespace(command="inspect-project-migration", project=str(project)))
    assert dispatched is not None
    payload, exit_code = dispatched
    assert payload["status"] == "current"
    assert exit_code == 0


def test_orchestrator_routes_writing_through_coordinator_module() -> None:
    source = inspect.getsource(_next_action)
    assert "coordinated_section_lifecycle_action" in source
    assert "coordinated_formal_release_action" in source
    assert not hasattr(orchestrator, "_section_lifecycle_action")
    assert not hasattr(orchestrator, "_formal_writing_release_action")


def test_quality_gate_uses_project_artifact_repository_boundary() -> None:
    source = inspect.getsource(quality_gate)
    assert "ArtifactRepository" in source
    assert "def _read_json(" not in source
