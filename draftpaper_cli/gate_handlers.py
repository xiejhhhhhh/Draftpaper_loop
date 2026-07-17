"""Command-registry adapters for gates with legacy result payloads."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import core_evidence, data_feasibility, methods, result_validity
from . import integrity_gate


def assess_core_evidence_gate(project: str | Path) -> dict[str, Any]:
    return core_evidence.assess_core_evidence(project=project)


def assess_data_quality_gate(
    project: str | Path,
    required_columns: list[str] | None = None,
    max_missing_ratio: float = 0.2,
) -> dict[str, Any]:
    result = data_feasibility.assess_data_quality(project=project, required_columns=required_columns, max_missing_ratio=max_missing_ratio)
    result["decision"] = "pass" if result.get("overall_status") == "pass" else "revise_required"
    return result


def assess_result_validity_gate(
    project: str | Path,
    primary_metric: str | None = None,
    minimum_value: float | None = None,
) -> dict[str, Any]:
    result = result_validity.assess_result_validity(project=project, primary_metric=primary_metric, minimum_value=minimum_value)
    result.setdefault("decision", "pass" if result.get("status") in {"pass", "passed"} else "revise_required")
    return result


def verify_methods_gate(
    project: str | Path,
    command: str | None = None,
    output_files: list[str] | None = None,
    input_data: list[str] | None = None,
    allow_system_binary: bool = False,
) -> dict[str, Any]:
    result = methods.verify_methods(
        project=project,
        command=command,
        output_files=output_files,
        input_data=input_data,
        allow_system_binary=allow_system_binary,
    )
    result["decision"] = "pass" if result.get("status") == "success" else "revise_required"
    return result


def run_integrity_gate(project: str | Path) -> dict[str, Any]:
    result = integrity_gate.run_integrity_gate(project=project)
    if "decision" not in result:
        result["decision"] = "pass" if result.get("status") in {"passed", "pass", "success"} else "revise_required"
    return result
