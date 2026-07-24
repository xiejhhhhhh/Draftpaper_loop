from __future__ import annotations

import json
from pathlib import Path

import pytest

from draftpaper_cli.extensions.contracts import ExtensionManifest, negotiate_extension, version_satisfies
from draftpaper_cli.extensions.dispatcher import dispatch_workflow_event
from draftpaper_cli.extensions.events import emit_command_event
from draftpaper_cli.extensions.host_capabilities import build_host_capabilities
from draftpaper_cli.extensions.registry import DiscoveredExtension
from draftpaper_cli.extensions.scoped_artifact_reader import ScopedArtifactReader
from draftpaper_cli.extensions.status_projection import extension_status


def _manifest(**overrides: object) -> ExtensionManifest:
    document = {
        "schema_version": "dpl.guidance_extension_manifest.v1",
        "extension_id": "test.guidance",
        "package_name": "test-guidance",
        "package_version": "1.0.0",
        "abi_family": "dpl.extension",
        "supported_abi": ">=1.0,<2.0",
        "required_capabilities": ["artifact.read_by_role"],
        "optional_capabilities": ["future.capability"],
        "subscriptions": ["workflow.stage_committed"],
        "read_globs": ["research_plan/**"],
        "write_scope": ["guidance/**"],
        "event_handler": "tests.test_extension_host:successful_handler",
    }
    document.update(overrides)
    return ExtensionManifest.from_dict(document)


def successful_handler(**context: object) -> dict[str, object]:
    event = context["event"]
    return {"status": "ok", "event_id": event["event_id"]}  # type: ignore[index]


def failing_handler(**_context: object) -> None:
    raise RuntimeError("extension failure")


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    (project / "research_plan").mkdir(parents=True)
    (project / "research_plan" / "research_plan.md").write_text("# Plan\n", encoding="utf-8")
    (project / "project.json").write_text(json.dumps({"project_id": "project:test", "stages": {}}), encoding="utf-8")
    return project


def test_version_range_and_capability_negotiation_are_not_patch_pinned() -> None:
    assert version_satisfies("1.1.0", ">=1.0,<2.0")
    result = negotiate_extension(_manifest(), build_host_capabilities(core_version="0.40.0"))
    assert result.status == "compatible_with_degradation"
    assert result.selected_abi == "1.0"
    assert result.unavailable_optional == ("future.capability",)


def test_published_host_capability_document_matches_runtime_contract() -> None:
    document = json.loads(
        Path("draftpaper_cli/resources/extension_host_capabilities.json").read_text(
            encoding="utf-8"
        )
    )
    runtime = build_host_capabilities(core_version=document["core_version"]).to_dict()
    assert document == runtime


def test_missing_required_capability_disables_only_the_extension() -> None:
    manifest = _manifest(required_capabilities=["missing.required"])
    result = negotiate_extension(manifest, build_host_capabilities())
    assert result.status == "incompatible"
    assert result.missing_required == ("missing.required",)


def test_scoped_reader_confines_paths_and_excludes_guidance(tmp_path: Path) -> None:
    project = _project(tmp_path)
    reader = ScopedArtifactReader(project, allowed_globs=("research_plan/**",))
    view = reader.read("research_plan/research_plan.md", token=reader.capability_token)
    assert view.text().splitlines() == ["# Plan"]
    with pytest.raises(PermissionError):
        reader.read("../outside.txt", token=reader.capability_token)
    with pytest.raises(PermissionError):
        reader.read("guidance/learning/index.html", token=reader.capability_token)
    with pytest.raises(PermissionError):
        reader.read("research_plan/research_plan.md", token="wrong")


def test_event_dispatch_is_nonblocking_and_records_receipts(tmp_path: Path) -> None:
    project = _project(tmp_path)
    event = emit_command_event(
        project,
        command="generate-plan",
        formal_stage="references",
        result={"output": "research_plan/research_plan.md"},
    )
    good_manifest = _manifest(subscriptions=[event.event_type])
    good = DiscoveredExtension("good", good_manifest, negotiate_extension(good_manifest, build_host_capabilities()))
    bad_manifest = _manifest(
        extension_id="test.failing",
        subscriptions=[event.event_type],
        event_handler="tests.test_extension_host:failing_handler",
    )
    bad = DiscoveredExtension("bad", bad_manifest, negotiate_extension(bad_manifest, build_host_capabilities()))
    receipts = dispatch_workflow_event(project, event, extensions=(good, bad))
    assert [item["status"] for item in receipts] == ["completed", "failed_nonblocking"]
    ledger = (project / ".draftpaper" / "extensions" / "extension_receipts.jsonl").read_text(encoding="utf-8")
    assert "extension failure" in ledger


def test_extension_status_projects_learning_receipts_without_changing_core_state(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    event = emit_command_event(
        project,
        command="generate-plan",
        formal_stage="references",
        result={"output": "research_plan/research_plan.md"},
    )
    report = extension_status(project)
    assert report["event_count"] == 1
    assert report["latest_event"]["event_id"] == event.event_id


def test_review_and_final_commands_use_semantic_event_types(tmp_path: Path) -> None:
    project = _project(tmp_path)
    review = emit_command_event(
        project,
        command="record-independent-manuscript-review",
        formal_stage="quality_checks",
        result={},
    )
    final = emit_command_event(
        project,
        command="confirm-final-manuscript",
        formal_stage="release",
        result={},
    )
    semantic_review = emit_command_event(
        project,
        command="review-results-with-discipline-rules",
        formal_stage="results",
        result={},
    )
    assert review.event_type == "review.completed"
    assert final.event_type == "manuscript.finalized"
    assert semantic_review.event_type == "workflow.stage_committed"
