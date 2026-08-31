"""Generated release identity shared by source, wheel, CI, and verifiers."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

RELEASE_MANIFEST = Path(__file__).resolve().parent / "resources" / "release_manifest.json"
CI_CONSTRAINTS = Path("requirements/ci-constraints.txt")
EXPECTED_LICENSE = "LicenseRef-Draftpaper-NonCommercial"
ANY_ACTION_RE = re.compile(r"\buses:\s*[^\s@]+@([^\s#]+)")
REQUIRED_CLI_COMMANDS = (
    "assemble-latex",
    "run-integrity-gate",
    "quality-check",
    "review-research-plan",
    "confirm-research-plan",
    "reopen-research-plan",
    "audit-research-plan-migration",
    "path-budget-check",
    "token-report",
    "validate-confirmed-figure-alignment",
    "apply-section-revision",
    "review-final-manuscript",
    "confirm-final-manuscript",
    "audit-citations",
    "re-audit-citations",
    "prepare-independent-manuscript-review",
    "record-independent-manuscript-review",
    "assess-manuscript-quality-release",
    "validate-command-contracts",
    "prepare-manuscript-completion",
    "preview-manuscript-completion",
    "apply-manuscript-completion",
    "manuscript-completion-status",
    "rollback-manuscript-completion",
    "assess-result-support",
    "apply-result-downgrade",
    "prepare-result-rescue",
    "benchmark-literature-quality",
    "benchmark-document-parsers",
    "audit-literature-integrity",
    "sync-literature-sources",
    "apply-literature-sync",
    "repair-literature-identities",
    "rebuild-literature-index",
    "configure-review-policy",
    "grant-agent-review",
    "review-policy-status",
    "review-authority-shadow",
    "revoke-agent-review",
    "evaluate-checkpoint-authority",
    "review-checkpoint",
    "show-stage-activity",
    "begin-managed-change",
    "apply-managed-change",
    "begin-revision-cycle",
    "audit-longitudinal-consistency",
    "reconcile-project-drift",
    "show-scientific-baseline",
    "show-checkpoint-audit",
    "inspect-review-evidence",
    "render-checkpoint-audit",
    "shadow-checkpoint-v6",
    "compare-checkpoint-decision",
    "explain-reconfirmation",
    "validate-checkpoint-readability",
    "show-confirmation-continuity",
    "rebuild-checkpoint-presentation",
    "verify-environment",
    "prepare-literature-admission",
    "activate-literature-corpus",
)


def _version(root: Path) -> str:
    match = re.search(r'^version\s*=\s*"([^"]+)"', (root / "pyproject.toml").read_text(encoding="utf-8"), re.MULTILINE)
    if not match:
        raise ValueError("pyproject.toml has no project version.")
    return match.group(1)


def _sha(path: Path) -> str:
    value = path.read_bytes()
    if path.suffix.lower() in {".json", ".py", ".md", ".yaml", ".yml", ".csv", ".txt"}:
        value = value.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(value).hexdigest()


def _project_license(root: Path) -> str:
    match = re.search(r'^license\s*=\s*"([^"]+)"', (root / "pyproject.toml").read_text(encoding="utf-8"), re.MULTILINE)
    return match.group(1) if match else ""


def _actions_pinned(root: Path) -> bool:
    workflow_root = root / ".github" / "workflows"
    references = []
    for path in sorted(workflow_root.glob("*.yml")) + sorted(workflow_root.glob("*.yaml")):
        references.extend(ANY_ACTION_RE.findall(path.read_text(encoding="utf-8")))
    return bool(references) and all(re.fullmatch(r"[0-9a-f]{40}", reference) for reference in references)


def _release_manifest_path(root: Path) -> Path:
    return root / "draftpaper_cli" / "resources" / "release_manifest.json"


def _load_schema_registry(root: Path) -> dict[str, Any]:
    path = root / "draftpaper_cli" / "resources" / "schemas" / "schema_registry.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Package schema registry is invalid under supplied root: {path}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("families"), dict):
        raise ValueError(f"Package schema registry is invalid under supplied root: {path}")
    return payload


def _load_optional_json(path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return dict(fallback)
    return payload if isinstance(payload, dict) else dict(fallback)


def _schema_family(registry: dict[str, Any], schema_id: str) -> str | None:
    for family, raw_contract in registry["families"].items():
        if not isinstance(raw_contract, dict):
            continue
        accepted = raw_contract.get("accepted")
        accepted_ids = accepted if isinstance(accepted, list) else []
        if schema_id == raw_contract.get("current") or schema_id in accepted_ids:
            return str(family)
    return None


def _validate_packaged_resource_schemas(root: Path, registry: dict[str, Any]) -> dict[str, Any]:
    package_root = root / "draftpaper_cli"
    checks: list[dict[str, str]] = []
    issues: list[str] = []

    release_files = sorted((package_root / "release_fixtures").glob("*.json"))
    for path in release_files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        schema_id = str(payload.get("schema_version") or "") if isinstance(payload, dict) else ""
        family = _schema_family(registry, schema_id) if schema_id else None
        resource = f"release_fixtures/{path.name}"
        checks.append({"resource": resource, "schema_id": schema_id, "family": str(family or "")})
        if family != "release_fixture":
            issues.append(f"{resource}:unregistered_or_wrong_schema:{schema_id or 'missing'}")

    capability_files = sorted((package_root / "capability_packs").glob("*/manifest.json"))
    for path in capability_files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        schema_id = str(payload.get("schema_version") or "") if isinstance(payload, dict) else ""
        family = _schema_family(registry, schema_id) if schema_id else None
        resource = f"capability_packs/{path.parent.name}/manifest.json"
        checks.append({"resource": resource, "schema_id": schema_id, "family": str(family or "")})
        if family != "research_capability_pack":
            issues.append(f"{resource}:unregistered_or_wrong_schema:{schema_id or 'missing'}")

    return {
        "schema_version": "dpl.packaged_resource_schema_report.v1",
        "status": "passed" if not issues else "failed",
        "release_fixture_count": len(release_files),
        "capability_pack_count": len(capability_files),
        "checks": checks,
        "issues": issues,
    }


def _build_release_manifest_isolated(repository: Path) -> dict[str, Any]:
    marker = "__DRAFTPAPER_RELEASE_MANIFEST__="
    bootstrap = (
        "import json, pathlib, sys\n"
        "root = pathlib.Path(sys.argv[1]).resolve()\n"
        "sys.path.insert(0, str(root))\n"
        "from draftpaper_cli.release_contract import build_release_manifest\n"
        f"print({marker!r} + json.dumps(build_release_manifest(), ensure_ascii=False))\n"
    )
    completed = subprocess.run(
        [sys.executable, "-I", "-c", bootstrap, str(repository)],
        cwd=repository,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=300,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"exit code {completed.returncode}"
        raise ValueError(f"Release manifest build failed in supplied root {repository}: {detail}")
    encoded = next((line[len(marker) :] for line in completed.stdout.splitlines() if line.startswith(marker)), "")
    try:
        payload = json.loads(encoded)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Release manifest build returned invalid output from supplied root {repository}.") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Release manifest build returned a non-object from supplied root {repository}.")
    return payload


def _build_release_manifest_local(repository: Path) -> dict[str, Any]:
    from .command_contracts import build_command_contracts
    from .command_registry import COMMAND_SPECS
    from .plugin_catalog import build_plugin_catalog_snapshot
    from .release_regression import FIXTURE_NAMES
    from .template_registry import discover_template_registry

    schema_registry = _load_schema_registry(repository)
    registry = discover_template_registry(repository / "draftpaper_cli" / "discipline_modules")
    catalog = build_plugin_catalog_snapshot(root=repository / "draftpaper_cli" / "discipline_modules", refresh=True)
    commands = build_command_contracts()
    skill = repository / "draftpaper_cli" / "resources" / "draftpaper_workflow" / "SKILL.md"
    skill_contract = skill.with_name("contract.json")
    available_release_fixtures = {path.stem for path in (repository / "draftpaper_cli" / "release_fixtures").glob("*.json")}
    release_fixtures = [fixture_id for fixture_id in FIXTURE_NAMES if fixture_id in available_release_fixtures]
    third_party = repository / "third_party" / "registry.json"
    constraints = repository / CI_CONSTRAINTS
    resource_schemas = _validate_packaged_resource_schemas(repository, schema_registry)
    ruff_audit = _load_optional_json(
        repository / "docs" / "quality" / "ruff_baseline_v0.35.0.json",
        {"status": "not_packaged", "baseline_version": "unknown", "current_count": None, "legacy_debt_count": None},
    )
    checkpoint_schema_ids = {
        "summary": "dpl.checkpoint_summary.v6",
        "artifact_manifest": "dpl.checkpoint_artifact_manifest.v2",
        "confirmation_request": "dpl.confirmation_request.v2",
        "change_report": "dpl.checkpoint_change_report.v1",
        "unresolved_issues": "dpl.checkpoint_unresolved_issues.v1",
        "agent_payload": "dpl.checkpoint_agent_payload.v3",
        "stage_audit": "dpl.checkpoint_stage_audit.v1",
        "decision_brief": "dpl.human_decision_brief.v1",
        "scientific_decision_fingerprint": "dpl.scientific_decision_fingerprint.v1",
        "confirmation_continuity_receipt": "dpl.confirmation_continuity_receipt.v1",
        "stage_activity": "dpl.stage_activity_bundle.v2",
        "readability_report": "dpl.checkpoint_readability_report.v1",
        "figure_claim_map": "dpl.figure_claim_map.v1",
    }
    checkpoint_schema_files = {
        "summary": "resources/schemas/checkpoint_summary_v6.json",
        "artifact_manifest": "resources/schemas/checkpoint_artifact_manifest_v2.json",
        "confirmation_request": "resources/schemas/confirmation_request_v2.json",
        "change_report": "resources/schemas/checkpoint_change_report_v1.json",
        "unresolved_issues": "resources/schemas/checkpoint_unresolved_issues_v1.json",
        "agent_payload": "resources/schemas/checkpoint_agent_payload_v3.json",
        "stage_audit": "resources/schemas/checkpoint_stage_audit_v1.json",
        "decision_brief": "resources/schemas/human_decision_brief_v1.json",
        "scientific_decision_fingerprint": "resources/schemas/scientific_decision_fingerprint_v1.json",
        "confirmation_continuity_receipt": "resources/schemas/confirmation_continuity_receipt_v1.json",
        "stage_activity": "resources/schemas/stage_activity_bundle_v2.json",
        "readability_report": "resources/schemas/checkpoint_readability_report_v1.json",
        "figure_claim_map": "resources/schemas/figure_claim_map_v1.json",
    }
    human_review_packet_schema_ids = {
        "packet": "dpl.human_review_packet.v1",
        "research_plan_brief": "dpl.research_plan_decision_brief.v1",
        "scientific_plan_fingerprint": "dpl.scientific_plan_fingerprint.v1",
        "operation_effect_fingerprint": "dpl.operation_effect_fingerprint.v1",
        "user_intent_receipt": "dpl.user_intent_receipt.v1",
    }
    human_review_packet_schema_files = {
        "packet": "resources/schemas/human_review_packet_v1.json",
        "research_plan_brief": "resources/schemas/research_plan_decision_brief_v1.json",
        "scientific_plan_fingerprint": "resources/schemas/scientific_plan_fingerprint_v1.json",
        "operation_effect_fingerprint": "resources/schemas/operation_effect_fingerprint_v1.json",
        "user_intent_receipt": "resources/schemas/user_intent_receipt_v1.json",
    }
    missing_checkpoint_schema_files = [
        relative for relative in checkpoint_schema_files.values() if not (repository / "draftpaper_cli" / relative).is_file()
    ]
    checkpoint_contract_status = (
        "passed"
        if all(_schema_family(schema_registry, schema_id) for schema_id in checkpoint_schema_ids.values())
        and not missing_checkpoint_schema_files
        else "failed"
    )
    missing_human_review_packet_schema_files = [
        relative for relative in human_review_packet_schema_files.values() if not (repository / "draftpaper_cli" / relative).is_file()
    ]
    human_review_packet_contract_status = (
        "passed"
        if all(_schema_family(schema_registry, schema_id) for schema_id in human_review_packet_schema_ids.values())
        and not missing_human_review_packet_schema_files
        else "failed"
    )
    required_commands: set[str] = {str(command) for command in REQUIRED_CLI_COMMANDS}
    registered_commands: set[str] = {str(command) for command in COMMAND_SPECS}
    missing_commands = sorted(required_commands - registered_commands)
    if missing_commands:
        raise ValueError("Required release commands are not registered in CommandSpec: " + ", ".join(missing_commands))
    environment_required_files = [
        "requirements/runtime-constraints.txt",
        "requirements/ci-constraints.txt",
        "config/environment.example",
        "docs/environment_deployment.md",
        "docs/environment_deployment.zh-CN.md",
        "docs/install_profiles.md",
        "docs/install_profiles.zh-CN.md",
        "tools/bootstrap_windows_environment.ps1",
        "draftpaper_cli/resources/schemas/core_environment_contract.schema.json",
        "draftpaper_cli/resources/schemas/environment_verification.schema.json",
    ]
    missing_environment_files = [
        relative for relative in environment_required_files if not (repository / relative).is_file()
    ]
    return {
        "schema_version": "dpl.release_manifest.v1",
        "package_version": _version(repository),
        "workflow_skill_sha256": _sha(skill),
        "workflow_contract_sha256": _sha(skill_contract),
        "plugin_count": registry["entry_count"],
        "fixture_count": sum(len(entry.get("fixtures") or []) for entry in registry["entries"]),
        "plugin_catalog_hash": catalog["catalog_hash"],
        "command_count": commands["command_count"],
        "command_contract_status": commands["status"],
        "required_cli_commands": list(REQUIRED_CLI_COMMANDS),
        "schema_registry_version": schema_registry["schema_version"],
        "resource_schema_status": resource_schemas["status"],
        "resource_schema_issue_count": len(resource_schemas["issues"]),
        "capability_pack_ids": sorted(path.parent.name for path in (repository / "draftpaper_cli" / "capability_packs").glob("*/manifest.json")),
        "release_fixture_ids": release_fixtures,
        "third_party_registry_sha256": _sha(third_party),
        "quality_gates": {
            "ruff_baseline_version": ruff_audit.get("baseline_version"),
            "ruff_status": ruff_audit.get("status"),
            "ruff_current_count": ruff_audit.get("current_count", ruff_audit.get("baseline_current_count")),
            "ruff_legacy_debt_count": ruff_audit.get("legacy_debt_count", 0 if ruff_audit.get("status") == "retired_zero_debt" else None),
            "no_new_debt": ruff_audit.get("no_new_debt", ruff_audit.get("status") in {"passed", "retired_zero_debt"}),
            "ruff_baseline_path": "docs/quality/ruff_baseline_v0.35.0.json",
        },
        "environment_contract": {
            "status": "passed" if not missing_environment_files else "failed",
            "core_schema": "dpl.core_environment_contract.v1",
            "verification_schema": "dpl.environment_verification.v1",
            "targets": ["control", "research", "publication", "agent"],
            "profiles": ["minimal", "plotting", "fulltext", "mcp", "browser", "mineru-agent"],
            "python_ranges": {
                "control": ">=3.10,<3.13",
                "plotting": ">=3.10,<3.13",
                "fulltext": ">=3.11,<3.13",
                "research": ">=3.11,<3.13",
                "publication": ">=3.11,<3.13",
                "agent": ">=3.11,<3.13",
                "browser": ">=3.11,<3.13",
            },
            "publication_core": ["pypdf", "pymupdf", "xelatex", "pdflatex", "bibtex", "kpsewhich"],
            "source_checkout_requires_system_git": True,
            "windows_bootstrap": "tools/bootstrap_windows_environment.ps1",
            "runtime_constraints": "requirements/runtime-constraints.txt",
            "environment_example": "config/environment.example",
            "missing_required_files": missing_environment_files,
            "vendored_paper_fetch_import_smoke": True,
            "browser_is_optional": True,
            "mineru_local_runtime_included": False,
            "doctor_read_only": True,
            "verification_isolated": True,
            "verification_command": "python -m draftpaper_cli verify-environment --target publication --compile-latex --output <output>",
        },
        "checkpoint_contract": {
            "status": checkpoint_contract_status,
            "summary_schema": checkpoint_schema_ids["summary"],
            "schema_files": checkpoint_schema_files,
            "missing_schema_files": missing_checkpoint_schema_files,
            "required_companions": [
                "stage_summary.zh-CN.html",
                "stage_summary.en.html",
                "stage_audit.json",
                "stage_summary.json",
                "human_decision_brief_v1.json",
                "scientific_decision_fingerprint_v1.json",
                "stage_activity_bundle.json",
                "artifact_manifest.json",
                "confirmation_request.json",
                "change_report.json",
                "unresolved_issues.json",
                "agent_payload.json",
                "checkpoint_readability_report.json",
                "checkpoint_readability_report.en.json",
                "figure_claim_map_v1.json",
            ],
            "agent_paths": ["project_relative_path", "absolute_path"],
        },
        "human_review_packet_contract": {
            "status": human_review_packet_contract_status,
            "schemas": human_review_packet_schema_ids,
            "schema_files": human_review_packet_schema_files,
            "missing_schema_files": missing_human_review_packet_schema_files,
            "default_agent_context_budget_bytes": 12288,
        },
        "review_governance": {
            "summary_schema": "dpl.checkpoint_summary.v6",
            "workflow_trace_schema": "dpl.workflow_trace.v2",
            "command_transaction_schema": "dpl.command_transaction.v3",
            "modes": ["manual", "balanced", "delegated"],
            "agent_decision_status": "agent_approved",
            "user_decision_status": "user_confirmed",
            "c3_human_only": True,
            "semantic_continuity_receipt": "dpl.confirmation_continuity_receipt.v1",
            "immutable_baseline_schema": "dpl.scientific_baseline_bundle.v1",
            "revision_cycle_schema": "dpl.revision_cycle.v1",
            "fact_registry_schema": "dpl.canonical_fact_registry.v2",
        },
        "research_code_sources": {
            "providers": ["github", "zenodo"],
            "metadata_only_default": True,
            "selection_modes": ["knowledge_base", "plugin_candidate", "historical_reference", "reproduction", "citation_only"],
            "archive_execution": "disabled",
        },
        "literature_identity_pipeline": {
            "query_contract_schema": "dpl.literature_query.v3",
            "fetch_policy_schema": "dpl.literature_fetch_policy.v1",
            "identity_schema": "dpl.paper_identity_resolution.v1",
            "postfetch_schema": "dpl.postfetch_relevance_assessment.v1",
            "quarantine_schema": "dpl.literature_quarantine_record.v1",
            "default_mode": "resolve_then_fetch_on_demand",
            "asset_profile": "none",
            "discipline_conflicts_symmetric": True,
            "unknown_discipline_auto_active": False,
            "postfetch_relevance_gate": True,
            "active_snapshot_reachability_required": True,
            "paper_fetch_runtime": {
                "version": "2.0.0",
                "upstream_commit": "10e30297df2cc7c354c1cb407a8514b22d2800d8",
                "license": "MIT",
                "vendored_fallback": True,
                "agent_skill_required": False,
            },
            "benchmark_thresholds": {
                "positive_recall": 0.95,
                "hard_negative_active_count": 0,
                "off_discipline_contamination_rate": 0.0,
                "bilingual_html_parity": 1.0,
            },
        },
        "release_security": {
            "license_identifier": _project_license(repository),
            "license_files": [name for name in ("LICENSE", "NOTICE") if (repository / name).is_file()],
            "github_actions_pinned": _actions_pinned(repository),
            "ci_constraints_sha256": _sha(constraints) if constraints.is_file() else "",
            "sbom_format": "CycloneDX JSON",
            "dependency_audit_scope": "project_dependency_graph",
            "ci_platforms": ["ubuntu", "windows", "macos_smoke"],
            "tag_build_verify": True,
            "public_pypi_publish": False,
        },
    }


def build_release_manifest(root: str | Path | None = None) -> dict[str, Any]:
    repository = Path(root).resolve() if root is not None else Path(__file__).resolve().parents[1]
    if root is not None:
        return _build_release_manifest_isolated(repository)
    return _build_release_manifest_local(repository)


def validate_release_manifest(root: str | Path | None = None) -> dict[str, Any]:
    repository = Path(root).resolve() if root else Path(__file__).resolve().parents[1]
    manifest_path = _release_manifest_path(repository)
    expected = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    current = build_release_manifest(repository if root is not None else None)
    raw_security = current.get("release_security")
    security: dict[str, Any] = raw_security if isinstance(raw_security, dict) else {}
    security_issues = []
    if security.get("license_identifier") != EXPECTED_LICENSE:
        security_issues.append("invalid_license_identifier")
    if security.get("license_files") != ["LICENSE", "NOTICE"]:
        security_issues.append("missing_license_files")
    if not security.get("github_actions_pinned"):
        security_issues.append("github_action_not_pinned_to_commit")
    if not security.get("ci_constraints_sha256"):
        security_issues.append("missing_ci_constraints")
    if current.get("resource_schema_status") != "passed" or current.get("resource_schema_issue_count"):
        security_issues.append("packaged_resource_schema_validation_failed")
    if (current.get("human_review_packet_contract") or {}).get("status") != "passed":
        security_issues.append("human_review_packet_schema_validation_failed")
    changed_fields = sorted(key for key in set(expected) | set(current) if expected.get(key) != current.get(key))
    return {
        "schema_version": "dpl.release_manifest_validation.v1",
        "status": "passed" if expected == current and not security_issues else "failed",
        "expected": expected,
        "current": current,
        "changed_fields": changed_fields,
        "security_issues": security_issues,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true", help="Validate the packaged release manifest without writing it.")
    args = parser.parse_args(argv)
    repository = Path(args.root).resolve()
    if args.check:
        report = validate_release_manifest(repository)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["status"] == "passed" else 1
    payload = build_release_manifest(repository)
    if args.write:
        _release_manifest_path(repository).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
