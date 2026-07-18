# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import hashlib
import re
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any
from ..discipline import infer_discipline_from_text, infer_discipline_profile
from ..discipline_modules import get_discipline_module
from ..html_utils import write_html_report
from ..project_scaffold import _write_json, utc_now
from ..project_state import load_project
from ..safe_fetch import SafeFetchError, fetch_text

from .common import (
    PluginCandidateError,
    RUNTIME_CLASSES,
    VALIDATION_LEVELS,
    _candidate_root,
    _privacy_scan_text,
    _read_json,
    _read_text,
    _render_candidate_summary,
    _safe_id,
)

from .extractors import (
    _criterion_type_for_rule_family,
    _review_rule_evidence_binding,
    _runtime_metadata,
    _threshold_validation_status,
    _validate_review_rule_fixture_pair,
)

def _method_template_candidates(module: Any, requested: str | None = None) -> list[dict[str, Any]]:
    templates = module.spec.method_template_dicts()
    if requested:
        wanted = requested.lower()
        templates = [
            item for item in templates
            if wanted in item.get("template_id", "").lower()
            or wanted in item.get("method_family", "").lower()
            or any(wanted in str(alias).lower() for alias in item.get("aliases") or [])
        ]
    return templates


def _genericity_report(text: str, manifest: dict[str, Any]) -> dict[str, Any]:
    project_specific_terms = []
    for term in ["beijing", "北京市", "3-6", "march", "june", "d:\\", "c:\\"]:
        if term in text.lower():
            project_specific_terms.append(term)
    placeholders = ["{{input_table}}", "{{target_column}}", "{{predictor_columns}}", "{{output_dir}}"]
    return {
        "status": "passed" if not project_specific_terms else "needs_generalization",
        "project_specific_terms": project_specific_terms,
        "recommended_placeholders": placeholders,
        "template_id": manifest.get("template_id") or manifest.get("plugin_id"),
    }


def summarize_plugin_candidates(project: str | Path, *, source_file: str | Path | None = None, method: str | None = None) -> dict[str, Any]:
    state = load_project(project)
    profile = infer_discipline_profile(state.path)
    module = get_discipline_module(profile)
    templates = _method_template_candidates(module, method)
    if not templates:
        templates = module.spec.method_template_dicts()[:1]
    source_text = _read_text(Path(source_file)) if source_file else _read_text(state.path / "methods" / "src" / "generated_pipeline.py")
    if not source_text:
        source_text = _read_text(state.path / "methods" / "scripts" / "run_analysis.py")
    candidates = []
    for template in templates:
        candidate_id = _safe_id(f"{profile['discipline']}_{template.get('template_id')}")
        root = _candidate_root(state.path, profile["discipline"], candidate_id)
        root.mkdir(parents=True, exist_ok=True)
        manifest = {
            "status": "candidate_summarized",
            "candidate_id": candidate_id,
            "generated_at": utc_now(),
            "project_id": state.metadata.get("project_id"),
            "discipline": profile["discipline"],
            "primary_discipline": profile.get("primary_discipline") or profile["discipline"],
            "secondary_disciplines": profile.get("secondary_disciplines") or [],
            "discipline_modules": profile.get("discipline_modules") or [profile["discipline"]],
            "plugin_type": "method_template",
            "plugin_id": f"{profile['discipline']}.method.{template.get('template_id')}",
            "template_id": template.get("template_id"),
            "method_family": template.get("method_family"),
            "aliases": template.get("aliases") or [],
            "input_roles": template.get("input_roles") or [],
            "output_artifacts": template.get("output_artifacts") or [],
            "figure_groups": template.get("figure_groups") or [],
            "source_file": "local_project_source_not_packaged",
            "source_policy": "candidate_only_no_direct_upload",
            "intended_merge_target": f"draftpaper_cli/discipline_modules/{profile['discipline']}/method_templates/{template.get('template_id')}",
            **_runtime_metadata(dict(template)),
        }
        _write_json(root / "candidate_manifest.json", manifest)
        (root / "source_excerpt.py").write_text(source_text[:20_000], encoding="utf-8")
        write_html_report(root / "candidate_summary.html", _render_candidate_summary(manifest), title="Plugin Candidate Summary")
        candidates.append({"candidate_id": candidate_id, "path": str(root), "manifest": str(root / "candidate_manifest.json")})
    return {
        "status": "written",
        "project_path": str(state.path),
        "discipline": profile["discipline"],
        "candidate_count": len(candidates),
        "candidates": candidates,
        "next_command": f'python -m draftpaper_cli.cli generalize-plugin-candidate --candidate "{candidates[0]["path"]}"' if candidates else "",
    }


