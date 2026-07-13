# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

"""Turn on-disk plugin manifests into runtime discipline-module contracts."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from ..template_registry import discover_template_registry
from ..plugin_catalog import normalize_execution_contract
from ..scientific_plugin_runtime import apply_runnable_profile
from .base import DisciplineModule, DisciplineModuleSpec


def _module_root() -> Path:
    return Path(__file__).resolve().parent


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))


def _merge_list_values(existing: list[Any], incoming: list[Any]) -> list[Any]:
    merged: list[Any] = []
    seen: set[str] = set()
    for item in existing + incoming:
        marker = repr(item)
        if marker in seen:
            continue
        seen.add(marker)
        merged.append(item)
    return merged


def _merge_by_id(items: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    index_by_id: dict[str, int] = {}
    for item in items:
        value = str(item.get(key) or "")
        if not value:
            continue
        if value in index_by_id:
            result[index_by_id[value]] = _merge_plugin_records(result[index_by_id[value]], dict(item))
            continue
        index_by_id[value] = len(result)
        result.append(dict(item))
    return result


def _merge_plugin_records(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Augment an existing plugin while preserving its established contract."""

    merged = dict(existing)
    for key, value in incoming.items():
        current = merged.get(key)
        if isinstance(current, list) and isinstance(value, list):
            merged[key] = _merge_list_values(current, value)
        elif isinstance(current, dict) and isinstance(value, dict):
            merged[key] = {**current, **{name: item for name, item in value.items() if item not in (None, "", [], {})}}
        elif current in (None, "", [], {}):
            merged[key] = value
    if incoming.get("merge_strategy") == "augment_existing":
        merged["merge_strategy"] = "augment_existing"
        merged["promotion_mode"] = "augment_existing"
        merged["merged_candidate_ids"] = _merge_list_values([
            *[str(item) for item in existing.get("merged_candidate_ids") or []],
        ], [
            *[str(item) for item in incoming.get("merged_candidate_ids") or []],
            str(incoming.get("candidate_id") or ""),
        ])
    return merged


def _normalized_entry(entry: dict[str, Any]) -> dict[str, Any]:
    manifest = dict(entry.get("manifest_data") or {})
    kind = str(entry.get("kind") or "")
    relative = str(entry.get("path") or "")
    fixture_paths = [f"{relative}/{name}" for name in entry.get("fixtures") or []]
    template_path = f"{relative}/template.py" if entry.get("has_template") else ""
    manifest.setdefault("discipline", entry.get("discipline"))
    manifest.setdefault("maturity", entry.get("maturity") or "foundation")
    manifest.setdefault("runtime_class", entry.get("runtime_class") or "local_optional_dependency")
    manifest.setdefault("validation_level", entry.get("validation_level") or "plan_only")
    manifest.setdefault("runtime_level", entry.get("runtime_level") or "contract_only")
    execution_kind = {"connector": "data", "method": "method", "review": "review"}.get(kind, "review")
    manifest.setdefault("execution_contract", normalize_execution_contract(manifest, kind=execution_kind))
    if kind == "connector":
        manifest.setdefault("connector_id", entry.get("plugin_id"))
        manifest.setdefault("display_name", str(manifest.get("connector_id") or "").replace("_", " ").title())
        manifest.setdefault("template_paths", [template_path] if template_path else [])
        manifest.setdefault("fixture_paths", fixture_paths)
        manifest.setdefault("access_modes", ["local_files"])
        manifest.setdefault("packages", [])
        manifest.setdefault("package_modules", list(manifest.get("packages") or []))
        manifest.setdefault("data_formats", ["csv", "json"])
        manifest.setdefault("genericity_rules", ["Keep project-specific locations and credentials outside the reusable plugin."])
    elif kind == "method":
        manifest.setdefault("template_id", entry.get("plugin_id"))
        manifest.setdefault("display_name", str(manifest.get("template_id") or "").replace("_", " ").title())
        manifest.setdefault("method_family", manifest.get("template_id"))
        manifest.setdefault("input_roles", [])
        manifest.setdefault("optional_roles", [])
        manifest.setdefault("packages", [])
        manifest.setdefault("package_modules", list(manifest.get("packages") or []))
        manifest.setdefault("output_artifacts", [])
        manifest.setdefault("figure_groups", [])
        manifest.setdefault("formula_families", [])
        manifest.setdefault("validation_checks", [])
        manifest.setdefault("template_path", template_path)
        manifest.setdefault("fixture_paths", fixture_paths)
        manifest.setdefault("aliases", [])
        manifest.setdefault("variants", [])
        manifest.setdefault("genericity_rules", ["Parameterize inputs and do not embed project-specific records."])
    elif kind == "review":
        rule_id = manifest.get("rule_id") or manifest.get("rule_group_id") or entry.get("plugin_id")
        manifest.setdefault("rule_id", rule_id)
        manifest.setdefault("rule_group_id", rule_id)
        manifest.setdefault("display_name", str(rule_id or "").replace("_", " ").title())
        manifest.setdefault("rule_family", "discipline_review")
        manifest.setdefault("criterion_type", "scientific_quality_gate")
        manifest.setdefault("applicable_disciplines", [entry.get("discipline")])
        manifest.setdefault("checks", [])
        manifest.setdefault("evidence_roles", [])
        manifest.setdefault("evidence_binding", {"registry_record_types": [], "required_fields": [], "forbidden_conflicts": []})
        manifest.setdefault("threshold_policy", {"mode": "contextual"})
        manifest.setdefault("threshold_source", {"type": "discipline_convention", "citation_or_note": "foundation rule; requires project confirmation"})
        manifest.setdefault("threshold_mode", "contextual")
        manifest.setdefault("threshold_validation_status", "candidate_unverified")
        manifest.setdefault("failure_route", "human_checkpoint")
        manifest.setdefault("pipeline_hooks", {})
        manifest.setdefault("deployment_state", "review_rule_candidate")
        manifest.setdefault("human_confirmation_required", True)
        manifest.setdefault("review_question", manifest.get("display_name"))
        manifest.setdefault("scientific_risk", "Rule must be evaluated against project-specific evidence.")
        manifest.setdefault("minimum_evidence_required", list(manifest.get("evidence_roles") or []))
        manifest.setdefault("allowed_claim_strength", "exploratory")
        manifest.setdefault("repair_priority", ["human_checkpoint"])
        manifest.setdefault("template_path", template_path)
        manifest.setdefault("fixture_paths", fixture_paths)
    return apply_runnable_profile(manifest)


