# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

from pathlib import Path
from typing import Any

from .io_utils import read_json


PLUGIN_KINDS = {
    "data_connectors": "connector",
    "method_templates": "method",
    "review_rules": "review",
}


def _module_root() -> Path:
    return Path(__file__).resolve().parent / "discipline_modules"


def discover_template_registry(root: Path | None = None) -> dict[str, Any]:
    base = root or _module_root()
    entries: list[dict[str, Any]] = []
    for manifest_path in sorted(base.glob("*/*/*/manifest.json")):
        plugin_dir = manifest_path.parent
        kind_dir = plugin_dir.parent.name
        discipline = plugin_dir.parent.parent.name
        manifest = read_json(manifest_path, {})
        if not isinstance(manifest, dict):
            manifest = {}
        fixtures = sorted(
            path.name
            for path in plugin_dir.iterdir()
            if path.is_file() and path.name.startswith("fixture_")
        )
        entries.append({
            "discipline": discipline,
            "kind": PLUGIN_KINDS.get(kind_dir, kind_dir),
            "kind_dir": kind_dir,
            "plugin_id": manifest.get("connector_id")
            or manifest.get("template_id")
            or manifest.get("rule_group_id")
            or plugin_dir.name,
            "path": str(plugin_dir.relative_to(base)),
            "manifest": str(manifest_path.relative_to(base)),
            "has_template": (plugin_dir / "template.py").exists(),
            "fixtures": fixtures,
            "maturity": manifest.get("maturity") or manifest.get("status") or "foundation",
        })
    return {
        "status": "written",
        "root": str(base),
        "entry_count": len(entries),
        "entries": entries,
    }


def validate_template_registry(root: Path | None = None) -> dict[str, Any]:
    registry = discover_template_registry(root)
    issues: list[dict[str, str]] = []
    for entry in registry["entries"]:
        if entry["kind"] in {"connector", "method"} and not entry["has_template"]:
            issues.append({
                "severity": "error",
                "code": "template_missing",
                "plugin_id": str(entry["plugin_id"]),
                "path": str(entry["path"]),
            })
        if not entry["plugin_id"]:
            issues.append({
                "severity": "error",
                "code": "plugin_id_missing",
                "plugin_id": "",
                "path": str(entry["path"]),
            })
    blocking = [issue for issue in issues if issue["severity"] == "error"]
    return {
        "status": "passed" if not blocking else "failed",
        "entry_count": registry["entry_count"],
        "issue_count": len(issues),
        "issues": issues,
        "registry": registry,
    }
