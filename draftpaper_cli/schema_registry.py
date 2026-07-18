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


def validate_packaged_resource_schemas() -> dict[str, Any]:
    root = files("draftpaper_cli")
    checks: list[dict[str, str]] = []
    issues: list[str] = []

    release_root = root.joinpath("release_fixtures")
    release_files = sorted(
        (item for item in release_root.iterdir() if item.name.endswith(".json")),
        key=lambda item: item.name,
    )
    for item in release_files:
        payload = json.loads(item.read_text(encoding="utf-8"))
        schema_id = str(payload.get("schema_version") or "") if isinstance(payload, dict) else ""
        family = schema_family(schema_id) if schema_id else None
        checks.append({"resource": f"release_fixtures/{item.name}", "schema_id": schema_id, "family": str(family or "")})
        if family != "release_fixture":
            issues.append(f"release_fixtures/{item.name}:unregistered_or_wrong_schema:{schema_id or 'missing'}")

    capability_root = root.joinpath("capability_packs")
    capability_files = sorted(
        (
            (directory.name, directory.joinpath("manifest.json"))
            for directory in capability_root.iterdir()
            if directory.is_dir()
        ),
        key=lambda item: item[0],
    )
    capability_files = [(pack_id, item) for pack_id, item in capability_files if item.is_file()]
    for pack_id, item in capability_files:
        payload = json.loads(item.read_text(encoding="utf-8"))
        schema_id = str(payload.get("schema_version") or "") if isinstance(payload, dict) else ""
        family = schema_family(schema_id) if schema_id else None
        checks.append({"resource": f"capability_packs/{pack_id}/manifest.json", "schema_id": schema_id, "family": str(family or "")})
        if family != "research_capability_pack":
            issues.append(f"capability_packs/{pack_id}/manifest.json:unregistered_or_wrong_schema:{schema_id or 'missing'}")

    return {
        "schema_version": "dpl.packaged_resource_schema_report.v1",
        "status": "passed" if not issues else "failed",
        "release_fixture_count": len(release_files),
        "capability_pack_count": len(capability_files),
        "checks": checks,
        "issues": issues,
    }
