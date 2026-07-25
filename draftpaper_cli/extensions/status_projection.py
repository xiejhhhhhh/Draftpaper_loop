"""Read-only extension status projection for Core status and doctor commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .dispatcher import RECEIPT_LEDGER
from .events import EVENT_LEDGER
from .registry import discover_extensions


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            records.append(item)
    return records


def extension_status(project: str | Path) -> dict[str, Any]:
    root = Path(project).expanduser().resolve()
    discovered = discover_extensions()
    events = _jsonl(root / EVENT_LEDGER)
    receipts = _jsonl(root / RECEIPT_LEDGER)
    return {
        "schema_version": "dpl.extension_status.v1",
        "status": "available" if discovered else "no_extensions_installed",
        "extensions": [item.to_dict() for item in discovered],
        "event_count": len(events),
        "receipt_count": len(receipts),
        "latest_event": events[-1] if events else None,
        "latest_receipts": receipts[-10:],
    }
