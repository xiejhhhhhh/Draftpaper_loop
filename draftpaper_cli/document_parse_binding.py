"""Bind parser receipts and evidence passages back to reference work identity."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .project_scaffold import _write_json
from .document_identity import reference_work_id


def bind_document_parse(project: str | Path, *, receipt: dict[str, Any], normalized: dict[str, Any], passages: list[dict[str, Any]]) -> dict[str, Any]:
    root = Path(project)
    references_path = root / "references" / "literature_items.json"
    try:
        items = json.loads(references_path.read_text(encoding="utf-8")) if references_path.is_file() else []
    except (OSError, json.JSONDecodeError):
        items = []
    if isinstance(items, dict):
        items = items.get("items", [])
    items = items if isinstance(items, list) else []
    work_id = str(normalized.get("work_id") or receipt.get("work_id") or "")
    bound = False
    for item in items:
        item_work_id = str(item.get("work_id") or item.get("canonical_work_id") or reference_work_id(item))
        if item_work_id and item_work_id == work_id:
            parses = list(item.get("document_parses") or [])
            marker = str(receipt.get("input_sha256") or "")
            if not any(str(value.get("input_sha256") or "") == marker for value in parses if isinstance(value, dict)):
                parses.append(receipt)
            item["document_parses"] = parses
            item["evidence_passages"] = passages
            item["candidate_state"] = "evidence_ready" if passages else item.get("candidate_state") or "document_parsed"
            item["work_id"] = work_id
            bound = True
            break
    if bound:
        _write_json(references_path, items)
    else:
        queue_path = root / "references" / "unresolved_document_bindings.json"
        try:
            queue = json.loads(queue_path.read_text(encoding="utf-8")) if queue_path.is_file() else {"schema_version": "dpl.unresolved_document_bindings.v1", "items": []}
        except (OSError, json.JSONDecodeError):
            queue = {"schema_version": "dpl.unresolved_document_bindings.v1", "items": []}
        queue.setdefault("items", [])
        marker = str(receipt.get("input_sha256") or normalized.get("document_id") or "")
        queue["items"] = [
            value
            for value in queue["items"]
            if not isinstance(value, dict)
            or str((value.get("receipt") or {}).get("input_sha256") or "") != marker
        ]
        queue["items"].append({"receipt": receipt, "normalized_document": normalized, "evidence_passages": passages})
        _write_json(queue_path, queue)
    normalized_path = root / "references" / "document_parses" / str(receipt.get("input_sha256") or "unknown")[:16] / "normalized_document.json"
    normalized_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(normalized_path, normalized)
    passage_path = normalized_path.with_name("evidence_passages.jsonl")
    passage_path.write_text("\n".join(json.dumps(item, ensure_ascii=False, sort_keys=True) for item in passages) + ("\n" if passages else ""), encoding="utf-8")
    return {"status": "bound" if bound else "unresolved", "work_id": work_id, "normalized_output": normalized_path.relative_to(root).as_posix(), "passage_count": len(passages)}
