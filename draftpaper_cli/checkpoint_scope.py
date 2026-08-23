"""Bounded, manifest-first artifact selection for checkpoint packages."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from .artifact_identity import canonical_json


CHECKPOINT_SCOPE_SCHEMA = "dpl.checkpoint_scope.v1"

_PATH_KEY_TOKENS = ("path", "file", "report", "manifest", "artifact", "output", "html", "json", "packet", "figure", "table", "script", "code")
_EXCLUDED_PREFIXES = (
    ".draftpaper/",
    "review/checkpoints/",
    "review/independent_review/",
    "lineage/",
    "results/evidence_snapshots/",
    "results/archive/",
    "results/historical/",
    "results/cache/",
)
_STAGE_ROOTS = {
    "research_plan": ("research_plan", "journal_profile", "plugins"),
    "research_plan_feasibility": ("research_plan", "data", "methods"),
    "data": ("data",),
    "method_plan": ("methods", "research_plan"),
    "methods": ("methods", "code", "results"),
    "result_support": ("results", "methods", "data"),
    "core_evidence": ("core_evidence", "results"),
    "plugin": ("plugins", "research_plan"),
    "quality_checks": ("quality_checks", "quality", "integrity", "citation_audit", "latex"),
    "writing": ("writing", "latex"),
    "results": ("results",),
    "introduction": ("introduction", "writing", "references"),
    "data_writing": ("data_writing", "data", "latex"),
    "methods_writing": ("methods_writing", "methods", "latex"),
    "discussion": ("discussion", "writing", "results", "references"),
    "latex": ("latex", "writing", "references"),
    "citation_audit": ("citation_audit", "references", "latex"),
}
_PRIMARY_DISCOVERY_ROOTS = {
    "research_plan": ("research_plan",),
    "research_plan_feasibility": ("research_plan",),
    "data": ("data",),
    "method_plan": ("methods",),
    "methods": ("methods",),
    "result_support": ("results",),
    "core_evidence": ("core_evidence", "results/figures", "results/tables"),
    "plugin": ("plugins",),
    "quality_checks": ("quality_checks",),
    "writing": ("writing",),
    "results": ("results",),
    "introduction": ("introduction",),
    "data_writing": ("data_writing",),
    "methods_writing": ("methods_writing",),
    "discussion": ("discussion",),
    "latex": ("latex",),
    "citation_audit": ("citation_audit",),
}
_DEFAULT_SUFFIXES = frozenset({".csv", ".html", ".ipynb", ".jl", ".json", ".md", ".pdf", ".png", ".jpg", ".jpeg", ".py", ".r", ".sh", ".tex", ".tsv", ".yaml", ".yml"})


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _safe_relative(root: Path, value: Any) -> str | None:
    text = str(value or "").strip().strip('"')
    if not text or "://" in text:
        return None
    candidate = Path(text)
    try:
        resolved = (candidate if candidate.is_absolute() else root / candidate).resolve()
        relative = resolved.relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        return None
    if not relative or relative == "." or any(relative.startswith(prefix) for prefix in _EXCLUDED_PREFIXES):
        return None
    return relative if (root / relative).is_file() else None


def _paths_from_value(root: Path, value: Any, *, key: str = "") -> set[str]:
    paths: set[str] = set()
    if isinstance(value, dict):
        for child_key, child in value.items():
            paths.update(_paths_from_value(root, child, key=str(child_key)))
    elif isinstance(value, list):
        for child in value:
            paths.update(_paths_from_value(root, child, key=key))
    elif isinstance(value, str) and any(token in key.lower() for token in _PATH_KEY_TOKENS):
        relative = _safe_relative(root, value)
        if relative:
            paths.add(relative)
    return paths


def _manifest_candidates(stage: str) -> tuple[str, ...]:
    roots = _STAGE_ROOTS.get(stage, (stage,))
    candidates = [f"{root}/stage_manifest.json" for root in roots]
    candidates.extend(f"{root}/output_manifest.json" for root in roots)
    candidates.extend(f"{root}/artifact_manifest.json" for root in roots)
    return tuple(dict.fromkeys(candidates))


def _manifest_paths(root: Path, stage: str) -> set[str]:
    paths: set[str] = set()
    for relative in _manifest_candidates(stage):
        path = root / relative
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        paths.add(relative)
        paths.update(_paths_from_value(root, payload))
    return paths


def _direct_stage_paths(root: Path, stage: str) -> set[str]:
    """Discover only current stage-owned material, never broad review history."""

    paths: set[str] = set()
    directories = _PRIMARY_DISCOVERY_ROOTS.get(stage, (stage,))
    # Core evidence is the critical case: only its dedicated directory plus
    # current rendered figures/tables are discoverable.  Its JSON evidence and
    # code are supplied as canonical/manifest paths by the caller.  This keeps
    # a long-lived ``results/`` tree from becoming a retrospective checkpoint.
    for directory_name in directories:
        directory = root / directory_name
        if not directory.is_dir():
            continue
        for path in directory.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in _DEFAULT_SUFFIXES:
                continue
            relative = path.relative_to(root).as_posix()
            if any(relative.startswith(prefix) for prefix in _EXCLUDED_PREFIXES):
                continue
            try:
                if path.stat().st_size <= 32 * 1024 * 1024:
                    paths.add(relative)
            except OSError:
                continue
    return paths


def build_checkpoint_scope(
    project: str | Path,
    *,
    stage: str,
    payload: dict[str, Any] | None = None,
    canonical_paths: Iterable[str] = (),
) -> dict[str, Any]:
    """Build a review scope whose declared paths always outrank discovery.

    Discovery is a bounded safety net for a missing plugin output declaration.
    It is never allowed to promote arbitrary historical content from ``review``
    or every result from a long-lived project directory.
    """

    root = Path(project).resolve()
    payload_paths = _paths_from_value(root, payload or {})
    declared = _manifest_paths(root, stage)
    canonical = {_safe_relative(root, value) for value in canonical_paths}
    canonical.discard(None)
    direct = _direct_stage_paths(root, stage)
    selected = sorted({*payload_paths, *declared, *canonical, *direct})
    rows = []
    for relative in selected:
        origins = []
        if relative in payload_paths:
            origins.append("payload")
        if relative in declared:
            origins.append("manifest")
        if relative in canonical:
            origins.append("canonical")
        if relative in direct:
            origins.append("stage_owned_discovery")
        rows.append({"project_relative_path": relative, "origins": origins})
    payload_out = {
        "schema_version": CHECKPOINT_SCOPE_SCHEMA,
        "stage": stage,
        "artifacts": rows,
        "excluded_prefixes": list(_EXCLUDED_PREFIXES),
        "scope_mode": "manifest_first_bounded_discovery",
    }
    payload_out["scope_sha256"] = _hash(payload_out)
    return payload_out


def discover_checkpoint_scope_paths(project: str | Path, *, stage: str, payload: dict[str, Any] | None = None, canonical_paths: Iterable[str] = ()) -> list[str]:
    scope = build_checkpoint_scope(project, stage=stage, payload=payload, canonical_paths=canonical_paths)
    return [str(item.get("project_relative_path")) for item in scope["artifacts"]]


__all__ = ["CHECKPOINT_SCOPE_SCHEMA", "build_checkpoint_scope", "discover_checkpoint_scope_paths"]
