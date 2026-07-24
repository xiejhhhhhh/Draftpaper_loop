"""Entry-point discovery with data-only manifest loading and isolation."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import EntryPoint, entry_points
from typing import Any, Iterable

from .contracts import ExtensionManifest, NegotiationResult, negotiate_extension
from .host_capabilities import build_host_capabilities


ENTRY_POINT_GROUP = "draftpaper.extensions.v1"


@dataclass(frozen=True)
class DiscoveredExtension:
    entry_point_name: str
    manifest: ExtensionManifest | None
    negotiation: NegotiationResult | None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_point_name": self.entry_point_name,
            "manifest": self.manifest.to_dict() if self.manifest else None,
            "negotiation": self.negotiation.to_dict() if self.negotiation else None,
            "error": self.error,
        }


def _installed_entry_points() -> Iterable[EntryPoint]:
    discovered = entry_points()
    if hasattr(discovered, "select"):
        return discovered.select(group=ENTRY_POINT_GROUP)
    return discovered.get(ENTRY_POINT_GROUP, ())  # type: ignore[attr-defined,no-any-return]


def discover_extensions(*, candidates: Iterable[Any] | None = None) -> tuple[DiscoveredExtension, ...]:
    host = build_host_capabilities()
    records: list[DiscoveredExtension] = []
    for candidate in candidates if candidates is not None else _installed_entry_points():
        name = str(getattr(candidate, "name", "extension"))
        try:
            factory = candidate.load() if hasattr(candidate, "load") else candidate
            document = factory() if callable(factory) else factory
            if not isinstance(document, dict):
                raise TypeError("extension entry point must return a manifest object")
            manifest = ExtensionManifest.from_dict(document)
            records.append(DiscoveredExtension(name, manifest, negotiate_extension(manifest, host)))
        except Exception as exc:
            records.append(DiscoveredExtension(name, None, None, f"{type(exc).__name__}: {exc}"))
    return tuple(records)
