# Copyright (c) 2026 xiejhhhhhh
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

from .astronomy import MODULE as ASTRONOMY
from .bioinformatics import MODULE as BIOINFORMATICS
from .base import DisciplineModule
from .default import MODULE as DEFAULT
from .ecology import MODULE as ECOLOGY
from .geography import MODULE as GEOGRAPHY
from .machine_learning import MODULE as MACHINE_LEARNING


MODULES: dict[str, DisciplineModule] = {
    "default": DEFAULT,
    "geography": GEOGRAPHY,
    "astronomy": ASTRONOMY,
    "machine_learning": MACHINE_LEARNING,
    "ecology": ECOLOGY,
    "bioinformatics": BIOINFORMATICS,
}


def get_discipline_module(profile_or_name: str | dict[str, object] | None) -> DisciplineModule:
    if isinstance(profile_or_name, dict):
        name = str(profile_or_name.get("discipline") or profile_or_name.get("engine") or "default")
    else:
        name = str(profile_or_name or "default")
    return MODULES.get(name, DEFAULT)


def list_discipline_modules() -> list[dict[str, object]]:
    return [module.spec.as_dict() for module in MODULES.values()]
