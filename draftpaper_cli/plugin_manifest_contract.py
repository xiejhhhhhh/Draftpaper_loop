"""Versioned, explicit contracts for discipline plugin manifests."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any

from .state_kernel import atomic_write_json


PLUGIN_MANIFEST_SCHEMA_VERSION = "dpl.plugin_manifest.v2"
PLUGIN_KINDS = {"data_connectors": "data", "method_templates": "method", "review_rules": "review"}
REQUIRED_FIELDS = {
    "schema_version",
    "plugin_id",
    "plugin_kind",
    "discipline",
    "runtime_class",
    "validation_level",
    "maturity",
    "deployment_state",
    "fixtures",
    "execution_contract",
}


def plugin_kind(plugin_dir: Path) -> str:
    return PLUGIN_KINDS.get(plugin_dir.parent.name, "review")


def plugin_identifier(manifest: dict[str, Any], plugin_dir: Path) -> str:
    return str(
        manifest.get("plugin_id")
        or manifest.get("connector_id")
        or manifest.get("template_id")
        or manifest.get("rule_id")
        or manifest.get("rule_group_id")
        or plugin_dir.name
    )


def fixture_inventory(plugin_dir: Path) -> dict[str, list[str]]:
    result = {"normal": [], "failure": [], "boundary": [], "mock": []}
    for path in sorted(plugin_dir.iterdir()):
        if not path.is_file() or not path.name.startswith("fixture"):
            continue
        lowered = path.name.lower()
        category = (
            "failure" if "failure" in lowered
            else "boundary" if "boundary" in lowered
            else "mock" if "mock" in lowered
            else "normal"
        )
        result[category].append(path.name)
    return result


def fixture_files(plugin_dir: Path, manifest: dict[str, Any] | None = None) -> list[str]:
    declared = (manifest or {}).get("fixtures")
    if isinstance(declared, dict):
        names = [str(name) for values in declared.values() if isinstance(values, list) for name in values]
        return list(dict.fromkeys(names))
    return [name for values in fixture_inventory(plugin_dir).values() for name in values]


def _execution_contract(manifest: dict[str, Any], kind: str) -> dict[str, Any]:
    runtime = str(manifest.get("runtime_class") or "local_optional_dependency")
    validation = str(manifest.get("validation_level") or "plan_only")
    raw_task = manifest.get("task_contract")
    task: dict[str, Any] = raw_task if isinstance(raw_task, dict) else {}
    if "gpu" in runtime:
        resource = "local_gpu" if "local" in runtime else "remote_server"
    elif "server" in runtime:
        resource = "remote_server"
    elif "api" in runtime:
        resource = "network_api"
    else:
        resource = "local_cpu"
    mock_only = validation in {"plan_only", "mock_validated"} or task.get("execution_mode") == "mock_only"
    side_effect = "none" if kind == "review" else "network" if resource in {"network_api", "remote_server"} else "project_write"
    return {
        "schema_version": "dpl.plugin_execution_contract.v2",
        "execution_mode": "mock_only" if mock_only else "sync",
        "resource_class": resource,
        "timeout_seconds": int(task.get("timeout_seconds") or 300),
        "max_attempts": int(task.get("max_attempts") or 1),
        "idempotency": str(task.get("idempotency") or "supported"),
        "side_effect_level": str(task.get("side_effect_level") or side_effect),
        "approval_policy": str(task.get("approval_policy") or "none"),
        "parallel_safe": bool(task.get("parallel_safe", False)),
        "credential_env_vars": sorted(str(item) for item in task.get("credential_env_vars") or []),
        "input_schema": task.get("input_schema") or {"type": "object", "additionalProperties": True},
        "output_schema": task.get("output_schema") or {"type": "object", "additionalProperties": True},
    }


def migrate_manifest_payload(manifest: dict[str, Any], plugin_dir: Path) -> dict[str, Any]:
    migrated = dict(manifest)
    kind = plugin_kind(plugin_dir)
    migrated["schema_version"] = PLUGIN_MANIFEST_SCHEMA_VERSION
    migrated["plugin_id"] = plugin_identifier(migrated, plugin_dir)
    migrated["plugin_kind"] = kind
    migrated.setdefault("discipline", plugin_dir.parent.parent.name)
    migrated.setdefault("runtime_class", "local_optional_dependency")
    migrated.setdefault("validation_level", "plan_only")
    migrated.setdefault("maturity", "foundation")
    migrated.setdefault("deployment_state", "review_rule_candidate" if kind == "review" else "foundation")
    migrated["fixtures"] = fixture_inventory(plugin_dir)
    migrated.setdefault("execution_contract", _execution_contract(migrated, kind))
    return migrated


def manifest_issues(manifest: dict[str, Any], plugin_dir: Path) -> list[str]:
    issues = [f"missing_explicit_field:{field}" for field in sorted(REQUIRED_FIELDS) if field not in manifest]
    if manifest.get("schema_version") != PLUGIN_MANIFEST_SCHEMA_VERSION:
        issues.append("unsupported_schema_version")
    if manifest.get("plugin_kind") != plugin_kind(plugin_dir):
        issues.append("plugin_kind_path_mismatch")
    if manifest.get("plugin_id") != plugin_identifier(manifest, plugin_dir):
        issues.append("plugin_id_mismatch")
    declared = fixture_files(plugin_dir, manifest)
    missing = [name for name in declared if not (plugin_dir / name).is_file()]
    if missing:
        issues.append("declared_fixture_missing:" + ",".join(sorted(missing)))
    if manifest.get("validation_level") == "fixture_runnable" and not declared:
        issues.append("fixture_runnable_without_fixture")
    if not isinstance(manifest.get("execution_contract"), dict):
        issues.append("execution_contract_not_object")
    return issues


def review_fixture_issues(manifest: dict[str, Any], plugin_dir: Path) -> list[str]:
    """Execute declared review fixtures without promoting their deployment level."""
    if plugin_kind(plugin_dir) != "review" or manifest.get("validation_level") != "fixture_runnable":
        return []
    template = plugin_dir / "template.py"
    if not template.is_file():
        return ["review_fixture_template_missing"]
    spec = importlib.util.spec_from_file_location(f"dpl_fixture_{plugin_dir.parent.parent.name}_{plugin_dir.name}", template)
    if not spec or not spec.loader:
        return ["review_fixture_template_load_failed"]
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        return [f"review_fixture_template_import_failed:{type(exc).__name__}"]
    evaluator = getattr(module, "evaluate_rule", None)
    if not callable(evaluator):
        return ["review_fixture_evaluator_missing"]
    issues: list[str] = []
    for name in fixture_files(plugin_dir, manifest):
        path = plugin_dir / name
        if path.suffix.lower() != ".json":
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
            result = evaluator(payload)
        except Exception as exc:
            issues.append(f"review_fixture_execution_failed:{name}:{type(exc).__name__}")
            continue
        if not isinstance(result, dict):
            issues.append(f"review_fixture_result_not_object:{name}")
    return issues


def migrate_plugin_manifests(root: str | Path, *, write: bool = False) -> dict[str, Any]:
    base = Path(root).resolve()
    changed: list[str] = []
    reports: list[dict[str, Any]] = []
    for path in sorted(base.glob("*/*/*/manifest.json")):
        manifest = json.loads(path.read_text(encoding="utf-8-sig"))
        migrated = migrate_manifest_payload(manifest, path.parent)
        relative = path.relative_to(base).as_posix()
        if migrated != manifest:
            changed.append(relative)
            if write:
                atomic_write_json(path, migrated)
        reports.append({"manifest": relative, "issues": manifest_issues(migrated, path.parent)})
    issues = [f"{row['manifest']}:{issue}" for row in reports for issue in row["issues"]]
    return {
        "schema_version": "dpl.plugin_manifest_migration.v1",
        "status": "passed" if not issues else "failed",
        "manifest_count": len(reports),
        "changed_count": len(changed),
        "changed": changed,
        "issues": issues,
        "written": write,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = migrate_plugin_manifests(args.root, write=args.write)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
