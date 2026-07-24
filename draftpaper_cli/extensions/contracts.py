"""Version-neutral contracts shared by the public extension host."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


_VERSION = re.compile(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?")


def _version_tuple(value: str) -> tuple[int, int, int]:
    match = _VERSION.match(str(value).strip())
    if match is None:
        raise ValueError(f"invalid version: {value}")
    return tuple(int(item or 0) for item in match.groups())  # type: ignore[return-value]


def version_satisfies(version: str, expression: str) -> bool:
    """Evaluate the small comparator subset used by extension manifests."""

    current = _version_tuple(version)
    for raw in str(expression or "").split(","):
        clause = raw.strip()
        if not clause:
            continue
        operator = next((item for item in (">=", "<=", "==", ">", "<") if clause.startswith(item)), None)
        if operator is None:
            operator, target = "==", clause
        else:
            target = clause[len(operator) :].strip()
        expected = _version_tuple(target)
        passed = {
            ">=": current >= expected,
            "<=": current <= expected,
            "==": current == expected,
            ">": current > expected,
            "<": current < expected,
        }[operator]
        if not passed:
            return False
    return True


@dataclass(frozen=True)
class HostCapabilities:
    core_version: str
    abi_family: str
    abi_versions: tuple[str, ...]
    stage_taxonomy_version: str
    artifact_schema_families: dict[str, tuple[str, ...]]
    capabilities: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "dpl.extension_host_capabilities.v1",
            "core_version": self.core_version,
            "abi_family": self.abi_family,
            "abi_versions": list(self.abi_versions),
            "stage_taxonomy_version": self.stage_taxonomy_version,
            "artifact_schema_families": {
                key: list(value) for key, value in sorted(self.artifact_schema_families.items())
            },
            "capabilities": list(self.capabilities),
        }


@dataclass(frozen=True)
class ExtensionManifest:
    extension_id: str
    package_name: str
    package_version: str
    abi_family: str
    supported_abi: str
    required_capabilities: tuple[str, ...]
    optional_capabilities: tuple[str, ...]
    subscriptions: tuple[str, ...]
    read_globs: tuple[str, ...]
    write_scope: tuple[str, ...]
    event_handler: str | None
    legacy_core_range: str | None = None

    @classmethod
    def from_dict(cls, document: dict[str, Any]) -> "ExtensionManifest":
        schema = str(document.get("schema_version") or "")
        if schema not in {"dpl.extension.v1", "dpl.guidance_extension_manifest.v1"}:
            raise ValueError(f"unsupported extension manifest schema: {schema or 'missing'}")
        extension_id = str(document.get("extension_id") or "").strip()
        package_name = str(document.get("package_name") or "").strip()
        package_version = str(document.get("package_version") or "").strip()
        if not extension_id or not package_name or not package_version:
            raise ValueError("extension_id, package_name, and package_version are required")
        legacy = str(document.get("compatible_core") or "").strip() or None
        return cls(
            extension_id=extension_id,
            package_name=package_name,
            package_version=package_version,
            abi_family=str(document.get("abi_family") or "dpl.extension"),
            supported_abi=str(document.get("supported_abi") or ">=1.0,<2.0"),
            required_capabilities=tuple(str(item) for item in document.get("required_capabilities") or ()),
            optional_capabilities=tuple(str(item) for item in document.get("optional_capabilities") or ()),
            subscriptions=tuple(str(item) for item in document.get("subscriptions") or ()),
            read_globs=tuple(str(item) for item in document.get("read_globs") or ("**/*",)),
            write_scope=tuple(str(item) for item in document.get("write_scope") or ()),
            event_handler=(str(document.get("event_handler")).strip() if document.get("event_handler") else None),
            legacy_core_range=legacy,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "dpl.guidance_extension_manifest.v1",
            "extension_id": self.extension_id,
            "package_name": self.package_name,
            "package_version": self.package_version,
            "abi_family": self.abi_family,
            "supported_abi": self.supported_abi,
            "required_capabilities": list(self.required_capabilities),
            "optional_capabilities": list(self.optional_capabilities),
            "subscriptions": list(self.subscriptions),
            "read_globs": list(self.read_globs),
            "write_scope": list(self.write_scope),
            "event_handler": self.event_handler,
            "legacy_core_range": self.legacy_core_range,
        }


@dataclass(frozen=True)
class NegotiationResult:
    extension_id: str
    status: str
    selected_abi: str | None
    missing_required: tuple[str, ...]
    unavailable_optional: tuple[str, ...]
    reason: str | None = None

    @property
    def compatible(self) -> bool:
        return self.status in {"compatible", "compatible_with_degradation"}

    def to_dict(self) -> dict[str, Any]:
        return {
            "extension_id": self.extension_id,
            "status": self.status,
            "selected_abi": self.selected_abi,
            "missing_required": list(self.missing_required),
            "unavailable_optional": list(self.unavailable_optional),
            "reason": self.reason,
        }


def negotiate_extension(manifest: ExtensionManifest, host: HostCapabilities) -> NegotiationResult:
    if manifest.abi_family != host.abi_family:
        return NegotiationResult(
            manifest.extension_id,
            "incompatible",
            None,
            (),
            (),
            f"ABI family mismatch: {manifest.abi_family} != {host.abi_family}",
        )
    selected = next(
        (version for version in sorted(host.abi_versions, key=_version_tuple, reverse=True) if version_satisfies(version, manifest.supported_abi)),
        None,
    )
    if selected is None:
        return NegotiationResult(
            manifest.extension_id,
            "incompatible",
            None,
            (),
            (),
            f"no host ABI satisfies {manifest.supported_abi}",
        )
    if manifest.legacy_core_range and not version_satisfies(host.core_version, manifest.legacy_core_range):
        return NegotiationResult(
            manifest.extension_id,
            "incompatible",
            selected,
            (),
            (),
            f"legacy Core range not satisfied: {manifest.legacy_core_range}",
        )
    available = set(host.capabilities)
    missing = tuple(sorted(set(manifest.required_capabilities) - available))
    optional = tuple(sorted(set(manifest.optional_capabilities) - available))
    if missing:
        return NegotiationResult(manifest.extension_id, "incompatible", selected, missing, optional, "required capabilities are unavailable")
    status = "compatible_with_degradation" if optional else "compatible"
    return NegotiationResult(manifest.extension_id, status, selected, (), optional)