def generalize_plugin_candidate(candidate: str | Path) -> dict[str, Any]:
    root = Path(candidate).resolve()
    if (root / "support_manifest.json").exists():
        raise PluginCandidateError("Support candidates cannot be generalized as formal discipline plugins; extract their review_rule backflow candidates instead.")
    manifest = _read_json(root / "candidate_manifest.json", {})
    if not manifest:
        raise PluginCandidateError(f"Missing candidate manifest: {root}")
    source = _read_text(root / "source_excerpt.py") or _read_text(root / "source_excerpt.md") or _read_text(root / "source_evidence_summary.md")
    generalized_dir = root / "generalized_template"
    generalized_dir.mkdir(parents=True, exist_ok=True)
    plugin_type = str(manifest.get("plugin_type") or "method_template")
    if plugin_type == "data_connector":
        data_connector = {
            "connector_id": manifest.get("connector_id"),
            "display_name": manifest.get("display_name"),
            "access_modes": manifest.get("access_modes") or [],
            "packages": manifest.get("packages") or [],
            "package_modules": manifest.get("package_modules") or [],
            "download_or_access": manifest.get("download_or_access") or [],
            "data_formats": manifest.get("data_formats") or [],
            "requires_credentials": bool(manifest.get("requires_credentials")),
            "credential_env_vars": manifest.get("credential_env_vars") or [],
            "template_paths": manifest.get("template_paths") or [],
            "fixture_paths": manifest.get("fixture_paths") or [],
            "genericity_rules": manifest.get("genericity_rules") or [],
            "source_skill_refs": manifest.get("source_skill_refs") or [f"{manifest.get('source')}:{manifest.get('source_skill_id')}"],
            "provenance_notes": manifest.get("provenance_notes") or "Candidate data connector generalized from skill/source text.",
            **_runtime_metadata(manifest),
        }
        _write_json(generalized_dir / "data_connector.json", data_connector)
        template = "\n".join([
            "# Copyright (c) 2026 Jinray Xie",
            "# Contact: xiejinhui22@mails.ucas.ac.cn",
            "# Source-available for non-commercial use only; commercial use requires written authorization.",
            "",
            "from __future__ import annotations",
            "",
            "from pathlib import Path",
            "from typing import Any",
            "",
            "",
            "def prepare_data_connector(*, output_dir: Path, parameters: dict[str, Any] | None = None) -> dict[str, Any]:",
            "    \"\"\"Prepare a reusable data connector without embedding private project inputs.\"\"\"",
            "    output_dir.mkdir(parents=True, exist_ok=True)",
            "    params = dict(parameters or {})",
            "    return {",
            f"        'connector_id': {data_connector['connector_id']!r},",
            "        'status': 'template_ready_for_project_binding',",
            "        'output_dir': str(output_dir),",
            "        'parameter_keys': sorted(str(key) for key in params.keys()),",
            "    }",
            "",
            "SOURCE_DERIVATION_METADATA = {",
            f"    'source': {manifest.get('source')!r},",
            f"    'source_skill_id': {manifest.get('source_skill_id')!r},",
            f"    'matched_terms': {list(manifest.get('matched_terms') or [])!r},",
            "    'source_text_copied': False,",
            "}",
        ])
        (generalized_dir / "template.py").write_text(template, encoding="utf-8")
        report = {
            "status": "written",
            "generated_at": utc_now(),
            "candidate_id": manifest.get("candidate_id"),
            "plugin_type": "data_connector",
            "template_path": str(generalized_dir / "template.py"),
            "data_connector_path": str(generalized_dir / "data_connector.json"),
            "rules": [
                "Parameterize dataset ids, dates, regions, cohorts, credentials, and output paths.",
                "Do not promote connectors until a public or synthetic fixture validates access-shape assumptions.",
            ],
        }
        _write_json(root / "genericity_report.json", _genericity_report(json.dumps(data_connector, ensure_ascii=False), manifest))
        _write_json(root / "generalization_report.json", report)
        return report
    if plugin_type == "review_rule":
        review_rule = {
            "rule_id": manifest.get("rule_id") or manifest.get("rule_group_id"),
            "rule_group_id": manifest.get("rule_group_id") or manifest.get("rule_id"),
            "display_name": manifest.get("display_name"),
            "rule_family": manifest.get("rule_family"),
            "criterion_type": manifest.get("criterion_type") or _criterion_type_for_rule_family(str(manifest.get("rule_family") or "")),
            "applicable_disciplines": manifest.get("applicable_disciplines") or [manifest.get("discipline")],
            "applicable_methods": manifest.get("applicable_methods") or [],
            "applicable_data_roles": manifest.get("applicable_data_roles") or [],
            "evidence_roles": manifest.get("evidence_roles") or [],
            "evidence_binding": manifest.get("evidence_binding") or _review_rule_evidence_binding(
                str(manifest.get("rule_family") or "discipline_review"),
                list(manifest.get("evidence_roles") or []),
            ),
            "checks": manifest.get("checks") or [],
            "metric_family": manifest.get("metric_family"),
            "unit_or_scale": manifest.get("unit_or_scale"),
            "threshold_policy": manifest.get("threshold_policy") or {"mode": "contextual"},
            "threshold_source": manifest.get("threshold_source") or {"type": "source_skill_statement"},
            "threshold_mode": manifest.get("threshold_mode") or (manifest.get("threshold_policy") or {}).get("mode") or "contextual",
            "threshold_validation_status": manifest.get("threshold_validation_status") or _threshold_validation_status(
                manifest.get("threshold_policy") or {"mode": "contextual"},
                manifest.get("threshold_source") or {"type": "source_skill_statement"},
            ),
            "minimum_sample_policy": manifest.get("minimum_sample_policy"),
            "model_family": manifest.get("model_family"),
            "blocking_level": manifest.get("blocking_level") or "warn_and_repair",
            "failure_route": manifest.get("failure_route") or "human_checkpoint",
            "pipeline_hooks": manifest.get("pipeline_hooks") or {},
            "maturity": manifest.get("maturity") or "candidate",
            "deployment_state": manifest.get("deployment_state") or "review_rule_candidate",
            "human_confirmation_required": bool(manifest.get("human_confirmation_required", True)),
            "review_question": manifest.get("review_question") or "Does the available evidence satisfy this discipline-aware review condition?",
            "scientific_risk": manifest.get("scientific_risk") or "The manuscript may make a claim that is not supported by the available evidence.",
            "minimum_evidence_required": manifest.get("minimum_evidence_required") or manifest.get("evidence_roles") or [],
            "sample_unit_policy": manifest.get("sample_unit_policy"),
            "metric_dimension_policy": manifest.get("metric_dimension_policy"),
            "allowed_claim_strength": manifest.get("allowed_claim_strength") or "exploratory",
            "repair_priority": manifest.get("repair_priority") or [manifest.get("failure_route") or "human_checkpoint"],
            "manual_review_triggers": manifest.get("manual_review_triggers") or [],
            "non_goals": manifest.get("non_goals") or [],
            "fixture_paths": manifest.get("fixture_paths") or [],
            "positive_fixture_refs": manifest.get("positive_fixture_refs") or [path for path in manifest.get("fixture_paths") or [] if "positive" in str(path).lower()],
            "negative_fixture_refs": manifest.get("negative_fixture_refs") or [path for path in manifest.get("fixture_paths") or [] if "negative" in str(path).lower()],
            "source_skill_refs": manifest.get("source_skill_refs") or [],
            "backflow_source_type": manifest.get("backflow_source_type") or "explicit_review",
            "support_layer_signal_refs": manifest.get("support_layer_signal_refs") or [],
            "aliases": manifest.get("aliases") or [],
            "variants": manifest.get("variants") or [],
            "provenance_notes": manifest.get("provenance_notes") or "Candidate review rule generalized from skill/source text.",
            **_runtime_metadata(manifest),
        }
        _write_json(generalized_dir / "review_rule.json", review_rule)
        template = "\n".join([
            "# Copyright (c) 2026 Jinray Xie",
            "# Contact: xiejinhui22@mails.ucas.ac.cn",
            "# Source-available for non-commercial use only; commercial use requires written authorization.",
            "",
            "from __future__ import annotations",
            "",
            "",
            "def evaluate_rule(evidence: dict[str, object]) -> dict[str, object]:",
            "    \"\"\"Evaluate a generalized review rule against evidence roles.",
            "",
            "    Replace this scaffold with a discipline fixture-tested implementation before promotion.",
            "    \"\"\"",
            "    return {",
            f"        'rule_id': {review_rule['rule_id']!r},",
            "        'status': 'requires_fixture_implementation',",
            "        'evidence_keys': sorted(str(key) for key in evidence.keys()),",
            "    }",
            "",
            "SOURCE_DERIVATION_METADATA = {",
            f"    'source': {manifest.get('source')!r},",
            f"    'source_skill_id': {manifest.get('source_skill_id')!r},",
            f"    'matched_terms': {list(manifest.get('matched_terms') or [])!r},",
            "    'source_text_copied': False,",
            "}",
        ])
        (generalized_dir / "template.py").write_text(template, encoding="utf-8")
        report = {
            "status": "written",
            "generated_at": utc_now(),
            "candidate_id": manifest.get("candidate_id"),
            "plugin_type": "review_rule",
            "template_path": str(generalized_dir / "template.py"),
            "review_rule_path": str(generalized_dir / "review_rule.json"),
            "rules": [
                "Review rules must declare discipline, evidence roles, threshold policy, threshold source, and failure route.",
                "Do not promote fixed thresholds unless a discipline convention, journal guideline, or benchmark source is documented.",
            ],
        }
        _write_json(root / "genericity_report.json", _genericity_report(json.dumps(review_rule, ensure_ascii=False), manifest))
        _write_json(root / "generalization_report.json", report)
        return report
    method_template = {
        "template_id": manifest.get("template_id"),
        "display_name": manifest.get("display_name"),
        "discipline": manifest.get("discipline"),
        "method_family": manifest.get("method_family"),
        "input_roles": manifest.get("input_roles") or [],
        "optional_roles": manifest.get("optional_roles") or [],
        "packages": manifest.get("packages") or [],
        "package_modules": manifest.get("package_modules") or [],
        "output_artifacts": manifest.get("output_artifacts") or [],
        "figure_groups": manifest.get("figure_groups") or [],
        "formula_families": manifest.get("formula_families") or [],
        "validation_checks": manifest.get("validation_checks") or [],
        "aliases": manifest.get("aliases") or [],
        "variants": manifest.get("variants") or [],
        "genericity_rules": manifest.get("genericity_rules") or [],
        **_runtime_metadata(manifest),
    }
    _write_json(generalized_dir / "method_template.json", method_template)
    template = "\n".join([
        "# Copyright (c) 2026 Jinray Xie",
        "# Contact: xiejinhui22@mails.ucas.ac.cn",
        "# Source-available for non-commercial use only; commercial use requires written authorization.",
        "",
        "from __future__ import annotations",
        "",
        "from pathlib import Path",
        "",
        "",
        "def run_template(*, input_table: Path, output_dir: Path, target_column: str = '{{target_column}}') -> dict[str, object]:",
        '    """Generalized method template derived from a completed Draftpaper-loop project."""',
        "    output_dir.mkdir(parents=True, exist_ok=True)",
        "    return {",
        f"        'template_id': '{manifest.get('template_id')}',",
        "        'input_table': str(input_table),",
        "        'target_column': target_column,",
        "        'status': 'template_ready_for_project_binding',",
        "    }",
        "",
        "SOURCE_DERIVATION_METADATA = {",
        f"    'source': {manifest.get('source')!r},",
        f"    'source_skill_id': {manifest.get('source_skill_id')!r},",
        f"    'matched_terms': {list(manifest.get('matched_terms') or [])!r},",
        "    'source_text_copied': False,",
        "}",
    ])
    (generalized_dir / "template.py").write_text(template, encoding="utf-8")
    report = {
        "status": "written",
        "generated_at": utc_now(),
        "candidate_id": manifest.get("candidate_id"),
        "plugin_type": "method_template",
        "template_path": str(generalized_dir / "template.py"),
        "method_template_path": str(generalized_dir / "method_template.json"),
        "rules": [
            "No local file paths, API keys, fixed regions, fixed dates, or project-specific sample IDs.",
            "Expose data columns, output paths, and optional groups as parameters.",
        ],
    }
    _write_json(root / "genericity_report.json", _genericity_report(template, manifest))
    _write_json(root / "generalization_report.json", report)
    return report


