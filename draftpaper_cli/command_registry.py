"""Declarative metadata for commands that define the formal v0.22+ workflow."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any


@dataclass(frozen=True)
class CommandSpec:
    name: str
    coordinator: str
    mutates_project: bool
    formal_stage: str
    handler_module: str | None = None
    handler_name: str | None = None
    argument_bindings: tuple[tuple[str, str], ...] = ()
    exit_policy: str = "always_success"


COMMAND_SPECS = {
    spec.name: spec for spec in (
        CommandSpec("inspect-project-migration", "state_kernel", False, "state", "project_state", "inspect_project_migration", (("project", "project"),)),
        CommandSpec("migrate-project", "state_kernel", True, "state", "project_state", "migrate_project", (("project", "project"),)),
        CommandSpec("prepare-section-writing", "writing_coordinator", True, "writing", "manuscript_composer", "build_section_evidence_packet", (("project", "project"), ("section", "section"))),
        CommandSpec("submit-section-draft", "writing_coordinator", True, "writing", "manuscript_composer", "submit_section_draft", (("project", "project"), ("section", "section"), ("input_path", "input"))),
        CommandSpec("prepare-scientific-editor", "writing_coordinator", True, "writing", "writing_architecture", "prepare_scientific_editor", (("project", "project"), ("section", "section"), ("input_path", "input"))),
        CommandSpec("accept-section-draft", "writing_coordinator", True, "writing", "manuscript_composer", "accept_section_draft", (("project", "project"), ("section", "section"))),
        CommandSpec("assess-functional-quality-release", "release_coordinator", True, "release", "writing_architecture", "assess_functional_quality_release", (("project", "project"),), "decision_pass"),
        CommandSpec("assess-paper-quality-parity", "release_coordinator", True, "release", "paper_quality_parity", "assess_paper_quality_parity", (("project", "project"),), "decision_pass"),
        CommandSpec("audit-citations", "release_coordinator", True, "citation_audit", "citation_audit", "audit_citations", (("project", "project"), ("final", "final")), "status_passed"),
        CommandSpec("prepare-blind-quality-evaluation", "release_coordinator", True, "release", "blind_quality", "prepare_blind_quality_evaluation", (("project", "project"),)),
        CommandSpec("record-blind-quality-evaluation", "release_coordinator", True, "release", "blind_quality", "record_blind_quality_evaluation", (("project", "project"), ("input_path", "input"))),
        CommandSpec("quality-check", "release_coordinator", True, "release", "quality_gate", "run_quality_check", (("project", "project"),), "status_passed"),
    )
}


def command_spec(name: str) -> CommandSpec | None:
    return COMMAND_SPECS.get(name)


def dispatch_registered_command(args: Any) -> tuple[dict[str, Any], int] | None:
    """Execute a formal command through its declared coordinator boundary."""
    spec = command_spec(str(getattr(args, "command", "")))
    if spec is None or not spec.handler_module or not spec.handler_name:
        return None
    module = import_module(f".{spec.handler_module}", package=__package__)
    handler = getattr(module, spec.handler_name)
    kwargs = {parameter: getattr(args, attribute) for parameter, attribute in spec.argument_bindings}
    payload = handler(**kwargs)
    if not isinstance(payload, dict):
        raise TypeError(f"Registered command {spec.name} returned a non-object payload.")
    if spec.exit_policy == "decision_pass":
        exit_code = 0 if payload.get("decision") == "pass" else 1
    elif spec.exit_policy == "status_passed":
        exit_code = 0 if payload.get("status") == "passed" else 1
    else:
        exit_code = 0
    return payload, exit_code
