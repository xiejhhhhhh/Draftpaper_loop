"""Independent expected-vs-checked coverage for scientific project artifacts.

The passport is an observation cache.  This module deliberately derives the
expected set from project declarations and manuscript reachability before it
looks at the checker output, so a checker cannot make an incomplete scan look
complete by returning only the files it happened to read.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from .artifact_identity import canonical_json, compute_artifact_identity
from .change_impact import artifact_role_for_path
from .passport import (
    CODE_MANIFEST_ARTIFACTS,
    DIRECT_DISCOVERY_MAX_BYTES,
    ROOT_ARTIFACTS,
    _code_manifest_artifacts,
    _direct_workspace_artifacts,
    _metadata,
    _read_json,
    _stage_manifest_outputs,
    project_root,
)


SCOPE_SCHEMA = "dpl.artifact_scope.v1"
_REACHABLE_RE = re.compile(r"\\(input|include|includegraphics)\s*(?:\[[^]]*\])?\s*\{([^}]+)\}")
_GRAPHICSPATH_RE = re.compile(r"\\graphicspath\s*\{((?:\{[^{}]*\}\s*)+)\}")


def _normalize(value: Any) -> str:
    normalized = str(value or "").replace("\\", "/").strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _inside(root: Path, relative: str) -> Path | None:
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        return None
    return path


def _expected_paths(root: Path) -> tuple[list[str], list[dict[str, Any]]]:
    metadata = _metadata(root)
    candidates = [*ROOT_ARTIFACTS]
    candidates.extend(_stage_manifest_outputs(root, metadata))
    candidates.extend(CODE_MANIFEST_ARTIFACTS)
    candidates.extend(_code_manifest_artifacts(root))
    declared = {_normalize(item) for item in candidates if _normalize(item)}
    candidates.extend(_direct_workspace_artifacts(root, declared=declared, include_large=True))

    # Scientific evidence records make their source files expected even when a
    # project migrated from a sparse stage manifest.
    registry = _read_json(root / "writing/scientific_evidence_registry.json", {})
    records = registry.get("records") if isinstance(registry, dict) else []
    for record in records or []:
        if isinstance(record, dict) and record.get("source_artifact"):
            candidates.append(str(record["source_artifact"]))

    queue = [_normalize(item) for item in candidates if _normalize(item)]
    seen: set[str] = set()
    expected: list[str] = []
    reasons: dict[str, set[str]] = {}
    for relative in queue:
        if relative in seen:
            continue
        seen.add(relative)
        expected.append(relative)
        reasons.setdefault(relative, set()).add("project_declaration")

    # Follow static TeX reachability.  Unsupported/dynamic includes are kept as
    # explicit unknowns rather than silently treated as absent dependencies.
    graphic_bases = [root / "latex", root]
    for relative in list(expected):
        path = _inside(root, relative)
        if path is None or path.suffix.lower() != ".tex" or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            continue
        for raw_group in _GRAPHICSPATH_RE.findall(text):
            for raw_base in re.findall(r"\{([^{}]*)\}", raw_group):
                candidate = (root / "latex" / raw_base).resolve()
                try:
                    candidate.relative_to(root.resolve())
                except ValueError:
                    continue
                if candidate not in graphic_bases:
                    graphic_bases.append(candidate)
    index = 0
    dynamic: list[dict[str, Any]] = []
    while index < len(expected):
        relative = expected[index]
        index += 1
        path = _inside(root, relative)
        if path is None or path.suffix.lower() != ".tex" or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            continue
        for command, raw in _REACHABLE_RE.findall(text):
            token = raw.strip()
            if (
                any(marker in token for marker in ("\\", "$", "#", " "))
                or Path(token).is_absolute()
                or "://" in token
            ):
                dynamic.append({"from": relative, "locator": token, "reason": "dynamic_include_not_resolved"})
                continue
            if command in {"input", "include"}:
                variants = [token] if Path(token).suffix else [token + ".tex"]
                bases = [root / "latex"]
            else:
                variants = [token] if Path(token).suffix else [
                    token + suffix for suffix in (".pdf", ".png", ".jpg", ".jpeg", ".svg")
                ]
                bases = graphic_bases
            candidates_for_token = [
                (base / variant).resolve()
                for base in bases
                for variant in variants
            ]
            existing_candidates = [candidate for candidate in candidates_for_token if candidate.is_file()]
            chosen_candidates = existing_candidates or candidates_for_token[:1]
            for candidate in chosen_candidates:
                try:
                    child = candidate.relative_to(root.resolve()).as_posix()
                except ValueError:
                    dynamic.append({"from": relative, "locator": token, "reason": "include_escapes_project_root"})
                    continue
                if child not in seen:
                    seen.add(child)
                    expected.append(child)
                    reasons.setdefault(child, set()).add(f"reachable_from:{relative}")

    rows = [
        {"path": path, "role": artifact_role_for_path(path)[0], "required_reasons": sorted(reasons.get(path) or [])}
        for path in sorted(expected)
    ]
    rows.extend(
        {"path": None, "role": "unknown", "required_reasons": [item["reason"]], "source": item["from"], "locator": item["locator"]}
        for item in dynamic
    )
    return [row["path"] for row in rows if row.get("path")], rows


def collect_artifact_scope(project: str | Path, candidate_id: str | None = None) -> dict[str, Any]:
    """Return expected, checked, missing, and excluded objects without mutation."""
    root = project_root(project)
    expected_paths, expected_rows = _expected_paths(root)
    checked: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    expected_by_path = {str(row["path"]): row for row in expected_rows if row.get("path")}
    for relative in expected_paths:
        path = _inside(root, relative)
        context = expected_by_path.get(relative) or {"path": relative, "role": artifact_role_for_path(relative)[0], "required_reasons": []}
        if path is None:
            missing.append({**context, "status": "missing", "reason": "path_escapes_project_root"})
            continue
        if not path.is_file():
            missing.append({**context, "status": "missing", "reason": "file_not_found"})
            continue
        try:
            size = path.stat().st_size
        except OSError as exc:
            missing.append({**context, "status": "error", "reason": f"stat_failed:{exc}"})
            continue
        if size > DIRECT_DISCOVERY_MAX_BYTES:
            excluded.append({
                **context,
                "status": "not_evaluated",
                "reason": "large_file_requires_declared_release_verification",
                "size_bytes": size,
            })
            continue
        try:
            identity = compute_artifact_identity(path, relative)
        except (OSError, UnicodeError, ValueError) as exc:
            missing.append({**context, "status": "error", "reason": f"identity_failed:{exc}"})
            continue
        checked.append({
            **context,
            "status": "checked",
            "size_bytes": size,
            "byte_sha256": identity.get("byte_sha256"),
            "semantic_sha256": identity.get("semantic_sha256"),
            "evidence_sha256": identity.get("evidence_sha256"),
        })
    for row in expected_rows:
        if row.get("path") is None:
            missing.append({**row, "status": "not_evaluated"})
    scope_payload = {
        "schema_version": SCOPE_SCHEMA,
        "candidate_id": candidate_id,
        "expected": expected_rows,
        "checked": checked,
        "missing": missing,
        "excluded": excluded,
    }
    digest = hashlib.sha256(canonical_json(scope_payload).encode("utf-8")).hexdigest()
    required_missing = [
        *[row for row in missing if row.get("status") in {"missing", "error", "not_evaluated"}],
        *excluded,
    ]
    return {
        **scope_payload,
        "scope_digest": digest,
        "expected_count": len(expected_rows),
        "checked_count": len(checked),
        "missing_count": len(required_missing),
        "excluded_count": len(excluded),
        "status": "passed" if not required_missing else "coverage_incomplete",
        "release_eligible": not required_missing,
        "project_path": str(root),
    }


__all__ = ["SCOPE_SCHEMA", "collect_artifact_scope"]
