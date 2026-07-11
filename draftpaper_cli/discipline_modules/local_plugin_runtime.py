# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

"""Small, dependency-aware runtime shared by first-party foundation templates."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any


def dependency_report(packages: list[str], package_modules: list[str]) -> dict[str, Any]:
    modules = list(package_modules) or list(packages)
    available = []
    missing = []
    for package, module in zip(packages, modules):
        name = str(module).split(">=")[0].replace("-", "_")
        (available if importlib.util.find_spec(name) is not None else missing).append(str(package))
    return {"available_packages": available, "missing_packages": missing}


def build_local_plugin_plan(manifest: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    context = context or {}
    packages = [str(item) for item in manifest.get("packages") or []]
    report = dependency_report(packages, [str(item) for item in manifest.get("package_modules") or packages])
    mock_only = str((manifest.get("task_contract") or {}).get("execution_mode") or "") == "mock_only"
    return {
        "status": "mock_contract_ready" if mock_only else ("ready" if not report["missing_packages"] else "requires_package_install"),
        "plugin_id": manifest.get("template_id") or manifest.get("connector_id") or manifest.get("rule_id"),
        "discipline": manifest.get("discipline"),
        "runtime_class": manifest.get("runtime_class", "local_optional_dependency"),
        "validation_level": manifest.get("validation_level", "plan_only"),
        "input_roles": list(manifest.get("input_roles") or []),
        "output_artifacts": list(manifest.get("output_artifacts") or []),
        "validation_checks": list(manifest.get("validation_checks") or manifest.get("checks") or []),
        "dependency_report": report,
        "execution_mode": "mock_contract_only" if mock_only else "local_template",
        "live_execution_performed": False if mock_only else None,
        "task_contract": dict(manifest.get("task_contract") or {}),
        "context_keys": sorted(context),
        "boundary": "This foundation template is local and parameterized. It never stores credentials, remote addresses, or project-specific records.",
    }


def run_local_plugin_fixture(
    manifest: dict[str, Any],
    output_dir: str | Path,
    *,
    fixture_path: str | Path | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    plan = build_local_plugin_plan(manifest, context)
    if fixture_path:
        fixture = Path(fixture_path)
        plan["fixture_path"] = str(fixture)
        plan["fixture_exists"] = fixture.exists()
        if not fixture.exists():
            plan["status"] = "fixture_missing"
    result_path = output / "plugin_fixture_result.json"
    result_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"status": "written", "result": str(result_path), "plan": plan}


def evaluate_local_review_rule(manifest: dict[str, Any], evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    evidence = evidence or {}
    required = list(manifest.get("minimum_evidence_required") or manifest.get("evidence_roles") or [])
    present = {str(item) for item in evidence.get("roles") or evidence.get("evidence_roles") or []}
    missing = [role for role in required if role not in present]
    return {
        "rule_id": manifest.get("rule_id") or manifest.get("rule_group_id"),
        "decision": "review_required" if missing else "advisory_pass",
        "missing_evidence_roles": missing,
        "blocking": False,
        "reason": "Foundation review rules stay advisory until mature, evidence-bound thresholds are promoted.",
    }
