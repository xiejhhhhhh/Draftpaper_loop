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
    protected_action: bool = False
    manual_only: bool = False
    stale_effects: tuple[str, ...] = ()


COMMAND_SPECS = {
    spec.name: spec for spec in (
        CommandSpec("inspect-project-migration", "state_kernel", False, "state", "project_state", "inspect_project_migration", (("project", "project"),)),
        CommandSpec("migrate-project", "state_kernel", True, "state", "project_state", "migrate_project", (("project", "project"),)),
        CommandSpec(
            "plan-project-version",
            "state_kernel",
            False,
            "state",
            "project_versioning",
            "plan_project_version",
            (
                ("project", "project"),
                ("version", "version"),
                ("destination_root", "destination_root"),
                ("change_request", "change_request"),
                ("output", "output"),
            ),
        ),
        CommandSpec(
            "create-project-version",
            "state_kernel",
            True,
            "state",
            "project_versioning",
            "create_project_version_from_plan",
            (("plan", "plan"),),
        ),
        CommandSpec(
            "import-version-assets",
            "state_kernel",
            True,
            "state",
            "project_versioning",
            "import_version_assets",
            (("project", "project"), ("plan", "plan")),
        ),
        CommandSpec(
            "validate-project-version",
            "state_kernel",
            False,
            "state",
            "project_versioning",
            "validate_project_version",
            (("project", "project"),),
            "status_passed",
        ),
        CommandSpec(
            "inspect-system-of-record",
            "state_kernel",
            False,
            "state",
            "project_system_of_record",
            "inspect_project_system_of_record",
            (("project", "project"),),
        ),
        CommandSpec(
            "prepare-project-method-implementation",
            "capability_coordinator",
            True,
            "methods",
            "project_method_implementation",
            "prepare_project_method_implementation",
            (("project", "project"),),
        ),
        CommandSpec(
            "resolve-figure-evidence",
            "evidence_coordinator",
            True,
            "results",
            "evidence_resolver",
            "resolve_figure_evidence",
            (("project", "project"),),
        ),
        CommandSpec(
            "resolve-paragraph-evidence",
            "evidence_coordinator",
            True,
            "writing",
            "evidence_resolver",
            "resolve_paragraph_evidence",
            (("project", "project"), ("section", "section")),
        ),
        CommandSpec(
            "record-stage-receipt",
            "state_kernel",
            True,
            "state",
            "stage_receipts",
            "record_stage_receipt",
            (
                ("project", "project"),
                ("stage", "stage"),
                ("task_id", "task_id"),
                ("input_artifacts", "input_artifact"),
                ("estimated_input_tokens", "estimated_input_tokens"),
                ("actual_input_tokens", "actual_input_tokens"),
                ("actual_output_tokens", "actual_output_tokens"),
                ("model", "model"),
                ("status", "receipt_status"),
            ),
        ),
        CommandSpec("build-reference-registry", "reference_coordinator", True, "references", "bibliography", "build_reference_registry", (("project", "project"),)),
        CommandSpec("inspect-reference-duplicates", "reference_coordinator", True, "references", "bibliography", "inspect_reference_duplicates", (("project", "project"),)),
        CommandSpec(
            "resolve-reference-version",
            "reference_coordinator",
            True,
            "references",
            "bibliography",
            "resolve_reference_version",
            (("project", "project"), ("work", "work"), ("preferred_key", "preferred_key")),
        ),
        CommandSpec("validate-bibliography", "reference_coordinator", True, "quality_checks", "bibliography", "validate_bibliography", (("project", "project"),), "status_passed"),
        CommandSpec("render-reference-proof", "reference_coordinator", True, "quality_checks", "bibliography", "render_reference_proof", (("project", "project"),)),
        CommandSpec("prepare-section-writing", "writing_coordinator", True, "writing", "manuscript_composer", "build_section_evidence_packet", (("project", "project"), ("section", "section"))),
        CommandSpec("submit-section-draft", "writing_coordinator", True, "writing", "manuscript_composer", "submit_section_draft", (("project", "project"), ("section", "section"), ("input_path", "input"))),
        CommandSpec("prepare-scientific-editor", "writing_coordinator", True, "writing", "writing_architecture", "prepare_scientific_editor", (("project", "project"), ("section", "section"), ("input_path", "input"))),
        CommandSpec("accept-section-draft", "writing_coordinator", True, "writing", "manuscript_composer", "accept_section_draft", (("project", "project"), ("section", "section"))),
        CommandSpec("assess-functional-quality-release", "release_coordinator", True, "release", "writing_architecture", "assess_functional_quality_release", (("project", "project"),), "decision_pass"),
        CommandSpec("assess-paper-quality-parity", "release_coordinator", True, "release", "paper_quality_parity", "assess_paper_quality_parity", (("project", "project"),), "decision_pass"),
        CommandSpec("audit-citations", "release_coordinator", True, "citation_audit", "citation_audit", "audit_citations", (("project", "project"), ("final", "final")), "status_passed"),
        CommandSpec("quality-check", "release_coordinator", True, "release", "quality_gate", "run_quality_check", (("project", "project"),), "status_passed"),
    )
}


