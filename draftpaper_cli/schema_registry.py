"""Independent schema-family registry and compatibility checks."""

from __future__ import annotations

import json
import re
from importlib.resources import files
from typing import Any


PRODUCT_VERSION_SCHEMA = re.compile(r"^v\d+\.\d+(?:\.\d+)?$")


def load_schema_registry() -> dict[str, Any]:
    resource = files("draftpaper_cli").joinpath("resources/schemas/schema_registry.json")
    payload = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("families"), dict):
        raise ValueError("Packaged schema registry is invalid.")
    return payload


def schema_family(schema_id: str) -> str | None:
    registry = load_schema_registry()
    for family, contract in registry["families"].items():
        if schema_id == contract.get("current") or schema_id in contract.get("accepted") or []:
            return family
    return None


def validate_schema_compatibility(schema_id: str, expected_family: str) -> dict[str, Any]:
    registry = load_schema_registry()
    contract = (registry.get("families") or {}).get(expected_family)
    if not isinstance(contract, dict):
        return {"status": "failed", "reason": "unknown_expected_family", "expected_family": expected_family}
    accepted = {str(contract.get("current")), *[str(item) for item in contract.get("accepted") or []]}
    if schema_id in accepted:
        return {"status": "passed", "schema_id": schema_id, "expected_family": expected_family}
    return {
        "status": "failed",
        "reason": "product_version_used_as_schema" if PRODUCT_VERSION_SCHEMA.match(schema_id) else "incompatible_schema",
        "schema_id": schema_id,
        "expected_family": expected_family,
        "accepted": sorted(accepted),
        "adapter": (contract.get("adapters") or {}).get(schema_id),
    }

def schema_registry_report() -> dict[str, Any]:
    registry = load_schema_registry()
    issues = []
    current_ids: list[str] = []
    for family, contract in registry["families"].items():
        current = str(contract.get("current") or "")
        if not current.startswith("dpl."):
            issues.append(f"{family}:current_schema_not_namespaced")
        current_ids.append(current)
    if len(current_ids) != len(set(current_ids)):
        issues.append("duplicate_current_schema_id")
    return {
        "schema_version": "dpl.schema_registry_report.v1",
        "status": "passed" if not issues else "failed",
        "family_count": len(registry["families"]),
        "issues": issues,
        "registry_version": registry.get("schema_version"),
    }
