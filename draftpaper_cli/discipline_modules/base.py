# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

from dataclasses import dataclass, field
import importlib.util
import os
from typing import Any


@dataclass(frozen=True)
class DataConnectorSpec:
    """Reusable, discipline-level data acquisition route."""

    connector_id: str
    display_name: str
    access_modes: list[str] = field(default_factory=list)
    packages: list[str] = field(default_factory=list)
    package_modules: list[str] = field(default_factory=list)
    download_or_access: list[str] = field(default_factory=list)
    data_formats: list[str] = field(default_factory=list)
    requires_credentials: bool = False
    credential_env_vars: list[str] = field(default_factory=list)
    template_paths: list[str] = field(default_factory=list)
    fixture_paths: list[str] = field(default_factory=list)
    genericity_rules: list[str] = field(default_factory=list)
    runtime_class: str = "local_optional_dependency"
    validation_level: str = "plan_only"

    def as_dict(self) -> dict[str, Any]:
        return {
            "connector_id": self.connector_id,
            "display_name": self.display_name,
            "access_modes": list(self.access_modes),
            "packages": list(self.packages),
            "package_modules": list(self.package_modules),
            "download_or_access": list(self.download_or_access),
            "data_formats": list(self.data_formats),
            "requires_credentials": self.requires_credentials,
            "credential_env_vars": list(self.credential_env_vars),
            "template_paths": list(self.template_paths),
            "fixture_paths": list(self.fixture_paths),
            "genericity_rules": list(self.genericity_rules),
            "runtime_class": self.runtime_class,
            "validation_level": self.validation_level,
        }


@dataclass(frozen=True)
class MethodTemplateSpec:
    """Reusable method-code template contract for a discipline module."""

    template_id: str
    display_name: str
    discipline: str
    method_family: str
    input_roles: list[str] = field(default_factory=list)
    optional_roles: list[str] = field(default_factory=list)
    packages: list[str] = field(default_factory=list)
    package_modules: list[str] = field(default_factory=list)
    output_artifacts: list[str] = field(default_factory=list)
    figure_groups: list[str] = field(default_factory=list)
    formula_families: list[str] = field(default_factory=list)
    validation_checks: list[str] = field(default_factory=list)
    template_path: str = ""
    fixture_paths: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    variants: list[str] = field(default_factory=list)
    genericity_rules: list[str] = field(default_factory=list)
    maturity: str = "foundation"
    runtime_class: str = "local_optional_dependency"
    validation_level: str = "plan_only"

    def as_dict(self) -> dict[str, Any]:
        return {
            "template_id": self.template_id,
            "display_name": self.display_name,
            "discipline": self.discipline,
            "method_family": self.method_family,
            "input_roles": list(self.input_roles),
            "optional_roles": list(self.optional_roles),
            "packages": list(self.packages),
            "package_modules": list(self.package_modules),
            "output_artifacts": list(self.output_artifacts),
            "figure_groups": list(self.figure_groups),
            "formula_families": list(self.formula_families),
            "validation_checks": list(self.validation_checks),
            "template_path": self.template_path,
            "fixture_paths": list(self.fixture_paths),
            "aliases": list(self.aliases),
            "variants": list(self.variants),
            "genericity_rules": list(self.genericity_rules),
            "maturity": self.maturity,
            "runtime_class": self.runtime_class,
            "validation_level": self.validation_level,
        }


