# Copyright (c) 2026 xiejhhhhhh
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .project_scaffold import _write_json, utc_now
from .project_state import load_project


OBSERVATION_LEDGER = "observations/observations.jsonl"


class ObservationError(RuntimeError):
    """Raised when an observation cannot be recorded or loaded."""


def _observation_dir(project_path: Path) -> Path:
    path = project_path / "observations"
    path.mkdir(parents=True, exist_ok=True)
    return path


def record_observation(
    project: str | Path,
    *,
    stage: str,
    kind: str,
    text: str,
    source: str = "codex_visible_analysis",
) -> dict[str, Any]:
    """Append a visible user/Codex analysis note to the project observation ledger."""
    state = load_project(project)
    clean_stage = str(stage or "").strip().lower()
    clean_kind = str(kind or "").strip().lower()
    clean_text = " ".join(str(text or "").split())
    if not clean_stage:
        raise ObservationError("Observation stage is required.")
    if not clean_kind:
        raise ObservationError("Observation kind is required.")
    if not clean_text:
        raise ObservationError("Observation text is required.")
    payload = {
        "project_id": state.metadata.get("project_id"),
        "stage": clean_stage,
        "kind": clean_kind,
        "source": source,
        "text": clean_text,
        "created_at": utc_now(),
    }
    path = _observation_dir(state.path) / "observations.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    _write_json(_observation_dir(state.path) / "latest_observation.json", payload)
    return {
        "status": "recorded",
        "project_path": str(state.path),
        "observation_ledger": str(path),
        "stage": clean_stage,
        "kind": clean_kind,
    }


def load_observations(project: str | Path, *, stage: str | None = None) -> list[dict[str, Any]]:
    """Load recorded visible observations, optionally filtered by stage."""
    state = load_project(project)
    path = state.path / OBSERVATION_LEDGER
    if not path.exists():
        return []
    wanted_stage = str(stage or "").strip().lower()
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        if wanted_stage and payload.get("stage") != wanted_stage:
            continue
        records.append(payload)
    return records

