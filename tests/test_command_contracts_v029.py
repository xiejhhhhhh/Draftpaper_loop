from __future__ import annotations

from draftpaper_cli.command_contracts import build_command_contracts, command_input_schema


def test_normalized_command_contracts_cover_every_cli_command() -> None:
    report = build_command_contracts()
    assert report["status"] == "passed", report["issues"]
    assert report["command_count"] >= 204
    assert report["registered_handler_count"] >= 80


def test_apply_section_revision_binding_uses_real_parser_and_handler_names() -> None:
    report = build_command_contracts()
    contract = next(item for item in report["commands"] if item["command"] == "apply-section-revision")
    assert contract["issues"] == []
    schema, project_scoped = command_input_schema("apply-section-revision")
    assert project_scoped is True
    assert {"project", "section", "input", "change_class"}.issubset(schema["properties"])