DECLARED_COMMAND_NAMES = frozenset(
    """
accept-section-draft apply-citation-repair apply-result-downgrade apply-revision assemble-latex
assess-core-evidence assess-data-feasibility assess-data-quality assess-figure-contracts
assess-figure-publication-quality assess-functional-quality-release assess-manuscript-quality
assess-method-feasibility assess-paper-quality-parity assess-plugin-sufficiency assess-publication-readiness
assess-research-plan-feasibility assess-result-support assess-result-validity assess-review-rules audit-citations
audit-project-capabilities bootstrap-discipline-foundation build-argument-matrices build-code-provenance
build-data-context build-method-context build-panel-contracts build-paper-narrative build-reference-registry
build-results-synthesis build-section-lifecycles capture-discipline-learning checkpoint classify-code-ownership
classify-data-access classify-plugin-reusability classify-skill-source collect-method-plan compile-latex-pdf
compile-skill-source create-project create-project-version detect-artifact-drift diagnose-figure-execution
diagnose-gate-failures discover-research-repos discover-review-workflow-gaps evaluate-capability-routing
execute-data-plugins execute-method-plugins extract-method-formulas extract-plugin-candidates
extract-review-rule-signals extract-skill-capabilities generalize-plugin-candidate generate-analysis-code
generate-citation-repair-plan generate-plan generate-revision-plan import-version-assets index-skill-source
inspect-project-migration inspect-reference-duplicates inspect-research-repo inspect-skill-source
inspect-system-of-record inventory-data inventory-data-sources inventory-results learn-writing-style-from-draft
list-capability-packs list-zotero-collections load-project map-repository-workflow map-skill-capabilities
mark-stage-stale migrate-project package-plugin-contribution plan-figures plan-project-version
preflight-plugin-contribution preflight-research-feasibility prepare-analysis-revision
prepare-data-acquisition prepare-discussion-comparison prepare-method-blueprint
prepare-panel-repair prepare-plugin-rescue prepare-project-method-implementation prepare-result-rescue
prepare-results-semantic-repair prepare-scientific-editor prepare-section-outline prepare-section-writing
promote-plugin-candidate propose-review-engineering-plan quality-check re-audit-citations re-review
recommend-statistical-revision record-observation record-plugin-rescue-outcome
record-scientific-editor-revision record-stage-receipt render-reference-proof render-third-party-notices
reopen-core-evidence repair-figure-data repair-figure-method resolve-figure-evidence resolve-journal-template
resolve-paragraph-evidence resolve-reference-version resolve-research-capabilities resolve-result-evidence
resolve-venue-writing-style resume review-draft review-plugin-contribution review-results-with-discipline-rules
revise-research-plan route-stage-code run-citation-repair-loop run-integrity-gate run-pipeline score-research-repos
search-literature snapshot-skill-source status submit-figure-semantic-annotations submit-section-draft
summarize-plugin-candidates sync-artifact-stale trace-figures-to-code update-stage-status validate-bibliography
validate-figure-plugin-trace validate-plugin-candidate validate-project validate-project-version
validate-template-registry validate-third-party-provenance verify-methods write-data write-discussion
write-github-contribution-guide write-introduction write-methods write-results
doctor start continue review recover revise verify-next-action rebuild-derived rebase-project-passport
prepare-independent-manuscript-review record-independent-manuscript-review assess-manuscript-quality-release
build-manuscript-source-map preview-manuscript-revision apply-manuscript-revision rollback-manuscript-revision
set-manuscript-metadata add-custom-reference import-review-findings list-revision-tasks prepare-revision
preview-revision accept-revision eval
""".split()
)