def validate_plugin_candidate(candidate: str | Path) -> dict[str, Any]:
    root = Path(candidate).resolve()
    if (root / "support_manifest.json").exists():
        raise PluginCandidateError("Support candidates are not formal plugin candidates. Validate their extracted data_connector, method_template, or review_rule backflow candidates instead.")
    manifest = _read_json(root / "candidate_manifest.json", {})
    if not manifest:
        raise PluginCandidateError(f"Missing candidate manifest: {root}")
    contribution_texts = []
    for path in [
        root / "generalized_template" / "template.py",
        root / "generalized_template" / "data_connector.json",
        root / "generalized_template" / "method_template.json",
        root / "generalized_template" / "review_rule.json",
        root / "candidate_manifest.json",
    ]:
        contribution_texts.append(_read_text(path))
    raw_source_privacy = _privacy_scan_text(_read_text(root / "source_excerpt.py") or _read_text(root / "source_excerpt.md") or _read_text(root / "source_evidence_summary.md"))
    privacy = _privacy_scan_text("\n".join(contribution_texts))
    genericity = _genericity_report("\n".join(contribution_texts), manifest)
    overlap = detect_plugin_overlap(candidate)
    schema = _candidate_schema_report(manifest, root)
    plugin_type = str(manifest.get("plugin_type") or "method_template")
    checked_files = ["generalized_template/template.py"]
    if plugin_type == "review_rule":
        checked_files.extend([
            "generalized_template/review_rule.json",
            "rule_rationale.md",
            "positive_fixture.json",
            "negative_fixture.json",
        ])
    elif plugin_type == "data_connector":
        checked_files.append("generalized_template/data_connector.json")
    else:
        checked_files.append("generalized_template/method_template.json")
    missing_checked_files = [path for path in checked_files if not (root / path).exists()]
    fixture_contract = (
        _validate_review_rule_fixture_pair(root, manifest)
        if plugin_type == "review_rule" and not missing_checked_files
        else {
            "status": "passed" if not missing_checked_files else "failed",
            "validation_level": "file_presence",
            "runtime_execution_performed": False,
            "fixtures": [],
            "problems": [f"missing:{path}" for path in missing_checked_files],
        }
    )
    fixture_status = fixture_contract["status"]
    validation = {
        "status": "passed" if privacy["status"] == "passed" and genericity["status"] == "passed" and schema["status"] == "passed" and fixture_status == "passed" else "failed",
        "generated_at": utc_now(),
        "candidate_id": manifest.get("candidate_id"),
        "privacy_scan": privacy,
        "raw_source_privacy_scan": raw_source_privacy,
        "genericity_report": genericity,
        "schema_report": schema,
        "overlap_report": overlap,
        "fixture_test_report": {
            "status": fixture_status,
            "checked_files": checked_files,
            "missing_files": missing_checked_files,
            "validation_level": fixture_contract.get("validation_level"),
            "runtime_execution_performed": fixture_contract.get("runtime_execution_performed", False),
            "fixtures": fixture_contract.get("fixtures") or [],
            "problems": fixture_contract.get("problems") or [],
        },
    }
    _write_json(root / "privacy_scan.json", privacy)
    _write_json(root / "genericity_report.json", genericity)
    _write_json(root / "overlap_report.json", overlap)
    _write_json(root / "schema_report.json", schema)
    _write_json(root / "validation_report.json", validation)
    return validation