@dataclass(frozen=True)
class ReviewRuleSpec:
    """Reusable discipline-aware review rule contract.

    Review rules are evidence-bound scientific checks. They are intentionally
    more explicit than legacy rule-group dictionaries so mined workflow, paper
    contract, and shared-capability skills cannot become global hard thresholds
    without declaring scope and provenance.
    """

    rule_id: str
    display_name: str
    rule_family: str
    criterion_type: str = "scientific_quality_gate"
    applicable_disciplines: list[str] = field(default_factory=list)
    applicable_methods: list[str] = field(default_factory=list)
    applicable_data_roles: list[str] = field(default_factory=list)
    evidence_roles: list[str] = field(default_factory=list)
    evidence_binding: dict[str, Any] = field(default_factory=dict)
    checks: list[str] = field(default_factory=list)
    metric_family: str | None = None
    unit_or_scale: str | None = None
    threshold_policy: dict[str, Any] = field(default_factory=dict)
    threshold_source: dict[str, Any] = field(default_factory=dict)
    threshold_mode: str = "contextual"
    threshold_validation_status: str = "candidate_unverified"
    minimum_sample_policy: str | None = None
    model_family: str | None = None
    blocking_level: str = "warn_and_repair"
    failure_route: str = "human_checkpoint"
    pipeline_hooks: dict[str, str] = field(default_factory=dict)
    maturity: str = "candidate"
    deployment_state: str = "review_rule_candidate"
    human_confirmation_required: bool = True
    review_question: str = ""
    scientific_risk: str = ""
    minimum_evidence_required: list[str] = field(default_factory=list)
    sample_unit_policy: str | None = None
    metric_dimension_policy: str | None = None
    allowed_claim_strength: str = "exploratory"
    repair_priority: list[str] = field(default_factory=list)
    manual_review_triggers: list[str] = field(default_factory=list)
    non_goals: list[str] = field(default_factory=list)
    template_path: str = ""
    fixture_paths: list[str] = field(default_factory=list)
    positive_fixture_refs: list[str] = field(default_factory=list)
    negative_fixture_refs: list[str] = field(default_factory=list)
    source_skill_refs: list[str] = field(default_factory=list)
    backflow_source_type: str = "explicit_review"
    support_layer_signal_refs: list[dict[str, Any]] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    variants: list[str] = field(default_factory=list)
    provenance_notes: str = ""
    notes: list[str] = field(default_factory=list)
    runtime_class: str = "local_pure_python"
    validation_level: str = "fixture_runnable"

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "rule_group_id": self.rule_id,
            "display_name": self.display_name,
            "rule_family": self.rule_family,
            "criterion_type": self.criterion_type,
            "applicable_disciplines": list(self.applicable_disciplines),
            "applicable_methods": list(self.applicable_methods),
            "applicable_data_roles": list(self.applicable_data_roles),
            "evidence_roles": list(self.evidence_roles),
            "evidence_binding": dict(self.evidence_binding),
            "checks": list(self.checks),
            "metric_family": self.metric_family,
            "unit_or_scale": self.unit_or_scale,
            "threshold_policy": dict(self.threshold_policy),
            "threshold_source": dict(self.threshold_source),
            "threshold_mode": self.threshold_mode or dict(self.threshold_policy).get("mode") or "contextual",
            "threshold_validation_status": self.threshold_validation_status,
            "minimum_sample_policy": self.minimum_sample_policy,
            "model_family": self.model_family,
            "blocking_level": self.blocking_level,
            "failure_route": self.failure_route,
            "pipeline_hooks": dict(self.pipeline_hooks),
            "maturity": self.maturity,
            "deployment_state": self.deployment_state,
            "human_confirmation_required": self.human_confirmation_required,
            "review_question": self.review_question,
            "scientific_risk": self.scientific_risk,
            "minimum_evidence_required": list(self.minimum_evidence_required),
            "sample_unit_policy": self.sample_unit_policy,
            "metric_dimension_policy": self.metric_dimension_policy,
            "allowed_claim_strength": self.allowed_claim_strength,
            "repair_priority": list(self.repair_priority),
            "manual_review_triggers": list(self.manual_review_triggers),
            "non_goals": list(self.non_goals),
            "template_path": self.template_path,
            "fixture_paths": list(self.fixture_paths),
            "positive_fixture_refs": list(self.positive_fixture_refs),
            "negative_fixture_refs": list(self.negative_fixture_refs),
            "source_skill_refs": list(self.source_skill_refs),
            "backflow_source_type": self.backflow_source_type,
            "support_layer_signal_refs": [dict(item) for item in self.support_layer_signal_refs],
            "aliases": list(self.aliases),
            "variants": list(self.variants),
            "provenance_notes": self.provenance_notes,
            "notes": list(self.notes),
            "runtime_class": self.runtime_class,
            "validation_level": self.validation_level,
        }


@dataclass(frozen=True)
class WorkflowRecipeSpec:
    """Support-layer recipe for workflow orchestration.

    Workflow recipes are not formal discipline-module subplugins. They can
    orchestrate data/method/review plugins and expose review-rule backflow
    candidates, but they must stay outside ``discipline_modules/<discipline>``.
    """

    recipe_id: str
    display_name: str
    applicable_disciplines: list[str] = field(default_factory=list)
    orchestrates: list[str] = field(default_factory=list)
    required_inputs: list[str] = field(default_factory=list)
    produced_artifacts: list[str] = field(default_factory=list)
    stale_triggers: list[str] = field(default_factory=list)
    checkpoint_policy: dict[str, Any] = field(default_factory=dict)
    failure_routes: list[str] = field(default_factory=list)
    review_rule_backflow_ids: list[str] = field(default_factory=list)
    source_skill_refs: list[str] = field(default_factory=list)
    provenance_notes: str = ""
    promotion_allowed: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "recipe_id": self.recipe_id,
            "display_name": self.display_name,
            "support_type": "workflow_recipe",
            "applicable_disciplines": list(self.applicable_disciplines),
            "orchestrates": list(self.orchestrates),
            "required_inputs": list(self.required_inputs),
            "produced_artifacts": list(self.produced_artifacts),
            "stale_triggers": list(self.stale_triggers),
            "checkpoint_policy": dict(self.checkpoint_policy),
            "failure_routes": list(self.failure_routes),
            "review_rule_backflow_ids": list(self.review_rule_backflow_ids),
            "source_skill_refs": list(self.source_skill_refs),
            "provenance_notes": self.provenance_notes,
            "promotion_allowed": self.promotion_allowed,
            "deployment_target": "draftpaper_cli/pipeline_recipes/",
        }


