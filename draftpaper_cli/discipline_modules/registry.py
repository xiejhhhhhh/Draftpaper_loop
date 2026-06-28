# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

from .astronomy import MODULE as ASTRONOMY
from .bioinformatics import MODULE as BIOINFORMATICS
from .base import DisciplineModule
from .base import DisciplineModuleSpec
from .default import MODULE as DEFAULT
from .ecology import MODULE as ECOLOGY
from .engineering import MODULE as ENGINEERING
from .finance import MODULE as FINANCE
from .geography import MODULE as GEOGRAPHY
from .machine_learning import MODULE as MACHINE_LEARNING
from .medicine import MODULE as MEDICINE
from .biology import MODULE as BIOLOGY


MODULES: dict[str, DisciplineModule] = {
    "default": DEFAULT,
    "geography": GEOGRAPHY,
    "astronomy": ASTRONOMY,
    "machine_learning": MACHINE_LEARNING,
    "ecology": ECOLOGY,
    "bioinformatics": BIOINFORMATICS,
    "finance": FINANCE,
    "medicine": MEDICINE,
    "biology": BIOLOGY,
    "engineering": ENGINEERING,
}


class CompositeDisciplineModule(DisciplineModule):
    """Runtime module assembled from default, primary, and secondary disciplines."""

    def __init__(self, modules: list[DisciplineModule], *, primary: str, secondary: list[str]) -> None:
        ordered = _unique_modules(modules)
        visible = [module.spec.module_id for module in ordered if module.spec.module_id != "default"]
        self.spec = DisciplineModuleSpec(
            module_id=f"composite:{'+'.join(visible) if visible else 'default'}",
            display_name="Composite discipline workflow",
            keywords=_merge_lists(module.spec.keywords for module in ordered),
            data_roles=_merge_lists(module.spec.data_roles for module in ordered),
            method_families=_merge_lists(module.spec.method_families for module in ordered),
            validation_checks=_merge_lists(module.spec.validation_checks for module in ordered),
            figure_families=_merge_lists(module.spec.figure_families for module in ordered),
            minimum_main_figures=max((module.spec.minimum_main_figures for module in ordered), default=5),
            target_main_figures=max((module.spec.target_main_figures for module in ordered), default=6),
            required_figure_groups=_merge_lists(module.spec.required_figure_groups for module in ordered),
            formula_families=_merge_lists(module.spec.formula_families for module in ordered),
            reviewer_risks=_merge_lists(module.spec.reviewer_risks for module in ordered),
            code_generation_constraints=_merge_lists(module.spec.code_generation_constraints for module in ordered),
            data_connectors=_merge_dicts_by_id((module.spec.connector_dicts() for module in ordered), "connector_id"),
            method_templates=_merge_dicts_by_id((module.spec.method_template_dicts() for module in ordered), "template_id"),
            review_rule_groups=_merge_dicts_by_id((module.spec.review_rule_groups for module in ordered), "rule_group_id"),
        )
        self.primary_discipline = primary
        self.secondary_disciplines = list(secondary)
        self.source_module_ids = [module.spec.module_id for module in ordered]

    def method_blueprint_hints(self, context: dict[str, object]) -> dict[str, object]:
        hints = super().method_blueprint_hints(context)
        hints["composite_discipline"] = {
            "primary_discipline": self.primary_discipline,
            "secondary_disciplines": list(self.secondary_disciplines),
            "source_module_ids": list(self.source_module_ids),
        }
        return hints


def _merge_lists(groups: object) -> list[str]:
    merged: list[str] = []
    for group in groups:
        for item in group:
            value = str(item)
            if value not in merged:
                merged.append(value)
    return merged


def _merge_dicts_by_id(groups: object, key: str) -> list[dict[str, object]]:
    merged: list[dict[str, object]] = []
    seen: set[str] = set()
    for group in groups:
        for item in group:
            value = str(item.get(key) or "")
            if not value or value in seen:
                continue
            seen.add(value)
            merged.append(dict(item))
    return merged


def _unique_modules(modules: list[DisciplineModule]) -> list[DisciplineModule]:
    result: list[DisciplineModule] = []
    seen: set[str] = set()
    for module in modules:
        module_id = module.spec.module_id
        if module_id in seen:
            continue
        seen.add(module_id)
        result.append(module)
    return result


def _module_order_from_profile(profile: dict[str, object]) -> list[str]:
    declared = [str(item) for item in profile.get("discipline_modules") or []]
    if declared:
        return declared
    primary = str(profile.get("primary_discipline") or profile.get("discipline") or profile.get("engine") or "default")
    secondary = [str(item) for item in profile.get("secondary_disciplines") or []]
    modules = ["default"]
    if primary != "default":
        modules.append(primary)
    for item in secondary:
        if item not in modules:
            modules.append(item)
    return modules


def get_discipline_module(profile_or_name: str | dict[str, object] | None) -> DisciplineModule:
    if isinstance(profile_or_name, dict):
        module_ids = [item for item in _module_order_from_profile(profile_or_name) if item in MODULES]
        visible = [item for item in module_ids if item != "default"]
        if len(visible) > 1:
            primary = str(profile_or_name.get("primary_discipline") or profile_or_name.get("discipline") or visible[0])
            secondary = [item for item in visible if item != primary]
            return CompositeDisciplineModule([MODULES[item] for item in module_ids], primary=primary, secondary=secondary)
        name = visible[0] if visible else str(profile_or_name.get("discipline") or profile_or_name.get("engine") or "default")
    else:
        name = str(profile_or_name or "default")
    return MODULES.get(name, DEFAULT)


def list_discipline_modules() -> list[dict[str, object]]:
    return [module.spec.as_dict() for module in MODULES.values()]