READ_ONLY_COMMANDS = {
    "detect-artifact-drift",
    "doctor",
    "evaluate-capability-routing",
    "inspect-project-migration",
    "inspect-research-repo",
    "inspect-skill-source",
    "inspect-system-of-record",
    "list-capability-packs",
    "list-zotero-collections",
    "load-project",
    "plan-project-version",
    "run-pipeline",
    "status",
    "validate-project",
    "validate-project-version",
    "validate-template-registry",
    "validate-third-party-provenance",
    "verify-next-action",
    "rebuild-derived",
    "continue",
    "review",
    "recover",
}


def _default_coordinator(name: str) -> tuple[str, str]:
    if any(token in name for token in ("citation", "reference", "bibliography", "literature", "zotero")):
        return "reference_coordinator", "references"
    if any(token in name for token in ("figure", "result")):
        return "evidence_coordinator", "results"
    if any(token in name for token in ("section", "writing", "introduction", "discussion", "manuscript", "revise")):
        return "writing_coordinator", "writing"
    if any(token in name for token in ("plugin", "skill", "capability", "discipline", "research-repo")):
        return "capability_coordinator", "capabilities"
    if any(token in name for token in ("method", "code", "analysis")):
        return "method_coordinator", "methods"
    if any(token in name for token in ("data",)):
        return "data_coordinator", "data"
    if any(token in name for token in ("quality", "review", "integrity", "publication")):
        return "release_coordinator", "quality_checks"
    return "state_kernel", "state"


for _name in sorted(DECLARED_COMMAND_NAMES):
    if _name in COMMAND_SPECS:
        continue
    _coordinator, _stage = _default_coordinator(_name)
    COMMAND_SPECS[_name] = CommandSpec(
        _name,
        _coordinator,
        _name not in READ_ONLY_COMMANDS,
        _stage,
        protected_action=_name in {
            "checkpoint",
            "resume",
            "reopen-core-evidence",
            "apply-result-downgrade",
            "promote-plugin-candidate",
            "resolve-reference-version",
            "apply-manuscript-revision",
            "rollback-manuscript-revision",
            "rebase-project-passport",
        },
        manual_only=_name in {"checkpoint", "resume", "promote-plugin-candidate", "resolve-reference-version"},
    )

