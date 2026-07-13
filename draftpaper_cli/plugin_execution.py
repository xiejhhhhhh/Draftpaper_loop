# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

"""Bind formal plugin manifests to stage-owned execution events.

Only first-party template contracts under the local discipline-module root are
loaded. The ledger distinguishes fixture execution from an actual project run so
planning output is never misrepresented as scientific evidence.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

from .project_scaffold import utc_now
from .project_state import load_project
from .plugin_catalog import build_plugin_catalog_snapshot, normalize_execution_contract, validate_execution_contract


BINDING_PLAN = "research_plan/plugin_binding_plan.json"


class PluginExecutionError(RuntimeError):
    """Raised when a selected plugin cannot be resolved safely."""


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _plugin_root() -> Path:
    return Path(__file__).resolve().parent / "discipline_modules"


def _kind_directory(kind: str) -> str:
    return {"data": "data_connectors", "method": "method_templates"}.get(kind, "")


def _resolve_plugin(binding: dict[str, Any]) -> tuple[Path, dict[str, Any], Path]:
    kind = str(binding.get("kind") or "")
    plugin_id = str(binding.get("plugin_id") or "")
    if kind not in {"data", "method"} or not plugin_id:
        raise PluginExecutionError("Plugin binding must identify a data or method plugin.")
    for manifest_path in _plugin_root().glob(f"*/{_kind_directory(kind)}/{plugin_id}/manifest.json"):
        manifest = _read_json(manifest_path)
        template = manifest_path.parent / str(manifest.get("template") or "template.py")
        if template.exists():
            return manifest_path, manifest, template
    raise PluginExecutionError(f"No local template manifest exists for selected plugin: {kind}:{plugin_id}")


def _append_jsonl(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def _load_template(path: Path):
    spec = importlib.util.spec_from_file_location(f"draftpaper_plugin_{path.parent.name}", path)
    if not spec or not spec.loader:
        raise PluginExecutionError(f"Cannot load plugin template: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _execute_bindings(project: str | Path, *, kind: str) -> dict[str, Any]:
    state = load_project(project)
    plan = _read_json(state.path / BINDING_PLAN)
    current_catalog = build_plugin_catalog_snapshot(refresh=True)
    planned_catalog_hash = plan.get("plugin_catalog_hash")
    if planned_catalog_hash and planned_catalog_hash != current_catalog.get("catalog_hash"):
        raise PluginExecutionError("Plugin catalog changed after capability planning; rerun assess-plugin-sufficiency before execution.")
    bindings = [item for item in plan.get("bindings") or [] if isinstance(item, dict) and item.get("kind") == kind]
    stage_dir = state.path / ("data" if kind == "data" else "methods")
    ledger_path = stage_dir / "plugin_execution_ledger.jsonl"
    events = []
    for binding in bindings:
        event = {
            "event_id": hashlib.sha256(f"{utc_now()}:{binding.get('requirement_id')}".encode("utf-8")).hexdigest()[:16],
            "generated_at": utc_now(),
            "stage": "data" if kind == "data" else "methods",
            "requirement_id": binding.get("requirement_id"),
            "figure_id": binding.get("figure_id"),
            "plugin_id": binding.get("plugin_id"),
            "manifest_path": None,
            "template_path": None,
            "manifest_sha256": None,
            "template_sha256": None,
            "runtime_class": binding.get("runtime_class"),
            "validation_level": binding.get("validation_level"),
            "input_hashes": {},
            "parameters": {"execution_scope": "fixture_or_contract_validation"},
            "output_hashes": {},
            "scientific_evidence_status": "not_established",
            "catalog_hash": current_catalog.get("catalog_hash"),
            "plugin_contract_hash": binding.get("plugin_contract_hash"),
        }
        if binding.get("binding_scope") == "project_local":
            event.update({
                "status": "project_local_asset_registered",
                "reason": "This binding is traceable project-local evidence. It is executed by the project method runner, not by a copied global plugin template.",
                "evidence": dict(binding.get("evidence") or {}),
            })
            _append_jsonl(ledger_path, event)
            events.append(event)
            continue
        try:
            manifest_path, manifest, template_path = _resolve_plugin(binding)
            execution_contract = normalize_execution_contract(manifest, kind=kind)
            contract_errors = validate_execution_contract(execution_contract)
            if contract_errors:
                raise PluginExecutionError("Invalid plugin execution contract: " + "; ".join(contract_errors))
            runtime = str(manifest.get("runtime_class") or binding.get("runtime_class") or "local_optional_dependency")
            validation = str(manifest.get("validation_level") or binding.get("validation_level") or "plan_only")
            event.update({
                "manifest_path": str(manifest_path),
                "template_path": str(template_path),
                "manifest_sha256": _sha256(manifest_path),
                "template_sha256": _sha256(template_path),
                "runtime_class": runtime,
                "validation_level": validation,
                "execution_contract": execution_contract,
            })
            output_dir = stage_dir / "plugin_runs" / str(binding["plugin_id"])
            if execution_contract.get("execution_mode") == "mock_only" or runtime not in {"local_pure_python", "local_optional_dependency"} or validation not in {"fixture_runnable", "live_validated"}:
                event.update({"status": "prepared_for_project_execution", "reason": "The selected template has no standard runnable fixture contract."})
            else:
                module = _load_template(template_path)
                runner = getattr(module, "run_template", None)
                fixture = manifest_path.parent / str(manifest.get("fixture") or "fixture_minimal.json")
                if not callable(runner) or not fixture.exists():
                    event.update({"status": "prepared_for_project_execution", "reason": "The selected template has no standard runnable fixture contract."})
                else:
                    output_dir.mkdir(parents=True, exist_ok=True)
                    result = runner(output_dir, fixture_path=fixture, context={"project_path": str(state.path), "requirement_id": binding.get("requirement_id")})
                    result_path = Path(str(result.get("result") or ""))
                    event.update({
                        "status": "fixture_executed",
                        "result": result,
                        "output_hashes": {str(result_path.relative_to(state.path)): _sha256(result_path)} if result_path.exists() and state.path in result_path.parents else {},
                        "scientific_evidence_status": "fixture_only_not_project_result",
                    })
        except Exception as exc:
            event.update({"status": "execution_failed", "reason": str(exc)})
        _append_jsonl(ledger_path, event)
        events.append(event)
    status = "failed" if any(item.get("status") == "execution_failed" for item in events) else "written"
    return {"status": status, "project_path": str(state.path), "stage": "data" if kind == "data" else "methods", "binding_count": len(bindings), "ledger": str(ledger_path), "events": events}


def execute_data_plugins(project: str | Path) -> dict[str, Any]:
    """Execute or prepare selected data connector fixture contracts under ``data/``."""
    return _execute_bindings(project, kind="data")


def execute_method_plugins(project: str | Path) -> dict[str, Any]:
    """Execute or prepare selected method-template fixture contracts under ``methods/``."""
    return _execute_bindings(project, kind="method")


def record_project_method_run(project: str | Path, *, output_files: list[str]) -> list[dict[str, Any]]:
    """Record real verified method outputs against selected method plugins.

    This is distinct from fixture execution. It records a current project run
    only after ``verify-methods`` succeeds, so a template plan cannot be
    mistaken for scientific evidence.
    """
    state = load_project(project)
    plan = _read_json(state.path / BINDING_PLAN)
    current_catalog = build_plugin_catalog_snapshot(refresh=True)
    bindings = [
        item for item in plan.get("bindings") or []
        if isinstance(item, dict) and item.get("kind") == "method" and item.get("state") in {"covered", "covered_project_local"}
    ]
    hashes = {
        relative: _sha256(state.path / relative)
        for relative in output_files
        if (state.path / relative).exists()
    }
    ledger_path = state.path / "methods" / "plugin_execution_ledger.jsonl"
    events = []
    for binding in bindings:
        event = {
            "event_id": hashlib.sha256(f"{utc_now()}:{binding.get('requirement_id')}:project_run".encode("utf-8")).hexdigest()[:16],
            "generated_at": utc_now(),
            "stage": "methods",
            "requirement_id": binding.get("requirement_id"),
            "figure_id": binding.get("figure_id"),
            "plugin_id": binding.get("plugin_id"),
            "status": "project_executed",
            "scientific_evidence_status": "project_result",
            "runtime_class": binding.get("runtime_class"),
            "validation_level": binding.get("validation_level"),
            "parameters": {"verification_output_count": len(hashes)},
            "input_hashes": {},
            "output_hashes": hashes,
            "catalog_hash": current_catalog.get("catalog_hash"),
            "plugin_contract_hash": binding.get("plugin_contract_hash"),
        }
        _append_jsonl(ledger_path, event)
        events.append(event)
    return events
