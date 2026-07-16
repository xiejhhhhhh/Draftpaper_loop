"""Deterministic plugin execution contracts and immutable catalog snapshots."""

from __future__ import annotations

import hashlib
import json
import copy
from pathlib import Path
from typing import Any

from .scientific_plugin_runtime import apply_runnable_profile, runnable_profile
from .plugin_runtime import inspect_static_runtime_level


EXECUTION_MODES = {"sync", "job", "mock_only"}
RESOURCE_CLASSES = {"local_cpu", "local_gpu", "network_api", "remote_server", "laboratory"}
IDEMPOTENCY = {"required", "supported", "none"}
SIDE_EFFECT_LEVELS = {"none", "project_write", "network", "remote_write", "irreversible"}
APPROVAL_POLICIES = {"none", "project_confirmation", "human_only"}
_DEFAULT_CATALOG_CACHE: dict[str, Any] | None = None


def plugin_root() -> Path:
    return Path(__file__).resolve().parent / "discipline_modules"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    value = path.read_bytes()
    if path.suffix.lower() in {".json", ".py", ".md", ".yaml", ".yml", ".csv"}:
        value = value.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return _sha256_bytes(value)


def _kind_from_path(path: Path) -> str:
    parts = set(path.parts)
    if "data_connectors" in parts:
        return "data"
    if "method_templates" in parts:
        return "method"
    return "review"


def normalize_execution_contract(manifest: dict[str, Any], *, kind: str) -> dict[str, Any]:
    """Adapt legacy manifests without claiming a higher runtime level."""
    declared = dict(manifest.get("execution_contract") or {})
    task = dict(manifest.get("task_contract") or {})
    runtime = str(manifest.get("runtime_class") or "")
    validation = str(manifest.get("validation_level") or "")
    remote = runtime in {"network_api", "remote_server", "external_api", "gpu_remote"}
    mock_only = str(task.get("execution_mode") or "") == "mock_only" or validation in {"plan_only", "mock_validated"}
    resource = declared.get("resource_class")
    if not resource:
        if "gpu" in runtime:
            resource = "local_gpu" if "local" in runtime else "remote_server"
        elif "server" in runtime:
            resource = "remote_server"
        elif "api" in runtime or remote:
            resource = "network_api"
        else:
            resource = "local_cpu"
    execution_mode = declared.get("execution_mode") or task.get("execution_mode") or ("mock_only" if mock_only else "sync")
    side_effect = declared.get("side_effect_level") or task.get("side_effect_level")
    if not side_effect:
        side_effect = "network" if resource in {"network_api", "remote_server"} else ("none" if kind == "review" else "project_write")
    approval = declared.get("approval_policy") or task.get("approval_policy")
    if not approval:
        approval = "human_only" if resource in {"laboratory"} or side_effect in {"remote_write", "irreversible"} else "none"
    contract = {
        "schema_version": "dpl.plugin_execution_contract.v2",
        "execution_mode": str(execution_mode),
        "resource_class": str(resource),
        "timeout_seconds": int(declared.get("timeout_seconds") or task.get("timeout_seconds") or 300),
        "max_attempts": int(declared.get("max_attempts") or task.get("max_attempts") or 1),
        "idempotency": str(declared.get("idempotency") or task.get("idempotency") or "supported"),
        "side_effect_level": str(side_effect),
        "approval_policy": str(approval),
        "parallel_safe": bool(declared.get("parallel_safe", task.get("parallel_safe", False))),
        "credential_env_vars": sorted(str(item) for item in declared.get("credential_env_vars") or task.get("credential_env_vars") or []),
        "input_schema": declared.get("input_schema") or task.get("input_schema") or {"type": "object", "additionalProperties": True},
        "output_schema": declared.get("output_schema") or task.get("output_schema") or {"type": "object", "additionalProperties": True},
        "compatibility_adapter": not bool(manifest.get("execution_contract")),
    }
    return contract


