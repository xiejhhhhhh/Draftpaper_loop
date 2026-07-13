"""Truthful plugin runtime-level derivation from source and execution evidence."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .scientific_plugin_runtime import runnable_profile


RUNTIME_LEVELS = {"contract_only", "code_generator", "fixture_executed", "project_validated", "live_validated"}


def inspect_static_runtime_level(plugin_dir: Path, kind: str, manifest: dict[str, Any]) -> str:
    plugin_id = str(manifest.get("template_id") or manifest.get("connector_id") or manifest.get("rule_id") or manifest.get("rule_group_id") or plugin_dir.name)
    if runnable_profile(plugin_id):
        return "fixture_executed" if kind == "review" else "code_generator"
    template = plugin_dir / "template.py"
    if not template.is_file() or kind == "review":
        return "contract_only"
    source = template.read_text(encoding="utf-8-sig", errors="replace")
    if str((manifest.get("task_contract") or {}).get("execution_mode") or "") == "mock_only" or "run_local_plugin_fixture" in source:
        return "contract_only"
    callable_markers = ("def run_", "def execute_", "def compute_", "def convert_", "def stream_", "def load_")
    output_markers = (".write_text(", ".write_bytes(", "csv.writer(", "csv.DictWriter(", "to_csv(", "savefig(")
    return "code_generator" if any(marker in source for marker in callable_markers) and any(marker in source for marker in output_markers) else "contract_only"


def resolve_effective_runtime_level(static_level: str, events: list[dict[str, Any]]) -> tuple[str, str]:
    if any(item.get("status") == "live_validated" and item.get("output_hashes") for item in events):
        return "live_validated", "live_execution_evidence"
    if any(item.get("status") == "project_executed" and item.get("output_hashes") for item in events):
        return "project_validated", "verified_project_output"
    if any(item.get("status") == "fixture_executed" for item in events):
        return "fixture_executed", "fixture_execution_only"
    return (static_level if static_level in RUNTIME_LEVELS else "contract_only"), "static_source_inspection"