def promote_plugin_candidate(
    candidate: str | Path,
    *,
    require_human_confirmation: bool = False,
    dry_run: bool = True,
    target_root: str | Path | None = None,
) -> dict[str, Any]:
    """Prepare or perform a guarded promotion into formal discipline modules.

    This command is intentionally narrow: only validated ``data_connector``,
    ``method_template``, and ``review_rule`` candidates can target
    ``discipline_modules``. Support-layer candidates must remain outside formal
    discipline plugin directories, although their extracted review-rule backflow
    candidates can be promoted after validation.
    """

    root = Path(candidate).resolve()
    support_manifest = _read_json(root / "support_manifest.json", {})
    if support_manifest:
        raise PluginCandidateError("Support candidates cannot be promoted into discipline_modules; promote extracted formal review_rule candidates instead.")
    manifest = _read_json(root / "candidate_manifest.json", {})
    if not manifest:
        raise PluginCandidateError(f"Missing candidate manifest: {root}")
    plugin_type = str(manifest.get("plugin_type") or "")
    allowed = {"data_connector", "method_template", "review_rule"}
    if plugin_type not in allowed:
        raise PluginCandidateError(f"Unsupported formal plugin type for promotion: {plugin_type}")
    validation = _read_json(root / "validation_report.json", {})
    if validation.get("status") != "passed":
        raise PluginCandidateError("validate-plugin-candidate must pass before promotion.")
    if not require_human_confirmation:
        raise PluginCandidateError("Promotion requires --require-human-confirmation to prevent unreviewed discipline module writes.")

    from ..third_party_provenance import ThirdPartyProvenanceError, validate_candidate_promotion_provenance

    try:
        promotion_provenance = validate_candidate_promotion_provenance(manifest)
    except ThirdPartyProvenanceError as exc:
        raise PluginCandidateError(str(exc)) from exc

    if plugin_type == "review_rule":
        generalized_rule = _read_json(root / "generalized_template" / "review_rule.json", {})
        maturity = str(generalized_rule.get("maturity") or manifest.get("maturity") or "candidate")
        if maturity not in {"runnable", "mature", "paper_integrated", "runtime_integrated"}:
            raise PluginCandidateError(
                "Review-rule promotion requires maturity=runnable or higher after an executable discipline fixture has been reviewed."
            )

    discipline = _safe_id(str(manifest.get("discipline") or manifest.get("primary_discipline") or "default"))
    if plugin_type == "data_connector":
        kind_dir = "data_connectors"
        plugin_id = _safe_id(str(manifest.get("connector_id") or manifest.get("candidate_id") or "data_connector"))
        required_generalized = root / "generalized_template" / "data_connector.json"
    elif plugin_type == "review_rule":
        kind_dir = "review_rules"
        plugin_id = _safe_id(str(manifest.get("rule_id") or manifest.get("candidate_id") or "review_rule"))
        required_generalized = root / "generalized_template" / "review_rule.json"
    else:
        kind_dir = "method_templates"
        plugin_id = _safe_id(str(manifest.get("template_id") or manifest.get("candidate_id") or "method_template"))
        required_generalized = root / "generalized_template" / "method_template.json"
    if not required_generalized.exists():
        raise PluginCandidateError(f"Missing generalized template file: {required_generalized}")

    module_root = Path(target_root).resolve() if target_root else Path(__file__).resolve().parent / "discipline_modules"
    target_dir = module_root / discipline / kind_dir / plugin_id
    overlap = detect_plugin_overlap(root)
    promotion_mode = "augment_existing" if overlap.get("decision") == "merge_with_existing" else "create_new"
    canonical_manifest = _canonical_promoted_manifest(manifest, _read_json(required_generalized, {}), plugin_type)
    canonical_manifest.update(promotion_provenance)
    canonical_manifest["merge_strategy"] = promotion_mode
    canonical_manifest["promotion_mode"] = promotion_mode
    canonical_manifest["intended_merge_target"] = str(target_dir)
    plan = {
        "status": "planned" if dry_run else "promoted",
        "generated_at": utc_now(),
        "candidate_id": manifest.get("candidate_id"),
        "plugin_type": plugin_type,
        "discipline": discipline,
        "source_candidate": str(root),
        "target_dir": str(target_dir),
        "dry_run": dry_run,
        "human_confirmation_required": True,
        "human_confirmation_received": require_human_confirmation,
        "policy": "Only generalized candidate files are copied; source evidence summaries and third-party source are not copied.",
        "promotion_mode": promotion_mode,
        "overlap_report": overlap,
        "runtime_registration": "available_after_write_via_manifest.json",
        "canonical_manifest": canonical_manifest,
        "provenance": promotion_provenance,
    }
    _write_json(root / "promotion_plan.json", plan)
    if dry_run:
        return plan

    target_dir.mkdir(parents=True, exist_ok=True)
    existing_manifest = _read_json(target_dir / "manifest.json", {})
    if existing_manifest:
        canonical_manifest = _merge_promoted_manifest(existing_manifest, canonical_manifest)
    elif promotion_mode == "augment_existing":
        canonical_manifest["augmentation_of"] = overlap.get("existing_matches") or []
    _copy_promotion_fixtures(root, target_dir, canonical_manifest, plugin_type)
    _write_json(target_dir / "manifest.json", canonical_manifest)
    template_path = root / "generalized_template" / "template.py"
    if template_path.exists() and not (target_dir / "template.py").exists():
        shutil.copy2(template_path, target_dir / "template.py")
    _write_json(target_dir / "PROMOTION_MANIFEST.json", plan)
    _write_json(target_dir / "PLUGIN_PROVENANCE.json", {
        "status": "written",
        "candidate_id": manifest.get("candidate_id"),
        "source": manifest.get("source"),
        "source_skill_id": manifest.get("source_skill_id"),
        "source_policy": manifest.get("source_policy"),
        "promotion_mode": promotion_mode,
        "overlap_report": overlap,
        "source_text_copied": False,
        **promotion_provenance,
    })
    return plan


