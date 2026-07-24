"""Append-only workflow events derived from successful Core commands."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from ..passport import project_root, utc_now
from ..state_kernel import append_jsonl_locked


EVENT_LEDGER = ".draftpaper/extensions/workflow_events.jsonl"


_COMMAND_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "create-project": ("project.idea",),
    "search-literature": ("literature.search", "literature.verified"),
    "generate-plan": ("literature.synthesis", "research_plan.ready"),
    "review-research-plan": ("research_plan.ready",),
    "confirm-research-plan": ("research_plan.confirmed",),
    "inventory-data": ("data.inventory", "data.schema"),
    "collect-method-plan": ("method.plan",),
    "verify-methods": ("data.processing", "method.verified"),
    "plan-figures": ("figure.plan",),
    "assess-result-validity": ("result.validity",),
    "assess-result-support": ("result.support_checkpoint",),
    "assess-core-evidence": ("core_evidence.ready",),
    "confirm-core-evidence": ("core_evidence.confirmed",),
    "write-results": ("manuscript.results",),
    "review-results-with-discipline-rules": ("discipline.review",),
    "write-introduction": ("manuscript.introduction",),
    "write-data": ("manuscript.data",),
    "write-methods": ("manuscript.methods",),
    "write-discussion": ("manuscript.discussion",),
    "audit-citations": ("citation.audit",),
    "run-independent-review": ("review.completed",),
    "confirm-final-manuscript": ("manuscript.finalized",),
}


def _event_type(command: str) -> str:
    if command.startswith("confirm-"):
        return "workflow.checkpoint_confirmed"
    if command.startswith(("review-", "assess-result-support", "assess-core-evidence")):
        return "workflow.checkpoint_opened"
    if command.startswith(("reopen-", "apply-section-revision", "revise-")):
        return "artifact.invalidated"
    if command.startswith("run-independent-review"):
        return "review.completed"
    return "workflow.stage_committed"


def _artifact_paths(value: Any, root: Path) -> Iterable[str]:
    if isinstance(value, dict):
        for child in value.values():
            yield from _artifact_paths(child, root)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _artifact_paths(child, root)
    elif isinstance(value, str) and value and len(value) < 500:
        candidate = (root / value).resolve()
        try:
            relative = candidate.relative_to(root).as_posix()
        except (OSError, ValueError):
            return
        if candidate.is_file() and not relative.startswith((".git/", "guidance/", "guidance_reviews/")):
            yield relative


def _project_id(root: Path) -> str:
    try:
        document = json.loads((root / "project.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return root.name
    return str(document.get("project_id") or document.get("slug") or root.name)


@dataclass(frozen=True)
class WorkflowEvent:
    event_id: str
    event_type: str
    project_id: str
    command: str
    formal_stage: str
    occurred_at: str
    snapshot_hash: str
    stage_capabilities: tuple[str, ...]
    changed_artifacts: tuple[dict[str, str], ...]
    checkpoint_state: str
    evidence_state: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "dpl.workflow_event.v1",
            "event_id": self.event_id,
            "event_type": self.event_type,
            "project_id": self.project_id,
            "command": self.command,
            "formal_stage": self.formal_stage,
            "occurred_at": self.occurred_at,
            "snapshot_hash": self.snapshot_hash,
            "stage_capabilities": list(self.stage_capabilities),
            "changed_artifacts": list(self.changed_artifacts),
            "checkpoint_state": self.checkpoint_state,
            "evidence_state": self.evidence_state,
        }


def emit_command_event(
    project: str | Path,
    *,
    command: str,
    formal_stage: str,
    result: dict[str, Any],
) -> WorkflowEvent:
    root = project_root(project)
    artifacts = []
    for relative in sorted(set(_artifact_paths(result, root))):
        content = (root / relative).read_bytes()
        artifacts.append({"relative_path": relative, "sha256": hashlib.sha256(content).hexdigest()})
    snapshot_seed = json.dumps(artifacts, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    snapshot_hash = hashlib.sha256(snapshot_seed.encode("utf-8")).hexdigest()
    occurred_at = utc_now()
    event_type = _event_type(command)
    event_seed = f"{_project_id(root)}|{command}|{snapshot_hash}|{occurred_at}"
    event = WorkflowEvent(
        event_id="evt_" + hashlib.sha256(event_seed.encode("utf-8")).hexdigest()[:24],
        event_type=event_type,
        project_id=_project_id(root),
        command=command,
        formal_stage=formal_stage,
        occurred_at=occurred_at,
        snapshot_hash=snapshot_hash,
        stage_capabilities=_COMMAND_CAPABILITIES.get(command, (f"stage.{formal_stage}",)),
        changed_artifacts=tuple(artifacts),
        checkpoint_state=("opened" if event_type == "workflow.checkpoint_opened" else "confirmed" if event_type == "workflow.checkpoint_confirmed" else "none"),
        evidence_state=("confirmed" if "confirmed" in event_type or command == "confirm-core-evidence" else "provisional" if "checkpoint" in event_type else "current"),
    )
    append_jsonl_locked(root / EVENT_LEDGER, event.to_dict())
    return event