def validate_execution_contract(contract: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    checks = (
        ("execution_mode", EXECUTION_MODES),
        ("resource_class", RESOURCE_CLASSES),
        ("idempotency", IDEMPOTENCY),
        ("side_effect_level", SIDE_EFFECT_LEVELS),
        ("approval_policy", APPROVAL_POLICIES),
    )
    for key, allowed in checks:
        if contract.get(key) not in allowed:
            errors.append(f"{key} must be one of {sorted(allowed)}")
    if int(contract.get("timeout_seconds") or 0) <= 0:
        errors.append("timeout_seconds must be positive")
    if int(contract.get("max_attempts") or 0) <= 0:
        errors.append("max_attempts must be positive")
    for key in ("input_schema", "output_schema"):
        if not isinstance(contract.get(key), dict):
            errors.append(f"{key} must be an object")
    return errors


def build_plugin_catalog_snapshot(*, root: str | Path | None = None, refresh: bool = False) -> dict[str, Any]:
    global _DEFAULT_CATALOG_CACHE
    if root is None and _DEFAULT_CATALOG_CACHE is not None and not refresh:
        return copy.deepcopy(_DEFAULT_CATALOG_CACHE)
    base = Path(root).resolve() if root else plugin_root().resolve()
    entries: list[dict[str, Any]] = []
    for manifest_path in sorted(base.glob("*/**/manifest.json")):
        manifest = _read_json(manifest_path)
        manifest = apply_runnable_profile(manifest)
        kind = _kind_from_path(manifest_path)
        plugin_id = str(
            manifest.get("plugin_id")
            or manifest.get("connector_id")
            or manifest.get("template_id")
            or manifest.get("rule_id")
            or manifest.get("rule_group_id")
            or manifest_path.parent.name
        )
        contract = normalize_execution_contract(manifest, kind=kind)
        template = manifest_path.parent / str(manifest.get("template") or "template.py")
        material = {
            "discipline": manifest_path.relative_to(base).parts[0],
            "kind": kind,
            "plugin_id": plugin_id,
            "manifest_sha256": _sha256_file(manifest_path),
            "template_sha256": _sha256_file(template) if template.is_file() else None,
            "execution_contract": contract,
            "maturity": manifest.get("maturity") or "foundation",
            "runtime_level": inspect_static_runtime_level(manifest_path.parent, kind, manifest),
            "runnable_profile": runnable_profile(plugin_id),
        }
        material["plugin_contract_hash"] = _sha256_bytes(json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        material["contract_errors"] = validate_execution_contract(contract)
        entries.append(material)
    catalog_material = json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    errors = [f"{entry['plugin_id']}: {error}" for entry in entries for error in entry["contract_errors"]]
    payload = {
        "schema_version": "dpl.plugin_catalog_snapshot.v1",
        "status": "passed" if not errors else "failed",
        "plugin_count": len(entries),
        "catalog_hash": _sha256_bytes(catalog_material),
        "entries": entries,
        "errors": errors,
    }
    if root is None:
        _DEFAULT_CATALOG_CACHE = copy.deepcopy(payload)
    return payload


def write_plugin_catalog_snapshot(project: str | Path) -> dict[str, Any]:
    from .project_state import load_project

    state = load_project(project)
    payload = build_plugin_catalog_snapshot()
    relative = Path("research_plan") / "plugin_catalog_snapshot.json"
    path = state.path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {**payload, "path": relative.as_posix()}


def validate_plugin_contract_diff(project: str | Path) -> dict[str, Any]:
    from .project_state import load_project

    state = load_project(project)
    path = state.path / "research_plan" / "plugin_catalog_snapshot.json"
    baseline = _read_json(path)
    current = build_plugin_catalog_snapshot(refresh=True)
    if not baseline:
        return {
            "schema_version": "dpl.plugin_contract_diff.v1",
            "status": "missing_snapshot",
            "current_catalog_hash": current["catalog_hash"],
            "next_command": f'draftpaper snapshot-plugin-catalog --project "{state.path}"',
        }
    baseline_by_id = {f"{item.get('discipline')}:{item.get('kind')}:{item.get('plugin_id')}": item for item in baseline.get("entries") or []}
    current_by_id = {f"{item.get('discipline')}:{item.get('kind')}:{item.get('plugin_id')}": item for item in current.get("entries") or []}
    changed = sorted(key for key in set(baseline_by_id) & set(current_by_id) if baseline_by_id[key].get("plugin_contract_hash") != current_by_id[key].get("plugin_contract_hash"))
    return {
        "schema_version": "dpl.plugin_contract_diff.v1",
        "status": "passed" if baseline.get("catalog_hash") == current.get("catalog_hash") else "drift_detected",
        "baseline_catalog_hash": baseline.get("catalog_hash"),
        "current_catalog_hash": current.get("catalog_hash"),
        "added": sorted(set(current_by_id) - set(baseline_by_id)),
        "removed": sorted(set(baseline_by_id) - set(current_by_id)),
        "changed": changed,
    }


def catalog_hash() -> str:
    return str(build_plugin_catalog_snapshot()["catalog_hash"])