COMMAND_SPECS.update({
    "doctor": CommandSpec("doctor", "state_kernel", False, "state", "doctor", "doctor_project", (("project", "project"),)),
    "verify-next-action": CommandSpec("verify-next-action", "state_kernel", False, "state", "doctor", "verify_next_action", (("project", "project"),), "status_passed"),
    "rebuild-derived": CommandSpec("rebuild-derived", "state_kernel", False, "state", "doctor", "rebuild_derived", (("project", "project"), ("dry_run", "dry_run"))),
    "start": CommandSpec("start", "state_kernel", True, "state", "workflow_macros", "start_workflow", (("root", "root"), ("idea", "idea"), ("field", "field"), ("target_journal", "target_journal"))),
    "continue": CommandSpec("continue", "state_kernel", False, "state", "workflow_macros", "continue_workflow", (("project", "project"),)),
    "review": CommandSpec("review", "release_coordinator", False, "quality_checks", "workflow_macros", "review_workflow", (("project", "project"),)),
    "recover": CommandSpec("recover", "state_kernel", False, "state", "workflow_macros", "recover_workflow", (("project", "project"),)),
    "rebase-project-passport": CommandSpec("rebase-project-passport", "state_kernel", True, "state", "workflow_macros", "rebase_project_passport", (("project", "project"), ("origin", "origin"), ("confirm", "confirm")), protected_action=True, manual_only=True),
    "prepare-independent-manuscript-review": CommandSpec("prepare-independent-manuscript-review", "release_coordinator", True, "quality_checks", "independent_review", "prepare_independent_manuscript_review", (("project", "project"),)),
    "record-independent-manuscript-review": CommandSpec("record-independent-manuscript-review", "release_coordinator", True, "quality_checks", "independent_review", "record_independent_manuscript_review", (("project", "project"), ("reviewer", "reviewer"), ("input_path", "input"))),
    "assess-manuscript-quality-release": CommandSpec("assess-manuscript-quality-release", "release_coordinator", True, "quality_checks", "independent_review", "assess_manuscript_quality_release", (("project", "project"),), "status_passed"),
    "build-manuscript-source-map": CommandSpec("build-manuscript-source-map", "writing_coordinator", True, "writing", "manuscript_revision", "build_manuscript_source_map", (("project", "project"),)),
    "preview-manuscript-revision": CommandSpec("preview-manuscript-revision", "writing_coordinator", True, "writing", "manuscript_revision", "preview_manuscript_revision", (("project", "project"), ("instruction", "instruction"), ("at", "at"), ("paragraph", "paragraph"), ("content_file", "content_file"), ("operation", "operation"), ("mode", "mode"), ("change_class", "change_class"))),
    "apply-manuscript-revision": CommandSpec("apply-manuscript-revision", "writing_coordinator", True, "writing", "manuscript_revision", "apply_manuscript_revision", (("project", "project"), ("request_id", "request_id")), protected_action=True),
    "rollback-manuscript-revision": CommandSpec("rollback-manuscript-revision", "writing_coordinator", True, "writing", "manuscript_revision", "rollback_manuscript_revision", (("project", "project"), ("revision_id", "revision_id")), protected_action=True),
    "set-manuscript-metadata": CommandSpec("set-manuscript-metadata", "writing_coordinator", True, "writing", "manuscript_revision", "set_manuscript_metadata", (("project", "project"), ("input_path", "input"))),
    "add-custom-reference": CommandSpec("add-custom-reference", "reference_coordinator", True, "references", "manuscript_revision", "add_custom_reference", (("project", "project"), ("input_path", "input"))),
    "import-review-findings": CommandSpec("import-review-findings", "writing_coordinator", True, "writing", "manuscript_revision", "import_review_findings", (("project", "project"), ("review", "review"))),
    "list-revision-tasks": CommandSpec("list-revision-tasks", "writing_coordinator", False, "writing", "manuscript_revision", "list_revision_tasks", (("project", "project"),)),
    "prepare-revision": CommandSpec("prepare-revision", "writing_coordinator", True, "writing", "manuscript_revision", "prepare_revision_from_task", (("project", "project"), ("task", "task"))),
    "preview-revision": CommandSpec("preview-revision", "writing_coordinator", False, "writing", "manuscript_revision", "inspect_revision_preview", (("project", "project"), ("revision_id", "revision"))),
    "accept-revision": CommandSpec("accept-revision", "writing_coordinator", True, "writing", "manuscript_revision", "apply_manuscript_revision", (("project", "project"), ("request_id", "revision")), protected_action=True),
    "revise": CommandSpec("revise", "writing_coordinator", True, "writing", "manuscript_revision", "preview_manuscript_revision", (("project", "project"), ("instruction", "instruction"), ("at", "at"), ("paragraph", "paragraph"), ("content_file", "content_file"), ("operation", "operation"), ("mode", "mode"), ("change_class", "change_class"))),
    "eval": CommandSpec("eval", "release_coordinator", True, "quality_checks", "eval_runtime", "run_eval_command", (("action", "eval_action"), ("project", "project"), ("case", "case"), ("capture", "capture"), ("baseline", "baseline"), ("report", "report"), ("output", "output"))),
})


def command_spec(name: str) -> CommandSpec | None:
    return COMMAND_SPECS.get(name)


def dispatch_registered_command(args: Any) -> tuple[dict[str, Any], int] | None:
    """Execute a formal command through its declared coordinator boundary."""
    spec = command_spec(str(getattr(args, "command", "")))
    if spec is None or not spec.handler_module or not spec.handler_name:
        return None
    module = import_module(f".{spec.handler_module}", package=__package__)
    handler = getattr(module, spec.handler_name)
    kwargs = {parameter: getattr(args, attribute, None) for parameter, attribute in spec.argument_bindings}
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
