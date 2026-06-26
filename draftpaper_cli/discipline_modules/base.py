# Copyright (c) 2026 xiejhhhhhh
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
    review_rule_groups: list[dict[str, Any]] = field(default_factory=list)
    maturity: str = "foundation"

    def connector_dicts(self) -> list[dict[str, Any]]:
        return [item.as_dict() if hasattr(item, "as_dict") else dict(item) for item in self.data_connectors]

    def method_template_dicts(self) -> list[dict[str, Any]]:
        return [item.as_dict() if hasattr(item, "as_dict") else dict(item) for item in self.method_templates]

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
            "review_rule_groups": list(self.review_rule_groups),
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
            "review_rule_hints": list(self.spec.review_rule_groups),
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
