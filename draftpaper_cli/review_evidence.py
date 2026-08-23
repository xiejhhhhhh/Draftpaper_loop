"""Read individual, project-owned review evidence without loading an audit bundle."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .artifact_identity import sha256_file
from .passport import project_root


MAX_PREVIEW_BYTES = 12 * 1024
_SENSITIVE_NAMES = frozenset({".env", "credentials.json", "credentials.yaml", "secrets.json"})
_PREFIXES = ("artifact:", "file:", "path:")


def _json_pointer(value: Any, pointer: str) -> Any:
    current = value
    for raw_token in pointer.lstrip("/").split("/"):
        if raw_token == "":
            continue
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            if token not in current:
                raise KeyError(token)
            current = current[token]
        elif isinstance(current, list):
            index = int(token)
            current = current[index]
        else:
            raise KeyError(token)
    return current


def _resolve(root: Path, reference: str) -> tuple[Path, str, str | None]:
    raw = str(reference or "").strip()
    for prefix in _PREFIXES:
        if raw.startswith(prefix):
            raw = raw[len(prefix) :]
            break
    relative, marker, selector = raw.partition("#")
    candidate = Path(relative.replace("\\", "/"))
    if not relative or candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("Evidence reference must be a project-relative file path.")
    path = (root / candidate).resolve()
    try:
        safe_relative = path.relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError("Evidence reference resolves outside the project root.") from exc
    if path.name.lower() in _SENSITIVE_NAMES or any(part.lower() == ".git" for part in Path(safe_relative).parts):
        raise ValueError("Evidence reference targets a protected file.")
    return path, safe_relative, selector if marker else None


def inspect_review_evidence(project: str | Path, *, ref: str) -> dict[str, Any]:
    """Return a bounded evidence preview for an explicit evidence reference.

    This is intentionally not a general filesystem reader.  It only resolves
    project-relative evidence paths and limits the returned preview so default
    Agent review remains decision-brief first.
    """

    root = project_root(project)
    try:
        path, relative, selector = _resolve(root, ref)
    except ValueError as exc:
        return {"status": "blocked", "project_path": str(root), "ref": ref, "reason": str(exc)}
    if not path.is_file():
        return {"status": "not_found", "project_path": str(root), "ref": ref, "project_relative_path": relative}
    size_bytes = path.stat().st_size
    result: dict[str, Any] = {
        "status": "passed",
        "project_path": str(root),
        "ref": ref,
        "project_relative_path": relative,
        "absolute_path": str(path),
        "sha256": sha256_file(path),
        "size_bytes": size_bytes,
        "preview_limit_bytes": MAX_PREVIEW_BYTES,
    }
    if path.suffix.lower() == ".json":
        if size_bytes > MAX_PREVIEW_BYTES and selector is None:
            try:
                payload = json.loads(path.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError) as exc:
                return {**result, "status": "invalid", "reason": str(exc)}
            result.update(
                {
                    "preview_mode": "json_top_level_only",
                    "top_level_keys": sorted(payload)[:100] if isinstance(payload, dict) else [],
                    "truncated": True,
                }
            )
            return result
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
            selected = _json_pointer(payload, selector) if selector else payload
        except (OSError, ValueError, KeyError, IndexError) as exc:
            return {**result, "status": "invalid", "reason": f"JSON evidence could not be resolved: {exc}"}
        encoded = json.dumps(selected, ensure_ascii=False, indent=2)
        if len(encoded.encode("utf-8")) > MAX_PREVIEW_BYTES:
            result.update(
                {
                    "preview_mode": "json_selected_value_metadata",
                    "selector": selector,
                    "value_type": type(selected).__name__,
                    "truncated": True,
                }
            )
            if isinstance(selected, dict):
                result["top_level_keys"] = sorted(selected)[:100]
            elif isinstance(selected, list):
                result["item_count"] = len(selected)
            return result
        result.update({"preview_mode": "json", "selector": selector, "content": selected, "truncated": False})
        return result
    raw = path.read_bytes()[:MAX_PREVIEW_BYTES]
    text = raw.decode("utf-8", errors="replace")
    result.update(
        {
            "preview_mode": "text",
            "content": text,
            "truncated": size_bytes > len(raw),
        }
    )
    return result


__all__ = ["MAX_PREVIEW_BYTES", "inspect_review_evidence"]
