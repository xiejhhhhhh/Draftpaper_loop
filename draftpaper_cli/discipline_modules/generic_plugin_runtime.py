"""Small shared wrapper for first-party, fixture-runnable plugin contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .local_plugin_runtime import evaluate_local_review_rule, run_local_plugin_fixture


def run_contract(manifest: dict[str, Any], output_dir: str | Path, *, fixture_path: str | Path | None = None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    return run_local_plugin_fixture(manifest, output_dir, fixture_path=fixture_path, context=context)


def evaluate_contract(manifest: dict[str, Any], evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    return evaluate_local_review_rule(manifest, evidence)