def _canonical_promoted_manifest(
    candidate: dict[str, Any],
    generalized: dict[str, Any],
    plugin_type: str,
) -> dict[str, Any]:
    """Build the single runtime manifest consumed by automatic registration."""

    manifest = dict(generalized)
    manifest.update({
        "candidate_id": candidate.get("candidate_id"),
        "discipline": candidate.get("discipline") or candidate.get("primary_discipline") or generalized.get("discipline") or "default",
        "plugin_type": plugin_type,
        "maturity": generalized.get("maturity") or candidate.get("maturity") or "foundation",
        "aliases": list(dict.fromkeys(list(generalized.get("aliases") or []) + list(candidate.get("aliases") or []))),
        "variants": list(dict.fromkeys(list(generalized.get("variants") or []) + list(candidate.get("variants") or []))),
        "source_skill_refs": list(dict.fromkeys(list(generalized.get("source_skill_refs") or []) + list(candidate.get("source_skill_refs") or [f"{candidate.get('source')}:{candidate.get('source_skill_id')}"]))),
        "provenance_notes": generalized.get("provenance_notes") or candidate.get("provenance_notes") or "Promoted generalized plugin candidate.",
        **_runtime_metadata({**candidate, **generalized}),
    })
    if plugin_type == "data_connector":
        manifest.setdefault("connector_id", candidate.get("connector_id"))
        manifest.setdefault("template", "template.py")
    elif plugin_type == "method_template":
        manifest.setdefault("template_id", candidate.get("template_id"))
        manifest.setdefault("template", "template.py")
    else:
        rule_id = generalized.get("rule_id") or candidate.get("rule_id") or candidate.get("rule_group_id")
        manifest.setdefault("rule_id", rule_id)
        manifest.setdefault("rule_group_id", rule_id)
        manifest.setdefault("template", "template.py")
    return manifest