@dataclass(frozen=True)
class PaperContractSpec:
    """Support-layer paper contract for writing and citation gates.

    Paper contracts can guide post-writing checks, citation audit, figure-caption
    consistency, and submission constraints. They do not replace evidence-bound
    discipline data/method/review plugins.
    """

    contract_id: str
    display_name: str
    applicable_sections: list[str] = field(default_factory=list)
    required_evidence: list[str] = field(default_factory=list)
    forbidden_content: list[str] = field(default_factory=list)
    citation_policy: dict[str, Any] = field(default_factory=dict)
    figure_policy: dict[str, Any] = field(default_factory=dict)
    writing_post_checks: list[str] = field(default_factory=list)
    journal_scope: list[str] = field(default_factory=list)
    blocking_conditions: list[str] = field(default_factory=list)
    repair_routes: list[str] = field(default_factory=list)
    review_rule_backflow_ids: list[str] = field(default_factory=list)
    source_skill_refs: list[str] = field(default_factory=list)
    provenance_notes: str = ""
    promotion_allowed: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "display_name": self.display_name,
            "support_type": "paper_contract",
            "applicable_sections": list(self.applicable_sections),
            "required_evidence": list(self.required_evidence),
            "forbidden_content": list(self.forbidden_content),
            "citation_policy": dict(self.citation_policy),
            "figure_policy": dict(self.figure_policy),
            "writing_post_checks": list(self.writing_post_checks),
            "journal_scope": list(self.journal_scope),
            "blocking_conditions": list(self.blocking_conditions),
            "repair_routes": list(self.repair_routes),
            "review_rule_backflow_ids": list(self.review_rule_backflow_ids),
            "source_skill_refs": list(self.source_skill_refs),
            "provenance_notes": self.provenance_notes,
            "promotion_allowed": self.promotion_allowed,
            "deployment_target": "draftpaper_cli/paper_contracts/",
        }


