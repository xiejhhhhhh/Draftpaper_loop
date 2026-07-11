# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

"""Research-plan contracts and structured discipline-plugin sufficiency gates.

This module deliberately separates a scientific requirement from the plugin that
may satisfy it. A plugin is only considered executable support when its runtime
contract and validation level allow the requested local workflow. This prevents
the planner from treating a similarly named, mock-only, or external connector as
evidence that a main figure can actually be generated.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .discipline import infer_discipline_profile
from .discipline_modules import get_discipline_module
from .html_utils import write_html_report
from .project_scaffold import utc_now
from .project_state import load_project
from .passport import read_jsonl
from .plugin_runtime import RUNTIME_LEVELS, resolve_effective_runtime_level


DISCIPLINE_CONTRACT = "research_plan/discipline_contract.json"
CAPABILITY_CONTRACT = "research_plan/research_capability_contract.json"
SUFFICIENCY_REPORT = "research_plan/plugin_sufficiency_report.json"
SUFFICIENCY_HTML = "research_plan/plugin_sufficiency_report.html"
BINDING_PLAN = "research_plan/plugin_binding_plan.json"
GAP_PLAN = "research_plan/plugin_gap_plan.json"

LOCAL_RUNTIME_CLASSES = {"local_pure_python", "local_optional_dependency"}
EXTERNAL_RUNTIME_CLASSES = {"remote_api", "remote_server", "gpu_model", "laboratory_hardware"}


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _normalise(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")


def _tokens(value: object) -> set[str]:
    return {item for item in _normalise(value).split("_") if item and item not in {"data", "dataset", "analysis", "model", "method"}}


def _as_list(value: object) -> list[dict[str, Any]]:
    return [item for item in value or [] if isinstance(item, dict)] if isinstance(value, list) else []


def _claim_ids(figure: dict[str, Any]) -> list[str]:
    values = figure.get("claim_ids") or figure.get("claim_id") or []
    if isinstance(values, str):
        return [values]
    return [str(item) for item in values if str(item)] if isinstance(values, list) else []


def _figure_id(figure: dict[str, Any], index: int) -> str:
    return str(figure.get("figure_id") or figure.get("id") or f"figure_{index:02d}")


def _main_figure(figure: dict[str, Any]) -> bool:
    return str(figure.get("manuscript_role") or figure.get("role") or "main").lower() not in {"appendix", "supporting", "supplement"}


def _interface_roles(primary: str, secondary: str, requirements: list[dict[str, Any]]) -> list[str]:
    roles = []
    for requirement in requirements:
        if requirement.get("discipline") in {primary, secondary, "composite"}:
            value = str(requirement.get("role") or requirement.get("method_family") or "")
            if value:
                roles.append(value)
    return sorted(set(roles))


def _profile_roles(profile: dict[str, Any]) -> dict[str, str]:
    primary = str(profile.get("primary_discipline") or profile.get("discipline") or "default")
    roles = {primary: "scientific_domain"}
    for discipline in profile.get("secondary_disciplines") or []:
        name = str(discipline)
        roles[name] = "computational_or_cross_domain_support" if name == "machine_learning" else "cross_domain_support"
    return roles


def _extract_requirements(project_path: Path, profile: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    claims = _as_list(_read_json(project_path / "research_plan" / "claim_contract.json").get("claims"))
    storyboard_payload = _read_json(project_path / "results" / "figure_storyboard.json")
    figures = _as_list(storyboard_payload.get("figures") or storyboard_payload.get("storyboard"))
    figure_contracts = _read_json(project_path / "results" / "figure_contracts.json")
    planned_contracts = _as_list(
        figure_contracts.get("main_contracts")
        or figure_contracts.get("contracts")
        or figure_contracts.get("figures")
    )
    if planned_contracts:
        storyboard_by_id = {
            str(item.get("figure_id") or item.get("id") or ""): item
            for item in figures
            if item.get("figure_id") or item.get("id")
        }
        figures = [
            {
                **storyboard_by_id.get(str(contract.get("storyboard_id") or contract.get("figure_id") or contract.get("id") or ""), {}),
                **contract,
                "figure_id": str(contract.get("figure_id") or contract.get("storyboard_id") or contract.get("id") or ""),
                "required_data_roles": contract.get("required_data_roles") or contract.get("required_data") or contract.get("data_roles") or [],
                "method_families": contract.get("required_method_roles") or contract.get("required_methods") or contract.get("required_method") or contract.get("method_families") or [],
                "method_output_roles": contract.get("required_method_outputs") or contract.get("method_outputs") or [],
            }
            for contract in planned_contracts
            if str(contract.get("manuscript_role") or "main").lower() != "appendix"
        ]
    method_requirements = _read_json(project_path / "methods" / "method_requirements.json")
    if not figures:
        figures = [{
            "figure_id": "figure_01",
            "research_question": "Resolve the central research question.",
            "method_families": method_requirements.get("method_families") or [],
            "required_data_roles": method_requirements.get("required_data_features") or [],
            "manuscript_role": "main",
        }]
    primary = str(profile.get("primary_discipline") or profile.get("discipline") or "default")
    secondaries = [str(item) for item in profile.get("secondary_disciplines") or []]
    requirements: list[dict[str, Any]] = []
    for index, figure in enumerate(figures, start=1):
        figure_id = _figure_id(figure, index)
        is_main = _main_figure(figure)
        claim_ids = _claim_ids(figure) or [str(item.get("claim_id")) for item in claims if item.get("claim_id")]
        requirements.append({
            "requirement_id": f"figure:{figure_id}",
            "kind": "figure",
            "figure_id": figure_id,
            "claim_ids": claim_ids,
            "research_question": str(figure.get("research_question") or figure.get("scientific_question") or ""),
            "core": is_main,
            "discipline": "composite" if secondaries else primary,
            "required_method_outputs": list(figure.get("method_output_roles") or figure.get("required_method_outputs") or []),
            "required_review_roles": list(figure.get("review_rule_ids") or figure.get("review_requirements") or []),
        })
        data_roles = figure.get("required_data_roles") or figure.get("data_roles") or []
        if isinstance(data_roles, str):
            data_roles = [data_roles]
        for role in data_roles:
            role = str(role)
            requirements.append({
                "requirement_id": f"data:{figure_id}:{_normalise(role)}",
                "kind": "data",
                "figure_id": figure_id,
                "claim_ids": claim_ids,
                "role": role,
                "core": is_main,
                "discipline": primary,
                "required_outputs": [role],
            })
        families = figure.get("method_families") or figure.get("method_family") or method_requirements.get("method_families") or []
        if isinstance(families, str):
            families = [families]
        for family in families:
            family = str(family)
            requirements.append({
                "requirement_id": f"method:{figure_id}:{_normalise(family)}",
                "kind": "method",
                "figure_id": figure_id,
                "claim_ids": claim_ids,
                "method_family": family,
                "core": is_main,
                "discipline": "machine_learning" if "machine" in family or family in {"baseline_model", "ablation_study"} else primary,
                "required_outputs": list(figure.get("method_output_roles") or figure.get("required_method_outputs") or []),
            })
        requirements.append({
            "requirement_id": f"review:{figure_id}",
            "kind": "review",
            "figure_id": figure_id,
            "claim_ids": claim_ids,
            "core": False,
            "discipline": "composite" if secondaries else primary,
            "required_outputs": ["review_rule_assessment"],
            "activation_stage": "post_results",
            "activation_policy": "Select applicable rules only when this figure has a data or method plugin execution trace.",
        })
    return requirements, {"claims": claims, "figures": figures, "method_requirements": method_requirements}


def resolve_research_capabilities(project: str | Path) -> dict[str, Any]:
    """Resolve final discipline and capability contracts from planned research artifacts."""
    state = load_project(project)
    profile = infer_discipline_profile(state.path)
    requirements, sources = _extract_requirements(state.path, profile)
    roles = _profile_roles(profile)
    primary = str(profile.get("primary_discipline") or profile.get("discipline") or "default")
    secondaries = [str(item) for item in profile.get("secondary_disciplines") or []]
    interfaces = [
        {
            "interface_id": f"{primary}_to_{secondary}",
            "disciplines": [primary, secondary],
            "data_owner": primary,
            "method_owner": secondary if secondary == "machine_learning" else primary,
            "review_owners": [primary, secondary],
            "capability_roles": _interface_roles(primary, secondary, requirements),
        }
        for secondary in secondaries
    ]
    discipline_contract = {
        "status": "written",
        "generated_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "primary_discipline": primary,
        "secondary_disciplines": secondaries,
        "discipline_modules": list(profile.get("discipline_modules") or ["default", primary]),
        "discipline_roles": roles,
        "evidence": {
            "matched_terms": list(profile.get("matched_terms") or []),
            "discipline_scores": dict(profile.get("discipline_scores") or {}),
            "source_artifacts": ["project.json", "research_plan/claim_contract.json", "results/figure_storyboard.json", "methods/method_requirements.json"],
        },
        "cross_discipline_interfaces": interfaces,
    }
    capability_contract = {
        "status": "written",
        "generated_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "discipline_contract": DISCIPLINE_CONTRACT,
        "requirements": requirements,
        "claim_count": len(sources["claims"]),
        "figure_count": len(sources["figures"]),
        "policy": "Every main figure requires a claim, data capability, method capability, run output, and review-rule route. Missing capabilities must enter rescue instead of silent fallback generation.",
    }
    _write_json(state.path / DISCIPLINE_CONTRACT, discipline_contract)
    _write_json(state.path / CAPABILITY_CONTRACT, capability_contract)
    return {"status": "written", "project_path": str(state.path), "discipline_contract": DISCIPLINE_CONTRACT, "research_capability_contract": CAPABILITY_CONTRACT, "primary_discipline": primary, "secondary_disciplines": secondaries, "requirement_count": len(requirements)}


def _catalog(profile: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    hints = get_discipline_module(profile).method_blueprint_hints({})
    return {
        "data": [dict(item) for item in hints.get("data_acquisition_hints") or [] if isinstance(item, dict)],
        "method": [dict(item) for item in hints.get("method_template_hints") or [] if isinstance(item, dict)],
        "review": [dict(item) for item in hints.get("review_rule_hints") or [] if isinstance(item, dict)],
    }


def _candidate_terms(candidate: dict[str, Any], kind: str) -> set[str]:
    fields = {
        "data": ["connector_id", "display_name", "data_formats", "access_modes", "aliases", "variants"],
        "method": ["template_id", "display_name", "method_family", "input_roles", "output_artifacts", "figure_groups", "aliases", "variants"],
        "review": ["rule_id", "display_name", "rule_family", "applicable_methods", "applicable_data_roles", "aliases", "variants"],
    }[kind]
    result: set[str] = set()
    for field in fields:
        value = candidate.get(field)
        values = value if isinstance(value, list) else [value]
        for item in values:
            result.update(_tokens(item))
    return result


def _candidate_id(candidate: dict[str, Any], kind: str) -> str:
    return str(candidate.get({"data": "connector_id", "method": "template_id", "review": "rule_id"}[kind]) or "")


def _has_local_template(candidate: dict[str, Any], kind: str) -> bool:
    plugin_id = _candidate_id(candidate, kind)
    directory = {"data": "data_connectors", "method": "method_templates", "review": "review_rules"}.get(kind, "")
    if not plugin_id or not directory:
        return False
    root = Path(__file__).resolve().parent / "discipline_modules"
    return any(path.exists() for path in root.glob(f"*/{directory}/{plugin_id}/template.py"))


def _effective_runtime_level(project_path: Path, candidate: dict[str, Any], kind: str) -> tuple[str, str]:
    plugin_id = _candidate_id(candidate, kind)
    static_level = str(candidate.get("runtime_level") or "contract_only")
    events = []
    for relative in ("data/plugin_execution_ledger.jsonl", "methods/plugin_execution_ledger.jsonl"):
        events.extend(item for item in read_jsonl(project_path / relative) if str(item.get("plugin_id") or "") == plugin_id)
    return resolve_effective_runtime_level(static_level, events)


def _runtime_state(project_path: Path, candidate: dict[str, Any], kind: str) -> tuple[str, str, str]:
    runtime = str(candidate.get("runtime_class") or "local_optional_dependency")
    level, basis = _effective_runtime_level(project_path, candidate, kind)
    if level in {"project_validated", "live_validated"}:
        return "covered", basis, level
    if runtime in EXTERNAL_RUNTIME_CLASSES:
        return "blocked_external", "external_contract_without_live_evidence", level
    if level in {"code_generator", "fixture_executed"}:
        return "execution_required", basis, level
    return "partially_covered", "contract_only", level


def _structured_match(requirement: dict[str, Any], candidate: dict[str, Any]) -> tuple[int, list[str]]:
    kind = str(requirement["kind"])
    if kind == "review":
        # Review requirements are satisfied by the composite module's
        # applicable evidence-bound rules; they are not selected by a fake
        # keyword called "review".
        return 4, ["composite_discipline_review_rule"]
    if kind == "data":
        target = _normalise(requirement.get("role"))
    elif kind == "method":
        target = _normalise(requirement.get("method_family"))
    else:
        target = "review"
    candidate_id = _normalise(_candidate_id(candidate, kind))
    reasons: list[str] = []
    score = 0
    if target and target == candidate_id:
        score += 12
        reasons.append("exact_plugin_identifier")
    candidate_terms = _candidate_terms(candidate, kind)
    target_terms = _tokens(target)
    overlap = len(target_terms & candidate_terms)
    if overlap:
        score += overlap * 2
        reasons.append("structured_role_overlap")
    if kind == "method" and target in _normalise(candidate.get("method_family")):
        score += 8
        reasons.append("method_family_match")
    if kind == "data" and target in _normalise(candidate.get("connector_id")):
        score += 8
        reasons.append("data_role_match")
    required_outputs = {_normalise(item) for item in requirement.get("required_outputs") or []}
    output_terms = {_normalise(item) for item in candidate.get("output_artifacts") or []}
    if required_outputs and required_outputs & output_terms:
        score += 3
        reasons.append("output_contract_overlap")
    return score, reasons


def _assess_requirement(project_path: Path, requirement: dict[str, Any], catalog: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    kind = str(requirement["kind"])
    if kind == "figure":
        return {
            **requirement,
            "state": "trace_pending",
            "matched_plugin_id": None,
            "matched_plugin": None,
            "match_score": 0,
            "match_reasons": ["validated_by_figure_plugin_trace"],
            "runtime_class": None,
            "validation_level": None,
            "alternatives": [],
        }
    candidates = catalog[kind]
    scored = []
    for candidate in candidates:
        score, reasons = _structured_match(requirement, candidate)
        # A single generic word such as "catalog" or "classifier" is not a
        # capability match. Require an identifier/family match or multiple
        # structured role signals before a plugin can be proposed.
        if score >= 4:
            scored.append({"candidate": candidate, "score": score, "reasons": reasons})
    scored.sort(key=lambda item: (-int(item["score"]), _candidate_id(item["candidate"], kind)))
    selected = scored[0] if scored else None
    if not selected:
        state = "missing"
    else:
        state, coverage_basis, runtime_level = _runtime_state(project_path, selected["candidate"], kind)
    candidate = selected["candidate"] if selected else {}
    return {
        **requirement,
        "state": state,
        "matched_plugin_id": _candidate_id(candidate, kind) or None,
        "matched_plugin": candidate or None,
        "match_score": int(selected["score"]) if selected else 0,
        "match_reasons": selected["reasons"] if selected else [],
        "runtime_class": candidate.get("runtime_class") if candidate else None,
        "validation_level": candidate.get("validation_level") if candidate else None,
        "runtime_level": runtime_level if selected else None,
        "coverage_basis": coverage_basis if selected else "no_matching_contract",
        "alternatives": [{"plugin_id": _candidate_id(item["candidate"], kind), "score": item["score"]} for item in scored[1:4]],
    }


def _render_sufficiency(report: dict[str, Any]) -> str:
    lines = ["# Plugin Sufficiency Report", "", f"Decision: `{report.get('decision')}`", "", "## Requirements", ""]
    for item in report.get("requirement_assessments") or []:
        lines.append(f"- `{item.get('requirement_id')}`: **{item.get('state')}**; plugin: `{item.get('matched_plugin_id') or 'none'}`")
    lines.extend(["", "## Rescue", ""])
    for item in report.get("rescue_tasks") or []:
        lines.append(f"- `{item.get('requirement_id')}` -> `{item.get('recommended_command')}`: {item.get('reason')}")
    return "\n".join(lines)


def assess_plugin_sufficiency(project: str | Path) -> dict[str, Any]:
    """Assess whether registered plugins can execute the planned core evidence."""
    state = load_project(project)
    contract = _read_json(state.path / CAPABILITY_CONTRACT)
    if not contract:
        resolve_research_capabilities(state.path)
        contract = _read_json(state.path / CAPABILITY_CONTRACT)
    discipline_contract = _read_json(state.path / DISCIPLINE_CONTRACT)
    profile = {
        "primary_discipline": discipline_contract.get("primary_discipline") or "default",
        "discipline": discipline_contract.get("primary_discipline") or "default",
        "secondary_disciplines": discipline_contract.get("secondary_disciplines") or [],
        "discipline_modules": discipline_contract.get("discipline_modules") or [],
    }
    catalog = _catalog(profile)
    assessments = [_assess_requirement(state.path, item, catalog) for item in _as_list(contract.get("requirements"))]
    core = [item for item in assessments if item.get("core") and item.get("kind") in {"data", "method"}]
    execution_pending = [item for item in core if item.get("state") == "execution_required"]
    blocking = [item for item in core if item.get("state") not in {"covered", "execution_required"}]
    rescue_tasks = [{
        "requirement_id": item["requirement_id"],
        "kind": item["kind"],
        "figure_id": item.get("figure_id"),
        "state": item["state"],
        "reason": "A required core-figure capability is not locally executable.",
        "recommended_command": "prepare-plugin-rescue",
        "search_scope": {"discipline": item.get("discipline"), "role": item.get("role") or item.get("method_family")},
    } for item in blocking]
    bindings = [{
        "requirement_id": item["requirement_id"],
        "figure_id": item.get("figure_id"),
        "kind": item["kind"],
        "plugin_id": item.get("matched_plugin_id"),
        "state": item["state"],
        "runtime_class": item.get("runtime_class"),
        "validation_level": item.get("validation_level"),
        "runtime_level": item.get("runtime_level"),
    } for item in assessments if item.get("state") in {"covered", "execution_required"} and item.get("matched_plugin_id")]
    decision = "rescue_required" if blocking else ("execution_required" if execution_pending else "pass")
    report = {
        "status": "written",
        "generated_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "decision": decision,
        "core_figure_decision": decision,
        "requirement_assessments": assessments,
        "covered_count": sum(item.get("state") == "covered" for item in assessments),
        "blocking_count": len(blocking),
        "execution_required_count": len(execution_pending),
        "rescue_tasks": rescue_tasks,
        "policy": "Contract-only, mock, plan, and fixture-only plugins cannot satisfy core figures. Only project-validated or live-validated outputs count; executable templates remain pending until a project run is verified.",
    }
    binding_plan = {"status": "written", "generated_at": utc_now(), "source_report": SUFFICIENCY_REPORT, "bindings": bindings}
    gap_plan = {"status": "written", "generated_at": utc_now(), "source_report": SUFFICIENCY_REPORT, "gaps": rescue_tasks, "requires_human_confirmation": bool(rescue_tasks)}
    _write_json(state.path / SUFFICIENCY_REPORT, report)
    _write_json(state.path / BINDING_PLAN, binding_plan)
    _write_json(state.path / GAP_PLAN, gap_plan)
    write_html_report(state.path / SUFFICIENCY_HTML, _render_sufficiency(report), title="Plugin Sufficiency Report")
    return {"status": "written", "project_path": str(state.path), "decision": report["decision"], "core_figure_decision": report["core_figure_decision"], "blocking_count": len(blocking), "report": SUFFICIENCY_REPORT}