def _merge_promoted_manifest(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Merge duplicate contributions without weakening an existing runtime contract."""

    merged = dict(existing)
    for key, value in incoming.items():
        current = merged.get(key)
        if isinstance(current, list) and isinstance(value, list):
            merged[key] = list(dict.fromkeys(current + value))
        elif isinstance(current, dict) and isinstance(value, dict):
            merged[key] = {**current, **{name: item for name, item in value.items() if item not in (None, "", [], {})}}
        elif current in (None, "", [], {}):
            merged[key] = value
    merged["merge_strategy"] = "augment_existing"
    merged["promotion_mode"] = "augment_existing"
    merged["merged_candidate_ids"] = list(dict.fromkeys(list(existing.get("merged_candidate_ids") or []) + [str(incoming.get("candidate_id") or "")]))
    return merged


def _copy_promotion_fixtures(root: Path, target_dir: Path, manifest: dict[str, Any], plugin_type: str) -> None:
    fixture_paths: list[str] = []
    if plugin_type == "review_rule":
        for source_name, target_name in [("positive_fixture.json", "fixture_positive.json"), ("negative_fixture.json", "fixture_negative.json")]:
            source = root / source_name
            if source.exists():
                shutil.copy2(source, target_dir / target_name)
                fixture_paths.append(target_name)
        manifest["fixture_paths"] = fixture_paths
        manifest["positive_fixture_refs"] = ["fixture_positive.json"] if "fixture_positive.json" in fixture_paths else []
        manifest["negative_fixture_refs"] = ["fixture_negative.json"] if "fixture_negative.json" in fixture_paths else []
    elif not manifest.get("fixture_paths"):
        manifest["fixture_paths"] = []


def _candidate_schema_report(manifest: dict[str, Any], root: Path) -> dict[str, Any]:
    plugin_type = str(manifest.get("plugin_type") or "method_template")
    missing: list[str] = []
    warnings: list[str] = []
    if manifest.get("runtime_class") not in RUNTIME_CLASSES:
        missing.append("valid_runtime_class")
    if manifest.get("validation_level") not in VALIDATION_LEVELS:
        missing.append("valid_validation_level")
    if plugin_type == "review_rule":
        for field in [
            "rule_id",
            "rule_family",
            "criterion_type",
            "applicable_disciplines",
            "evidence_roles",
            "evidence_binding",
            "threshold_policy",
            "threshold_source",
            "threshold_mode",
            "threshold_validation_status",
            "failure_route",
            "pipeline_hooks",
            "fixture_paths",
            "maturity",
            "deployment_state",
            "review_question",
            "scientific_risk",
            "minimum_evidence_required",
            "allowed_claim_strength",
            "repair_priority",
            "positive_fixture_refs",
            "negative_fixture_refs",
            "backflow_source_type",
            "support_layer_signal_refs",
        ]:
            if not manifest.get(field):
                missing.append(field)
        binding = manifest.get("evidence_binding") or {}
        if not isinstance(binding, dict):
            missing.append("valid_evidence_binding")
        else:
            for field in ["registry_record_types", "required_fields", "forbidden_conflicts"]:
                if field not in binding:
                    missing.append(f"evidence_binding.{field}")
        if "human_confirmation_required" not in manifest:
            missing.append("human_confirmation_required")
        hooks = manifest.get("pipeline_hooks") or {}
        allowed_hook_values = {"optional", "required", "not_applicable"}
        required_hooks = {
            "research_plan",
            "data_acquisition",
            "method_plan",
            "figure_contract",
            "result_support_checkpoint",
            "write_results",
            "write_discussion",
            "citation_audit",
            "reviewer_rescue_loop",
        }
        if set(hooks) != required_hooks:
            missing.append("complete_pipeline_hooks")
        elif any(str(value) not in allowed_hook_values for value in hooks.values()):
            missing.append("valid_pipeline_hook_values")
        threshold = manifest.get("threshold_policy") or {}
        source = manifest.get("threshold_source") or {}
        allowed_threshold_modes = {"fixed", "contextual", "comparative", "journal_guided", "human_confirmed", "none"}
        threshold_mode = manifest.get("threshold_mode") or threshold.get("mode")
        if threshold.get("mode") not in allowed_threshold_modes:
            missing.append("valid_threshold_policy_mode")
        if threshold_mode != threshold.get("mode"):
            missing.append("threshold_mode_matches_policy")
        if threshold.get("mode") == "fixed" and source.get("type") not in {"discipline_convention", "journal_guideline", "benchmark_comparison", "public_benchmark", "user_confirmation", "human_confirmed"}:
            missing.append("fixed_threshold_authoritative_source")
        if threshold.get("mode") == "journal_guided" and source.get("type") != "journal_guideline":
            missing.append("journal_guided_threshold_source")
        if manifest.get("deployment_state") == "promoted_review_rule" and manifest.get("maturity") not in {"runnable", "mature"}:
            missing.append("promoted_review_rule_requires_runnable_or_mature")
        for path_name in ["rule_rationale.md", "positive_fixture.json", "negative_fixture.json", "provenance_summary.json"]:
            if not (root / path_name).exists():
                missing.append(path_name)
        if not (root / "generalized_template" / "review_rule.json").exists():
            warnings.append("generalized_template/review_rule.json missing before generalization")
    elif plugin_type == "method_template":
        for field in ["template_id", "method_family", "input_roles", "output_artifacts"]:
            if not manifest.get(field):
                missing.append(field)
        if not (root / "generalized_template" / "method_template.json").exists():
            warnings.append("generalized_template/method_template.json missing before generalization")
    elif plugin_type == "data_connector":
        for field in ["connector_id", "access_modes", "data_formats", "source_policy"]:
            if not manifest.get(field):
                missing.append(field)
        if manifest.get("source_policy") != "candidate_only_no_direct_upload":
            missing.append("candidate_only_source_policy")
        if not (root / "generalized_template" / "data_connector.json").exists():
            warnings.append("generalized_template/data_connector.json missing before generalization")
    else:
        missing.append(f"unsupported_plugin_type:{plugin_type}")
    return {
        "status": "passed" if not missing else "failed",
        "plugin_type": plugin_type,
        "missing_fields": missing,
        "warnings": warnings,
    }


def detect_plugin_overlap(candidate: str | Path) -> dict[str, Any]:
    root = Path(candidate).resolve()
    manifest = _read_json(root / "candidate_manifest.json", {})
    discipline = str(manifest.get("discipline") or "default")
    module = get_discipline_module({"discipline": discipline})
    plugin_type = str(manifest.get("plugin_type") or "method_template")
    if plugin_type == "review_rule":
        target_id = str(manifest.get("rule_id") or manifest.get("rule_group_id") or "")
        existing = module.spec.review_rule_dicts()
        id_key = "rule_group_id"
        family_key = "rule_family"
    elif plugin_type == "data_connector":
        target_id = str(manifest.get("connector_id") or "")
        existing = module.spec.connector_dicts()
        id_key = "connector_id"
        family_key = "access_modes"
    else:
        target_id = str(manifest.get("template_id") or "")
        existing = module.spec.method_template_dicts()
        id_key = "template_id"
        family_key = "method_family"
    matches = []
    for item in existing:
        score = 0.0
        if item.get(id_key) == target_id or item.get("rule_id") == target_id:
            score += 0.7
        if plugin_type == "data_connector":
            existing_modes = set(str(value).lower() for value in item.get("access_modes") or [])
            candidate_modes = set(str(value).lower() for value in manifest.get("access_modes") or [])
            existing_formats = set(str(value).lower() for value in item.get("data_formats") or [])
            candidate_formats = set(str(value).lower() for value in manifest.get("data_formats") or [])
            existing_packages = set(str(value).lower() for value in item.get("packages") or [])
            candidate_packages = set(str(value).lower() for value in manifest.get("packages") or [])
            if existing_modes & candidate_modes:
                score += 0.15
            if existing_formats & candidate_formats:
                score += 0.15
            if existing_packages & candidate_packages:
                score += 0.1
        elif item.get(family_key) == manifest.get(family_key):
            score += 0.2
        aliases = set(str(a).lower() for a in item.get("aliases") or [])
        candidate_aliases = set(str(a).lower() for a in manifest.get("aliases") or [])
        if aliases & candidate_aliases:
            score += 0.1
        if score:
            matches.append({id_key: item.get(id_key), family_key: item.get(family_key), "overlap_score": round(score, 3)})
    decision = "merge_with_existing" if matches and max(m["overlap_score"] for m in matches) >= 0.7 else "new_plugin_candidate"
    report = {
        "status": "written",
        "decision": decision,
        "candidate_id": manifest.get("candidate_id"),
        "existing_matches": sorted(matches, key=lambda item: item["overlap_score"], reverse=True),
        "merge_action": "merge aliases, variants, fixtures, and source provenance into the existing discipline module" if decision == "merge_with_existing" else "add a new plugin directory under the discipline module after validation",
    }
    _write_json(root / "overlap_report.json", report)
    return report


def _support_backflow_provenance(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    support_candidate_ids = [str(item) for item in manifest.get("support_candidate_ids") or []]
    support_routes = [str(item) for item in manifest.get("backflow_from_support_routes") or []]
    source_root = root.parent
    while source_root.name and source_root.name != str(manifest.get("source_skill_id") or ""):
        if (source_root / "SKILL_DISPOSITION.json").exists():
            break
        if source_root.parent == source_root:
            break
        source_root = source_root.parent
    disposition = _read_json(source_root / "SKILL_DISPOSITION.json", {})
    support_manifests: list[dict[str, Any]] = []
    for support_record in disposition.get("support_candidates") or []:
        if support_candidate_ids and str(support_record.get("candidate_id")) not in support_candidate_ids:
            continue
        support_path = Path(str(support_record.get("path") or ""))
        support_manifest = _read_json(support_path / "support_manifest.json", {}) if support_path else {}
        backflow_links = _read_json(support_path / "review_rule_backflow_links.json", {}) if support_path else {}
        if support_manifest:
            support_manifests.append({
                "candidate_id": support_manifest.get("candidate_id"),
                "support_type": support_manifest.get("support_type"),
                "intended_support_target": support_manifest.get("intended_support_target"),
                "support_purpose": support_manifest.get("support_purpose"),
                "review_rule_backflow_candidate_ids": support_manifest.get("review_rule_backflow_candidate_ids") or [],
                "review_rule_backflow_scope": support_manifest.get("review_rule_backflow_scope") or {},
                "backflow_signal_scan": support_manifest.get("backflow_signal_scan") or backflow_links.get("backflow_signal_scan") or {},
                "capability_ir": support_manifest.get("capability_ir") or {},
                "backflow_links": backflow_links,
                "source_policy": support_manifest.get("source_policy"),
                "promotion_policy": support_manifest.get("promotion_policy"),
            })
    return {
        "status": "written",
        "generated_at": utc_now(),
        "candidate_id": manifest.get("candidate_id"),
        "plugin_type": manifest.get("plugin_type"),
        "source": manifest.get("source"),
        "source_skill_id": manifest.get("source_skill_id"),
        "backflow_from_support_routes": support_routes,
        "support_candidate_ids": support_candidate_ids,
        "support_candidates": support_manifests,
        "source_policy": "metadata_only; source_evidence_summary and third-party source files are intentionally excluded from contribution packages",
        "review_rule_backflow_policy": "Support candidates remain outside discipline_modules; only validated formal candidates can be promoted with human confirmation.",
    }