@dataclass(frozen=True)
class DisciplineModuleSpec:
    """Declarative contract shared by data, method, figure, and review plugins."""

    module_id: str
    display_name: str
    keywords: list[str] = field(default_factory=list)
    data_roles: list[str] = field(default_factory=list)
    method_families: list[str] = field(default_factory=list)
    validation_checks: list[str] = field(default_factory=list)
    figure_families: list[str] = field(default_factory=list)
    minimum_main_figures: int = 5
    target_main_figures: int = 6
    required_figure_groups: list[str] = field(default_factory=list)
    formula_families: list[str] = field(default_factory=list)
    reviewer_risks: list[str] = field(default_factory=list)
    code_generation_constraints: list[str] = field(default_factory=list)
    data_connectors: list[dict[str, Any] | DataConnectorSpec] = field(default_factory=list)
    method_templates: list[dict[str, Any] | MethodTemplateSpec] = field(default_factory=list)
    review_rule_groups: list[dict[str, Any] | ReviewRuleSpec] = field(default_factory=list)
    maturity: str = "foundation"

    def connector_dicts(self) -> list[dict[str, Any]]:
        return [item.as_dict() if hasattr(item, "as_dict") else dict(item) for item in self.data_connectors]

    def method_template_dicts(self) -> list[dict[str, Any]]:
        return [item.as_dict() if hasattr(item, "as_dict") else dict(item) for item in self.method_templates]

    def review_rule_dicts(self) -> list[dict[str, Any]]:
        from ..scientific_plugin_runtime import apply_runnable_profile

        rules = []
        for item in self.review_rule_groups:
            rule = item.as_dict() if hasattr(item, "as_dict") else dict(item)
            rule = apply_runnable_profile(rule)
            rule_id = str(rule.get("rule_id") or rule.get("rule_group_id") or "")
            if rule_id:
                rule.setdefault("rule_id", rule_id)
                rule.setdefault("rule_group_id", rule_id)
            rule.setdefault("rule_family", "discipline_review")
            rule.setdefault("criterion_type", "scientific_quality_gate")
            rule.setdefault("blocking_level", "warn_and_repair")
            rule.setdefault("failure_route", "human_checkpoint")
            rule.setdefault("pipeline_hooks", {})
            rule.setdefault("threshold_policy", {"mode": "contextual"})
            rule.setdefault("threshold_source", {"type": "project_context", "citation_or_note": "legacy discipline rule"})
            rule.setdefault("threshold_mode", (rule.get("threshold_policy") or {}).get("mode") or "contextual")
            rule.setdefault("threshold_validation_status", "legacy_contextual")
            rule.setdefault("maturity", "foundation")
            rule.setdefault("deployment_state", "promoted_review_rule")
            rule.setdefault("human_confirmation_required", False)
            rule.setdefault("minimum_evidence_required", list(rule.get("evidence_roles") or []))
            rule.setdefault("evidence_binding", {
                "registry_record_types": [],
                "required_fields": list(rule.get("minimum_evidence_required") or rule.get("evidence_roles") or []),
                "forbidden_conflicts": [],
            })
            rule.setdefault("repair_priority", [rule.get("failure_route") or "human_checkpoint"])
            rule.setdefault("manual_review_triggers", [])
            rule.setdefault("non_goals", [])
            rule.setdefault("positive_fixture_refs", [path for path in rule.get("fixture_paths") or [] if "positive" in str(path).lower()])
            rule.setdefault("negative_fixture_refs", [path for path in rule.get("fixture_paths") or [] if "negative" in str(path).lower()])
            rule.setdefault("backflow_source_type", "explicit_review")
            rule.setdefault("support_layer_signal_refs", [])
            rule.setdefault("aliases", [])
            rule.setdefault("variants", [])
            rule.setdefault("runtime_class", "local_pure_python")
            rule.setdefault("validation_level", "fixture_runnable")
            rules.append(rule)
        return rules

    def as_dict(self) -> dict[str, Any]:
        return {
            "module_id": self.module_id,
            "display_name": self.display_name,
            "keywords": list(self.keywords),
            "data_roles": list(self.data_roles),
            "method_families": list(self.method_families),
            "validation_checks": list(self.validation_checks),
            "figure_families": list(self.figure_families),
            "minimum_main_figures": self.minimum_main_figures,
            "target_main_figures": self.target_main_figures,
            "required_figure_groups": list(self.required_figure_groups),
            "formula_families": list(self.formula_families),
            "reviewer_risks": list(self.reviewer_risks),
            "code_generation_constraints": list(self.code_generation_constraints),
            "data_connectors": self.connector_dicts(),
            "method_templates": self.method_template_dicts(),
            "review_rule_groups": self.review_rule_dicts(),
            "maturity": self.maturity,
        }


class DisciplineModule:
    """Base class for discipline-specific research workflow modules."""

    spec: DisciplineModuleSpec

    def method_blueprint_hints(self, context: dict[str, Any]) -> dict[str, Any]:
        return {
            "module": self.spec.as_dict(),
            "data_contract_hints": list(self.spec.data_roles),
            "method_code_hints": list(self.spec.method_families),
            "validation_hints": list(self.spec.validation_checks),
            "figure_hints": list(self.spec.figure_families),
            "figure_policy": {
                "minimum_main_figures": self.spec.minimum_main_figures,
                "target_main_figures": self.spec.target_main_figures,
                "required_figure_groups": list(self.spec.required_figure_groups),
            },
            "formula_hints": list(self.spec.formula_families),
            "reviewer_risk_hints": list(self.spec.reviewer_risks),
            "code_generation_constraints": list(self.spec.code_generation_constraints),
            "data_acquisition_hints": self.data_acquisition_hints(context),
            "method_template_hints": self.spec.method_template_dicts(),
            "review_rule_hints": self.spec.review_rule_dicts(),
        }

    def data_acquisition_hints(self, context: dict[str, Any]) -> list[dict[str, Any]]:
        hints = []
        for connector in self.spec.connector_dicts():
            packages = list(connector.get("packages") or [])
            package_modules = list(connector.get("package_modules") or packages)
            if len(package_modules) < len(packages):
                package_modules.extend(packages[len(package_modules):])
            missing_packages = [
                package for package, module in zip(packages, package_modules)
                if importlib.util.find_spec(str(module).split(">=")[0]) is None
            ]
            env_vars = list(connector.get("credential_env_vars") or [])
            missing_env = [name for name in env_vars if not os.environ.get(name)]
            if connector.get("requires_credentials") and missing_env:
                feasibility = "requires_credentials"
            elif missing_packages:
                feasibility = "requires_package_install"
            else:
                feasibility = "locally_feasible"
            item = dict(connector)
            item["feasibility_status"] = feasibility
            item["missing_packages"] = missing_packages
            item["missing_env_vars"] = missing_env
            item.setdefault("fetch_policy", "plan_first_user_confirmed_fetch")
            hints.append(item)
        return hints