def discovered_plugin_specs(root: Path | None = None) -> dict[str, dict[str, list[dict[str, Any]]]]:
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for entry in discover_template_registry(root or _module_root()).get("entries") or []:
        discipline = str(entry.get("discipline") or "default")
        bucket = grouped.setdefault(discipline, {"connector": [], "method": [], "review": []})
        kind = str(entry.get("kind") or "")
        if kind in bucket:
            bucket[kind].append(_normalized_entry(entry))
    return grouped


def merge_manifest_plugins(module: DisciplineModule, root: Path | None = None) -> DisciplineModule:
    grouped = discovered_plugin_specs(root).get(module.spec.module_id, {})
    if not any(grouped.values()):
        return module
    spec = module.spec
    merged = replace(
        spec,
        data_connectors=_merge_by_id(spec.connector_dicts() + list(grouped.get("connector") or []), "connector_id"),
        method_templates=_merge_by_id(spec.method_template_dicts() + list(grouped.get("method") or []), "template_id"),
        review_rule_groups=_merge_by_id(spec.review_rule_dicts() + list(grouped.get("review") or []), "rule_id"),
        data_roles=_unique(list(spec.data_roles) + [role for item in grouped.get("method", []) for role in item.get("input_roles") or []]),
        method_families=_unique(list(spec.method_families) + [str(item.get("method_family") or "") for item in grouped.get("method", [])]),
        validation_checks=_unique(list(spec.validation_checks) + [check for item in grouped.get("method", []) for check in item.get("validation_checks") or []]),
    )
    runtime = DisciplineModule()
    runtime.spec = merged
    return runtime


def dynamic_manifest_module(discipline: str, root: Path | None = None) -> DisciplineModule | None:
    grouped = discovered_plugin_specs(root).get(discipline)
    if not grouped or not any(grouped.values()):
        return None
    method_templates = list(grouped.get("method") or [])
    spec = DisciplineModuleSpec(
        module_id=discipline,
        display_name=f"{discipline.replace('_', ' ').title()} workflow",
        keywords=_unique([discipline.replace("_", " ")] + [alias for item in method_templates for alias in item.get("aliases") or []]),
        data_roles=_unique([role for item in method_templates for role in item.get("input_roles") or []]),
        method_families=_unique([str(item.get("method_family") or "") for item in method_templates]),
        validation_checks=_unique([check for item in method_templates for check in item.get("validation_checks") or []]),
        figure_families=_unique([group for item in method_templates for group in item.get("figure_groups") or []]),
        formula_families=_unique([formula for item in method_templates for formula in item.get("formula_families") or []]),
        data_connectors=list(grouped.get("connector") or []),
        method_templates=method_templates,
        review_rule_groups=list(grouped.get("review") or []),
        maturity="foundation",
    )
    runtime = DisciplineModule()
    runtime.spec = spec
    return runtime
