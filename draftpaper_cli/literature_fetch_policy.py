"""Project-level policy for paper identity resolution and evidence fetching."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .project_scaffold import _write_json
from .project_state import load_project


FETCH_POLICY_SCHEMA = "dpl.literature_fetch_policy.v1"
FETCH_POLICY_RELATIVE_PATH = "references/literature_fetch_policy.json"
FETCH_MODES = {"off", "resolve_only", "resolve_then_fetch_on_demand", "fulltext_eager", "local_only"}


def default_literature_fetch_policy() -> dict[str, Any]:
    return {
        "schema_version": FETCH_POLICY_SCHEMA,
        "mode": "resolve_then_fetch_on_demand",
        "identity_resolution": "default_for_shortlist",
        "fulltext_fetch": "evidence_on_demand",
        "asset_profile": "none",
        "remote_document_classes": ["published-public"],
        "max_identity_candidates": 60,
        "max_fulltext_candidates": 12,
        "batch_concurrency": 4,
        "ambiguous_resolution": "review_required",
        "post_fetch_relevance_gate": True,
        "preserve_previous_snapshot_on_failure": True,
    }


def _canonical_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def validate_literature_fetch_policy(policy: dict[str, Any]) -> dict[str, Any]:
    value = {**default_literature_fetch_policy(), **dict(policy or {})}
    if value.get("schema_version") != FETCH_POLICY_SCHEMA:
        raise ValueError(f"Unsupported literature fetch policy schema: {value.get('schema_version')}")
    mode = str(value.get("mode") or "")
    if mode not in FETCH_MODES:
        raise ValueError(f"Unsupported literature fetch mode: {mode}")
    if str(value.get("asset_profile") or "none") != "none":
        raise ValueError("Draftpaper-loop Core only supports asset_profile=none for automatic literature fetching.")
    for field in ("max_identity_candidates", "max_fulltext_candidates", "batch_concurrency"):
        value[field] = max(0, int(value.get(field) or 0))
    value["batch_concurrency"] = min(8, max(1, value["batch_concurrency"]))
    value["policy_hash"] = _canonical_hash({key: item for key, item in value.items() if key != "policy_hash"})
    return value


def load_literature_fetch_policy(
    project: str | Path,
    *,
    mode: str | None = None,
    write_default: bool = True,
) -> dict[str, Any]:
    state = load_project(project)
    path = state.path / FETCH_POLICY_RELATIVE_PATH
    payload: dict[str, Any] = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            loaded = {}
        if isinstance(loaded, dict):
            payload = loaded
    if mode:
        payload = {**payload, "mode": mode}
    policy = validate_literature_fetch_policy(payload or default_literature_fetch_policy())
    if write_default or mode:
        _write_json(path, policy)
    return policy


def policy_hash(policy: dict[str, Any]) -> str:
    return str(validate_literature_fetch_policy(policy).get("policy_hash") or "")
