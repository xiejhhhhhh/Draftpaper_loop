"""Non-blocking dispatch of committed Core events to compatible extensions."""

from __future__ import annotations

import fnmatch
import hashlib
import importlib
from pathlib import Path
from typing import Any, Iterable

from ..passport import utc_now
from ..state_kernel import append_jsonl_locked
from .events import WorkflowEvent
from .host_capabilities import build_host_capabilities
from .registry import DiscoveredExtension, discover_extensions
from .scoped_artifact_reader import ScopedArtifactReader


RECEIPT_LEDGER = ".draftpaper/extensions/extension_receipts.jsonl"


def _handler(path: str) -> Any:
    module_name, separator, attribute = path.partition(":")
    if not separator or not module_name or not attribute:
        raise ValueError("event_handler must use module:function syntax")
    candidate = getattr(importlib.import_module(module_name), attribute)
    if not callable(candidate):
        raise TypeError("event_handler is not callable")
    return candidate


def _state(root: Path) -> dict[str, tuple[int, int]]:
    result = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative.startswith((".git/", ".draftpaper/extensions/")):
            continue
        stat = path.stat()
        result[relative] = (stat.st_size, stat.st_mtime_ns)
    return result


def _write_scope_violations(before: dict[str, tuple[int, int]], after: dict[str, tuple[int, int]], allowed: tuple[str, ...]) -> tuple[str, ...]:
    changed = {path for path in set(before) | set(after) if before.get(path) != after.get(path)}
    return tuple(sorted(path for path in changed if not any(fnmatch.fnmatchcase(path, pattern) for pattern in allowed)))


def dispatch_workflow_event(
    project: str | Path,
    event: WorkflowEvent,
    *,
    extensions: Iterable[DiscoveredExtension] | None = None,
) -> tuple[dict[str, Any], ...]:
    root = Path(project).expanduser().resolve()
    records = tuple(extensions) if extensions is not None else discover_extensions()
    host = build_host_capabilities()
    receipts: list[dict[str, Any]] = []
    for record in records:
        manifest = record.manifest
        negotiation = record.negotiation
        if manifest is None or negotiation is None or not negotiation.compatible:
            continue
        if manifest.subscriptions and event.event_type not in manifest.subscriptions:
            continue
        if not manifest.event_handler:
            continue
        reader = ScopedArtifactReader(root, allowed_globs=manifest.read_globs)
        before = _state(root)
        receipt: dict[str, Any] = {
            "schema_version": "dpl.extension_receipt.v1",
            "recorded_at": utc_now(),
            "event_id": event.event_id,
            "extension_id": manifest.extension_id,
            "extension_version": manifest.package_version,
            "selected_abi": negotiation.selected_abi,
            "capability_token_sha256": reader.token_sha256,
            "status": "completed",
            "error": None,
            "write_scope_violations": [],
        }
        try:
            response = _handler(manifest.event_handler)(
                event=event.to_dict(),
                artifact_reader=reader,
                capability_token=reader.capability_token,
                host_capabilities=host.to_dict(),
                extension_manifest=manifest.to_dict(),
            )
            receipt["response_sha256"] = hashlib.sha256(repr(response).encode("utf-8")).hexdigest()
        except Exception as exc:
            receipt["status"] = "failed_nonblocking"
            receipt["error"] = f"{type(exc).__name__}: {exc}"
        violations = _write_scope_violations(before, _state(root), manifest.write_scope)
        if violations:
            receipt["status"] = "write_scope_violation"
            receipt["write_scope_violations"] = list(violations)
        append_jsonl_locked(root / RECEIPT_LEDGER, receipt)
        receipts.append(receipt)
    return tuple(receipts)
