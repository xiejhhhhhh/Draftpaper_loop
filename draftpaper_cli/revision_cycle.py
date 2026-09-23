"""First-class revision cycles bound to immutable scientific baselines."""

from __future__ import annotations

import hashlib
import html
import json
import uuid
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator

from .artifact_identity import canonical_json
from .passport import project_root, utc_now
from .scientific_baseline import ScientificBaselineError, create_scientific_baseline, read_active_baseline_state
from .state_kernel import atomic_write_json
from .scoped_transaction import ScopedProjectTransaction


REVISION_SCHEMA = "dpl.revision_cycle.v2"
LEGACY_REVISION_SCHEMA = "dpl.revision_cycle.v1"
REVISION_DIR = "lineage/revision_cycles"
ACTIVE_POINTER = ".draftpaper/active_revision_cycle.json"
REVISION_MODES = {"live", "author_edit"}
RECONCILIATION_STATES = {"reconciled", "pending", "reviewing", "repair_required", "awaiting_decision"}


class RevisionCycleError(RuntimeError):
    """Raised when a revision cycle cannot be opened safely."""


def _hash(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


@lru_cache(maxsize=2)
def _revision_cycle_validator(schema_version: str) -> Draft202012Validator:
    schema_files = {
        LEGACY_REVISION_SCHEMA: "revision_cycle_v1.json",
        REVISION_SCHEMA: "revision_cycle_v2.json",
    }
    filename = schema_files.get(schema_version)
    if filename is None:
        raise RevisionCycleError(f"Unsupported revision-cycle schema: {schema_version or 'missing'}.")
    try:
        resource = files("draftpaper_cli").joinpath("resources").joinpath("schemas").joinpath(filename)
        schema = json.loads(resource.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
    except (OSError, ValueError) as exc:
        raise RevisionCycleError(f"Revision-cycle schema resource is invalid: {filename}.") from exc
    return Draft202012Validator(schema)


def _validate_revision_cycle_record(payload: dict[str, Any], schema_version: str) -> None:
    validator = _revision_cycle_validator(schema_version)
    errors = sorted(validator.iter_errors(payload), key=lambda error: tuple(str(part) for part in error.absolute_path))
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.absolute_path) or "<root>"
        raise RevisionCycleError(
            f"Revision cycle schema validation failed for {schema_version} at {location}: {first.message}"
        )


def _seal_revision_cycle_record(payload: dict[str, Any]) -> dict[str, Any]:
    sealed = dict(payload)
    sealed["schema_version"] = REVISION_SCHEMA
    sealed.pop("revision_cycle_sha256", None)
    sealed["revision_cycle_sha256"] = _hash(sealed)
    _validate_revision_cycle_record(sealed, REVISION_SCHEMA)
    return sealed


def _legacy_value_is_positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _migrate_legacy_revision_cycle(payload: dict[str, Any]) -> dict[str, Any]:
    source = json.loads(canonical_json(payload))
    source_hash = str(source["revision_cycle_sha256"])
    cycle_id = source.get("revision_cycle_id")
    status = source.get("status")
    if (
        not isinstance(cycle_id, str)
        or not cycle_id.strip()
        or not isinstance(status, str)
        or status not in {"open", "closed", "superseded", "rejected"}
    ):
        raise RevisionCycleError("Active revision cycle cannot be safely migrated from its v1 identity/status.")

    defaulted_fields: set[str] = {"mode", "automatic_upstream", "reconciliation_status"}
    missing_fields: set[str] = set()

    def text_value(key: str, fallback: str, *, required_for_migration: bool = False) -> str:
        value = source.get(key)
        if isinstance(value, str) and value.strip():
            return value
        defaulted_fields.add(key)
        if required_for_migration:
            missing_fields.add(key)
        return fallback

    def nullable_text_value(key: str) -> str | None:
        value = source.get(key)
        if value is None or isinstance(value, str):
            if key not in source:
                defaulted_fields.add(key)
            return value
        defaulted_fields.add(key)
        missing_fields.add(key)
        return None

    def string_array_value(key: str) -> list[str]:
        value = source.get(key)
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return value
        defaulted_fields.add(key)
        if key not in source:
            missing_fields.add(key)
        return []

    def generation_value(key: str) -> int:
        value = source.get(key)
        if _legacy_value_is_positive_int(value):
            return value
        defaulted_fields.add(key)
        missing_fields.add(key)
        return 1

    raw_pending_tasks = source.get("pending_tasks")
    if isinstance(raw_pending_tasks, list) and all(isinstance(item, (dict, str)) for item in raw_pending_tasks):
        pending_tasks = [
            dict(item) if isinstance(item, dict) else {"task": item, "status": "pending"}
            for item in raw_pending_tasks
        ]
    else:
        pending_tasks = []
        defaulted_fields.add("pending_tasks")
        if "pending_tasks" not in source:
            missing_fields.add("pending_tasks")

    legacy_mode = source.get("mode")
    legacy_mode_hint = legacy_mode if isinstance(legacy_mode, str) and legacy_mode in REVISION_MODES else None
    if "project_id" not in source or (source.get("project_id") is not None and not isinstance(source.get("project_id"), str)):
        defaulted_fields.add("project_id")
        if "project_id" not in source:
            missing_fields.add("project_id")
    raw_review_status = source.get("review_status")
    if not isinstance(raw_review_status, str) or raw_review_status not in {"drafting", "validating", "ready_for_review", "awaiting_decision"}:
        defaulted_fields.add("review_status")
        if "review_status" not in source:
            missing_fields.add("review_status")
    updated: dict[str, Any] = {
        "schema_version": REVISION_SCHEMA,
        "revision_cycle_id": cycle_id,
        "project_id": source.get("project_id") if isinstance(source.get("project_id"), str) else None,
        "parent_baseline_id": nullable_text_value("parent_baseline_id"),
        "reason": text_value("reason", "legacy_import"),
        "requested_changes": string_array_value("requested_changes"),
        "allowed_change_classes": string_array_value("allowed_change_classes"),
        "protected_facts": string_array_value("protected_facts"),
        "expected_artifacts": string_array_value("expected_artifacts"),
        "expected_decision_items": string_array_value("expected_decision_items"),
        "pending_tasks": pending_tasks,
        "scope": text_value("scope", "project"),
        "revision_generation": generation_value("revision_generation"),
        "review_status": raw_review_status
        if isinstance(raw_review_status, str) and raw_review_status in {"drafting", "validating", "ready_for_review", "awaiting_decision"}
        else "drafting",
        "started_by": text_value("started_by", "legacy_migration"),
        "started_at": text_value("started_at", "unknown"),
        "status": status,
        "mode": "author_edit",
        "automatic_upstream": False,
        "reconciliation_status": "pending",
        "draft_generation": generation_value("draft_generation"),
        "candidate_generation": generation_value("candidate_generation"),
        "candidate_baseline_id": nullable_text_value("candidate_baseline_id"),
        "closed_by_decision_receipt": nullable_text_value("closed_by_decision_receipt"),
        "migration_status": "legacy_unverified",
        "migration_source_schema_version": LEGACY_REVISION_SCHEMA,
        "migration_source_sha256": source_hash,
        "migration_missing_fields": sorted(missing_fields),
        "migration_defaulted_fields": sorted(defaulted_fields),
        "legacy_mode_hint": legacy_mode_hint,
        "legacy_source_record": source,
    }
    closed_generation = source.get("closed_candidate_generation")
    if closed_generation is None or _legacy_value_is_positive_int(closed_generation):
        if "closed_candidate_generation" in source:
            updated["closed_candidate_generation"] = closed_generation
    else:
        defaulted_fields.add("closed_candidate_generation")
    for key in ("updated_at", "mode_changed_at", "closed_at", "commit_receipt_path"):
        value = source.get(key)
        if isinstance(value, str) and value:
            updated[key] = value
        elif key in source:
            defaulted_fields.add(key)
    candidate_packet_hash = source.get("candidate_packet_sha256")
    if isinstance(candidate_packet_hash, str) and len(candidate_packet_hash) == 64 and all(character in "0123456789abcdef" for character in candidate_packet_hash):
        updated["candidate_packet_sha256"] = candidate_packet_hash
    elif "candidate_packet_sha256" in source:
        defaulted_fields.add("candidate_packet_sha256")
    updated["migration_missing_fields"] = sorted(missing_fields)
    updated["migration_defaulted_fields"] = sorted(defaulted_fields)
    return _seal_revision_cycle_record(updated)


def _project_has_stale_stage(root: Path) -> bool:
    """Preserve an already recorded stale fact when a cycle is opened."""
    try:
        payload = json.loads((root / "project.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return False
    stages = payload.get("stages") if isinstance(payload, dict) else {}
    return bool(
        isinstance(stages, dict)
        and any(isinstance(item, dict) and item.get("stale") is True for item in stages.values())
    )


def begin_revision_cycle(
    project: str | Path,
    *,
    reason: str = "author_update",
    requested_changes: Iterable[str] = (),
    allowed_change_classes: Iterable[str] = (),
    protected_facts: Iterable[str] = (),
    expected_artifacts: Iterable[str] = (),
    expected_decision_items: Iterable[str] = (),
    pending_tasks: Iterable[dict[str, Any] | str] = (),
    scope: str = "project",
    started_by: str = "user",
    baseline_id: str | None = None,
    mode: str = "live",
) -> dict[str, Any]:
    if mode not in REVISION_MODES:
        raise RevisionCycleError("Revision mode must be live or author_edit.")
    root = project_root(project)
    active_cycle = load_active_revision_cycle(root)
    if active_cycle and active_cycle.get("status") == "open":
        raise RevisionCycleError("An active revision cycle is already open; close or reject it before opening another.")
    baseline_state = read_active_baseline_state(root)
    if baseline_state["status"] not in {"valid", "not_initialized"}:
        raise ScientificBaselineError(
            "Cannot begin a revision cycle because the active scientific baseline is "
            f"{baseline_state['status']}: {baseline_state.get('reason')}."
        )
    baseline = baseline_state.get("baseline")
    if baseline_id and (not baseline or baseline.get("baseline_id") != baseline_id):
        raise RevisionCycleError("Requested baseline is not the active immutable baseline.")
    if baseline is None:
        baseline = create_scientific_baseline(root, reason="revision_cycle_seed")["baseline"]
    payload = {
        "schema_version": REVISION_SCHEMA,
        "revision_cycle_id": "revision-" + uuid.uuid4().hex,
        "project_id": _project_id(root),
        "parent_baseline_id": baseline.get("baseline_id"),
        "reason": reason,
        "requested_changes": sorted({str(item) for item in requested_changes if str(item).strip()}),
        "allowed_change_classes": sorted({str(item) for item in allowed_change_classes if str(item).strip()}),
        "protected_facts": sorted({str(item) for item in protected_facts if str(item).strip()}),
        "expected_artifacts": sorted({str(item) for item in expected_artifacts if str(item).strip()}),
        "expected_decision_items": sorted({str(item) for item in expected_decision_items if str(item).strip()}),
        "pending_tasks": [
            dict(item) if isinstance(item, dict) else {"task": str(item), "status": "pending"}
            for item in pending_tasks
            if str(item).strip()
        ],
        "scope": str(scope or "project"),
        "revision_generation": 1,
        "review_status": "drafting",
        "started_by": started_by,
        "started_at": utc_now(),
        "status": "open",
        "mode": mode,
        "automatic_upstream": mode == "live",
        "reconciliation_status": "pending" if _project_has_stale_stage(root) else "reconciled",
        "draft_generation": 1,
        "candidate_generation": 1,
        "candidate_baseline_id": None,
        "closed_by_decision_receipt": None,
    }
    payload = _seal_revision_cycle_record(payload)
    path = root / REVISION_DIR / f"{payload['revision_cycle_id']}.json"
    atomic_write_json(path, payload)
    pointer = {
        "schema_version": "dpl.active_revision_cycle.v1",
        "revision_cycle_id": payload["revision_cycle_id"],
        "revision_cycle_sha256": payload["revision_cycle_sha256"],
        "path": str(path.relative_to(root).as_posix()),
        "updated_at": utc_now(),
    }
    atomic_write_json(root / ACTIVE_POINTER, pointer)
    return {"status": "started", "project_path": str(root), "revision_cycle": payload, "revision_cycle_path": str(path.resolve()), "active_pointer": str((root / ACTIVE_POINTER).resolve()), "parent_baseline_id": payload["parent_baseline_id"]}


def update_revision_cycle_review_state(
    project: str | Path,
    *,
    review_status: str,
    pending_tasks: Iterable[dict[str, Any] | str] | None = None,
    expected_decision_items: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Write a superseding review-state record without mutating cycle history."""

    if review_status not in {"drafting", "validating", "ready_for_review", "awaiting_decision"}:
        raise RevisionCycleError("Invalid revision review status.")
    root = project_root(project)
    active = load_active_revision_cycle(root)
    if not active or active.get("status") != "open":
        raise RevisionCycleError("No open revision cycle is available.")
    updated = dict(active)
    updated["review_status"] = review_status
    updated["revision_generation"] = int(updated.get("revision_generation") or 1) + 1
    if pending_tasks is not None:
        updated["pending_tasks"] = [
            dict(item) if isinstance(item, dict) else {"task": str(item), "status": "pending"}
            for item in pending_tasks
            if str(item).strip()
        ]
    if expected_decision_items is not None:
        updated["expected_decision_items"] = sorted(
            {str(item) for item in expected_decision_items if str(item).strip()}
        )
    updated["updated_at"] = utc_now()
    updated = _seal_revision_cycle_record(updated)
    path = root / REVISION_DIR / (
        f"{updated['revision_cycle_id']}-review-{updated['revision_generation']:04d}.json"
    )
    atomic_write_json(path, updated)
    atomic_write_json(
        root / ACTIVE_POINTER,
        {
            "schema_version": "dpl.active_revision_cycle.v1",
            "revision_cycle_id": updated["revision_cycle_id"],
            "revision_cycle_sha256": updated["revision_cycle_sha256"],
            "path": str(path.relative_to(root).as_posix()),
            "updated_at": utc_now(),
        },
    )
    return {
        "status": review_status,
        "project_path": str(root),
        "revision_cycle": updated,
        "revision_cycle_path": str(path.resolve()),
    }


def set_revision_mode(project: str | Path, *, mode: str) -> dict[str, Any]:
    """Switch the automatic upstream policy for the open cycle only.

    This changes scheduling policy, never evidence validity.  Pending and
    stale facts are deliberately retained when moving between modes.
    """
    if mode not in REVISION_MODES:
        raise RevisionCycleError("Revision mode must be live or author_edit.")
    root = project_root(project)
    active = load_active_revision_cycle(root)
    if not active or active.get("status") != "open":
        raise RevisionCycleError("No open revision cycle is available.")
    updated = dict(active)
    updated["mode"] = mode
    updated["automatic_upstream"] = mode == "live"
    updated["mode_changed_at"] = utc_now()
    updated["revision_generation"] = int(updated.get("revision_generation") or 1) + 1
    updated = _seal_revision_cycle_record(updated)
    path = root / REVISION_DIR / f"{updated['revision_cycle_id']}-mode-{updated['revision_generation']:04d}.json"
    atomic_write_json(path, updated)
    atomic_write_json(root / ACTIVE_POINTER, {
        "schema_version": "dpl.active_revision_cycle.v1",
        "revision_cycle_id": updated["revision_cycle_id"],
        "revision_cycle_sha256": updated["revision_cycle_sha256"],
        "path": str(path.relative_to(root).as_posix()),
        "updated_at": utc_now(),
    })
    return {"status": "mode_changed", "project_path": str(root), "mode": mode, "automatic_upstream": mode == "live", "revision_cycle": updated, "revision_cycle_path": str(path.resolve())}


def _reconciliation_changes(project: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    from .change_impact import affected_stages, artifact_role_for_path, classify_change
    from .stale_sync import detect_artifact_drift

    drift = detect_artifact_drift(project)
    changes: list[dict[str, Any]] = []
    for item in [*(drift.get("changed_artifacts") or []), *(drift.get("missing_artifacts") or []), *(drift.get("added_artifacts") or [])]:
        path = str(item.get("path") or "")
        role, owner_stage = artifact_role_for_path(path)
        if item.get("drift_kind") == "byte_only_drift":
            change_class = "byte_only_drift"
            scientific = False
            reason = "Only bytes changed while the semantic artifact identity remained stable."
            affected = []
        elif item.get("drift_kind") == "unresolved_artifact":
            change_class = "unregistered_artifact"
            scientific = None
            reason = "The changed path is not covered by a known artifact role."
            affected = []
        else:
            change = classify_change(
                artifact_role=role,
                before=item.get("previous_semantic_sha256") or item.get("previous_sha256"),
                after=item.get("current_semantic_sha256") or item.get("current_sha256"),
                source_stage=owner_stage,
                declaration={
                    "before_semantic_fingerprint": item.get("previous_semantic_fingerprint"),
                    "after_semantic_fingerprint": item.get("current_semantic_fingerprint"),
                    "before_evidence_fingerprint": item.get("previous_evidence_sha256"),
                    "after_evidence_fingerprint": item.get("current_evidence_sha256"),
                },
            )
            change_class = change.change_class
            scientific = change.scientific_semantics_changed
            reason = change.reason
            affected = affected_stages(change)
        changes.append({
            **item,
            "artifact_role": role,
            "change_class": change_class,
            "scientific_semantics_changed": scientific,
            "affected_stages": sorted(set(affected)),
            "reason": reason,
            "requires_human_confirmation": scientific is True,
            "reconciliation_action": "rebind_or_reuse" if scientific is False else "scientific_review_required" if scientific is True else "classify_before_release",
        })
    return drift, changes


def _write_reconciliation_summary(
    path: Path,
    *,
    language: str,
    mode: str,
    generation: int,
    changes: list[dict[str, Any]],
    status: str,
    reconciliation_id: str,
    packet_hash: str,
    base_snapshot_id: str | None,
    preview_pdf_path: str | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for item in changes:
        key = str(item.get("change_class") or "unclassified")
        counts[key] = counts.get(key, 0) + 1
    count_text = ", ".join(f"{key}={value}" for key, value in sorted(counts.items())) or "none"
    preserved_count = sum(
        1
        for item in changes
        if item.get("scientific_semantics_changed") is False
    )
    scientific_count = sum(
        1
        for item in changes
        if item.get("scientific_semantics_changed") is True
    )
    unresolved_count = sum(
        1
        for item in changes
        if item.get("scientific_semantics_changed") is None
    )
    affected_stage_count = len({
        stage
        for item in changes
        for stage in item.get("affected_stages") or []
        if str(stage).strip()
    })
    artifact_items = []
    for item in changes:
        relative = str(item.get("path") or "").replace("\\", "/")
        if not relative:
            continue
        stages = ", ".join(str(stage) for stage in item.get("affected_stages") or [] if str(stage).strip())
        artifact_items.append(
            "<li><span class='path'>"
            + html.escape(relative)
            + "</span>"
            + (" <small>" + html.escape(stages) + "</small>" if stages else "")
            + "</li>"
        )
    artifact_list = "".join(artifact_items) or "<li>None</li>"
    values = {
        "mode": html.escape(str(mode)),
        "generation": html.escape(str(generation)),
        "status": html.escape(str(status)),
        "reconciliation_id": html.escape(str(reconciliation_id)),
        "packet_hash": html.escape(str(packet_hash)),
        "base_snapshot_id": html.escape(str(base_snapshot_id or "none")),
        "preview_pdf_path": html.escape(str(preview_pdf_path or "not generated")),
        "change_count": html.escape(str(len(changes))),
        "change_counts": html.escape(count_text),
        "preserved_count": html.escape(str(preserved_count)),
        "scientific_count": html.escape(str(scientific_count)),
        "unresolved_count": html.escape(str(unresolved_count)),
        "affected_stage_count": html.escape(str(affected_stage_count)),
    }
    if language == "en":
        title = "Revision reconciliation review"
        sentence = (
            f"This candidate generation ({values['generation']}) uses {values['mode']} mode and records "
            f"{values['change_count']} change(s) from the immutable baseline ({values['base_snapshot_id']}). "
            f"It preserves {values['preserved_count']} non-scientific item(s), identifies "
            f"{values['scientific_count']} scientific change(s), and leaves {values['unresolved_count']} "
            f"item(s) to classify. The affected stage count is {values['affected_stage_count']}; "
            f"change classes are {values['change_counts']}. Scientific changes must be decided and "
            "rebound before this candidate can become a formal manuscript or release."
        )
        labels = {
            "mode": "Mode",
            "generation": "Generation",
            "status": "Reconciliation status",
            "reconciliation_id": "Reconciliation ID",
            "base_snapshot_id": "Baseline snapshot",
            "packet_hash": "Packet SHA-256",
            "preview_pdf_path": "Preview PDF",
            "changes": "Changes",
            "class": "Change class",
            "reason": "Reason",
            "human": "Human confirmation",
            "scope": "What this generation contains",
            "preserved": "Preserved or non-scientific changes",
            "scientific": "Scientific changes requiring decision",
            "unresolved": "Unclassified changes requiring review",
            "stages": "Affected workflow stages",
            "artifacts": "Candidate artifacts observed",
            "none": "None",
            "yes": "yes",
            "no": "no",
        }
        pending = "This is an unreconciled draft: release_eligible=false; reconciliation pending."
    else:
        title = "修订证据对账确认"
        sentence = (
            f"本候选版本为 generation {values['generation']}，采用 {values['mode']} 模式，"
            f"相对于不可变基线（{values['base_snapshot_id']}）发现 {values['change_count']} 项变化。"
            f"其中保留或可按非科学变化处理 {values['preserved_count']} 项，科学语义变化 "
            f"{values['scientific_count']} 项，尚待分类 {values['unresolved_count']} 项，影响 "
            f"{values['affected_stage_count']} 个阶段；变化分类为 {values['change_counts']}。"
            "科学语义变化必须完成用户决策和证据重新绑定，才能成为正式稿件或发布版本。"
        )
        labels = {
            "mode": "模式",
            "generation": "候选代次",
            "status": "对账状态",
            "reconciliation_id": "对账编号",
            "base_snapshot_id": "基线快照",
            "packet_hash": "对账包 SHA-256",
            "preview_pdf_path": "预览 PDF",
            "changes": "变化明细",
            "class": "变化类别",
            "reason": "原因",
            "human": "需要人工确认",
            "scope": "本候选版本包含的内容",
            "preserved": "保留或可按非科学变化处理",
            "scientific": "需要科学决策的变化",
            "unresolved": "尚待分类的变化",
            "stages": "受影响的工作流阶段",
            "artifacts": "本候选版本发现的产物",
            "none": "无",
            "yes": "是",
            "no": "否",
        }
        pending = "这是尚未完成对账的草稿：release_eligible=false；reconciliation pending（等待证据对账）。"
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(item.get('path') or ''))}</td>"
        f"<td>{html.escape(str(item.get('change_class') or 'unclassified'))}</td>"
        f"<td>{html.escape(str(item.get('reason') or ''))}</td>"
        f"<td>{labels['yes'] if item.get('requires_human_confirmation') else labels['no']}</td>"
        "</tr>"
        for item in changes
    )
    body_rows = rows or "<tr><td colspan='4'>No changes</td></tr>"
    rendered = (
        "<!doctype html><html lang='" + ("en" if language == "en" else "zh-CN") + "><head>"
        "<meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{title}</title>"
        "<style>body{font-family:system-ui,sans-serif;max-width:1180px;margin:2rem auto;padding:0 1rem;line-height:1.6;color:#202124}"
        "table{border-collapse:collapse;width:100%;margin-top:1rem}td,th{border:1px solid #bbb;padding:.45rem;text-align:left;vertical-align:top}"
        ".warning{border-left:4px solid #b45309;background:#fff7ed;padding:.8rem 1rem}.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:.5rem}"
        ".fact{border:1px solid #ddd;padding:.5rem}.path{word-break:break-all;font-family:ui-monospace,monospace}</style></head><body>"
        f"<h1>{title}</h1><div class='warning'>{pending}</div><p>{sentence}</p>"
        "<div class='facts'>"
        f"<div class='fact'><b>{labels['mode']}</b><br>{values['mode']}</div>"
        f"<div class='fact'><b>{labels['generation']}</b><br>{values['generation']}</div>"
        f"<div class='fact'><b>{labels['status']}</b><br>{values['status']}</div>"
        f"<div class='fact'><b>{labels['reconciliation_id']}</b><br><span class='path'>{values['reconciliation_id']}</span></div>"
        f"<div class='fact'><b>{labels['base_snapshot_id']}</b><br><span class='path'>{values['base_snapshot_id']}</span></div>"
        f"<div class='fact'><b>{labels['packet_hash']}</b><br><span class='path'>{values['packet_hash']}</span></div>"
        f"<div class='fact'><b>{labels['preview_pdf_path']}</b><br><span class='path'>{values['preview_pdf_path']}</span></div>"
        "</div>"
        f"<h2>{labels['scope']}</h2>"
        "<ul>"
        f"<li>{labels['preserved']}: {values['preserved_count']}</li>"
        f"<li>{labels['scientific']}: {values['scientific_count']}</li>"
        f"<li>{labels['unresolved']}: {values['unresolved_count']}</li>"
        f"<li>{labels['stages']}: {values['affected_stage_count']}</li>"
        "</ul>"
        f"<h2>{labels['artifacts']}</h2><ul>{artifact_list}</ul>"
        f"<h2>{labels['changes']}</h2>"
        f"<table><thead><tr><th>Path</th><th>{labels['class']}</th><th>{labels['reason']}</th><th>{labels['human']}</th></tr></thead>"
        f"<tbody>{body_rows}</tbody></table>"
        "</body></html>"
    )
    path.write_text(rendered, encoding="utf-8")


def prepare_revision_reconciliation(project: str | Path) -> dict[str, Any]:
    """Freeze the current candidate generation for one centralized review."""
    root = project_root(project)
    active = load_active_revision_cycle(root)
    if not active or active.get("status") != "open":
        raise RevisionCycleError("No open revision cycle is available.")
    drift, changes = _reconciliation_changes(root)
    generation = int(active.get("candidate_generation") or active.get("draft_generation") or 1) + 1
    has_scientific_change = any(item.get("scientific_semantics_changed") is True for item in changes)
    has_unresolved_change = any(item.get("scientific_semantics_changed") is None for item in changes)
    status = (
        "awaiting_decision"
        if has_scientific_change
        else "repair_required"
        if has_unresolved_change
        else "reviewing"
        if changes
        else "reconciled"
    )
    reconciliation_id = f"reconciliation-{active['revision_cycle_id']}-{generation:04d}"
    packet = {
        "schema_version": "dpl.revision_reconciliation.v1",
        "reconciliation_id": reconciliation_id,
        "revision_cycle_id": active["revision_cycle_id"],
        "mode": active.get("mode", "live"),
        "base_snapshot_id": active.get("parent_baseline_id"),
        "generation": generation,
        "status": status,
        "changes": changes,
        "drift_status": drift.get("status"),
        "created_at": utc_now(),
    }
    directory = root / "review" / "revision_reconciliation" / active["revision_cycle_id"] / f"generation-{generation:04d}"
    packet_path = directory / "reconciliation.json"
    summary_paths = {
        "zh-CN": directory / "reconciliation_summary.zh-CN.html",
        "en": directory / "reconciliation_summary.en.html",
    }
    packet["human_review"] = {
        language: str(path.relative_to(root).as_posix())
        for language, path in summary_paths.items()
    }
    packet["change_set_sha256"] = _hash(changes)
    packet["packet_sha256"] = _hash(packet)
    atomic_write_json(packet_path, packet)
    for language, summary_path in summary_paths.items():
        _write_reconciliation_summary(
            summary_path,
            language=language,
            mode=str(packet["mode"]),
            generation=generation,
            changes=changes,
            status=status,
            reconciliation_id=reconciliation_id,
            packet_hash=str(packet["packet_sha256"]),
            base_snapshot_id=packet.get("base_snapshot_id"),
        )
    updated = dict(active)
    updated.update({"candidate_generation": generation, "draft_generation": generation, "reconciliation_status": status, "candidate_packet_sha256": packet["packet_sha256"]})
    updated["revision_generation"] = int(updated.get("revision_generation") or 1) + 1
    updated["updated_at"] = utc_now()
    updated = _seal_revision_cycle_record(updated)
    state_path = root / REVISION_DIR / f"{active['revision_cycle_id']}-reconciliation-{updated['revision_generation']:04d}.json"
    atomic_write_json(state_path, updated)
    atomic_write_json(root / ACTIVE_POINTER, {"schema_version": "dpl.active_revision_cycle.v1", "revision_cycle_id": updated["revision_cycle_id"], "revision_cycle_sha256": updated["revision_cycle_sha256"], "path": str(state_path.relative_to(root).as_posix()), "updated_at": utc_now()})
    return {
        "status": "prepared",
        "project_path": str(root),
        "revision_cycle_id": active["revision_cycle_id"],
        "generation": generation,
        "reconciliation_status": status,
        "reconciliation_id": reconciliation_id,
        "reconciliation_path": str(packet_path.resolve()),
        "summary_html": str(summary_paths["zh-CN"].resolve()),
        "summary_html.zh-CN": str(summary_paths["zh-CN"].resolve()),
        "summary_html.en": str(summary_paths["en"].resolve()),
        "human_review": {
            language: str(path.resolve())
            for language, path in summary_paths.items()
        },
        "changes": changes,
        "release_eligible": False,
    }


def update_reconciliation_preview_pdf(
    project: str | Path,
    *,
    revision_cycle_id: str,
    generation: int,
    preview_pdf_path: str | None,
) -> dict[str, str]:
    """Refresh only the derived human-readable summaries with a preview path."""

    root = project_root(project)
    directory = root / "review" / "revision_reconciliation" / revision_cycle_id / f"generation-{int(generation):04d}"
    packet_path = directory / "reconciliation.json"
    if not packet_path.is_file():
        return {}
    try:
        packet = json.loads(packet_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    packet_hash = str(packet.get("packet_sha256") or "")
    if not packet_hash:
        return {}
    changes = [item for item in packet.get("changes") or [] if isinstance(item, dict)]
    paths = {
        "zh-CN": directory / "reconciliation_summary.zh-CN.html",
        "en": directory / "reconciliation_summary.en.html",
    }
    for language, path in paths.items():
        if path.is_file():
            _write_reconciliation_summary(
                path,
                language=language,
                mode=str(packet.get("mode") or "live"),
                generation=int(packet.get("generation") or generation),
                changes=changes,
                status=str(packet.get("status") or "pending"),
                reconciliation_id=str(packet.get("reconciliation_id") or ""),
                packet_hash=packet_hash,
                base_snapshot_id=packet.get("base_snapshot_id"),
                preview_pdf_path=preview_pdf_path,
            )
    return {
        language: str(path.resolve())
        for language, path in paths.items()
        if path.is_file()
    }


def apply_revision_reconciliation(
    project: str | Path,
    *,
    reconciliation_id: str,
    packet_hash: str,
    decision_receipt_id: str | None = None,
) -> dict[str, Any]:
    """Apply a reconciled candidate, requiring C3 user approval for semantic changes."""
    root = project_root(project)
    candidates = list((root / "review" / "revision_reconciliation").glob("*/generation-*/reconciliation.json"))
    path = next((item for item in candidates if item.is_file() and json.loads(item.read_text(encoding="utf-8-sig")).get("reconciliation_id") == reconciliation_id), None)
    if not path:
        raise RevisionCycleError("Revision reconciliation packet was not found.")
    packet = json.loads(path.read_text(encoding="utf-8-sig"))
    if packet.get("packet_sha256") != packet_hash or _hash({key: value for key, value in packet.items() if key != "packet_sha256"}) != packet_hash:
        raise RevisionCycleError("Revision reconciliation packet hash does not match its immutable preview.")
    active = load_active_revision_cycle(root)
    if not active or active.get("revision_cycle_id") != packet.get("revision_cycle_id") or active.get("status") != "open":
        raise RevisionCycleError("Revision reconciliation belongs to a different or closed cycle.")
    if (
        active.get("candidate_packet_sha256") != packet_hash
        or active.get("candidate_generation") != packet.get("generation")
    ):
        raise RevisionCycleError("The reconciliation packet is not the active candidate generation.")
    _current_drift, current_changes = _reconciliation_changes(root)
    expected_change_set = str(packet.get("change_set_sha256") or _hash(packet.get("changes") or []))
    if _hash(current_changes) != expected_change_set:
        raise RevisionCycleError(
            "The revision candidate changed after this reconciliation preview; prepare a new candidate generation."
        )
    changes = list(packet.get("changes") or [])
    semantic = [item for item in changes if item.get("scientific_semantics_changed") is True]
    unresolved = [item for item in changes if item.get("scientific_semantics_changed") is None]
    decision_receipt_sha256: str | None = None
    if unresolved and decision_receipt_id:
        raise RevisionCycleError("Unclassified changes must be resolved before a decision receipt can be applied.")
    if not semantic and decision_receipt_id:
        raise RevisionCycleError("A scientific decision receipt is only applicable to a semantic-change candidate.")
    if semantic and decision_receipt_id:
        receipt_path = _find_decision_receipt(root, decision_receipt_id)
        if receipt_path is None:
            raise RevisionCycleError("The scientific decision receipt is missing or ambiguous in this project.")
        decision_receipt_sha256 = _validate_candidate_decision_receipt(
            root,
            receipt_path,
            receipt_id=decision_receipt_id,
            active=active,
            baseline_id=str(active.get("parent_baseline_id") or ""),
            candidate_hash=packet_hash,
        )
        status = "reconciled"
    else:
        status = "awaiting_decision" if semantic else "repair_required" if unresolved else "reconciled"
    if status == "reconciled":
        from .passport import refresh_project_passport

        refresh_project_passport(root, event="revision_reconciliation_applied")
    receipt = {
        "schema_version": "dpl.revision_reconciliation_receipt.v1",
        "receipt_id": uuid.uuid4().hex,
        "reconciliation_id": reconciliation_id,
        "packet_sha256": packet_hash,
        "status": status,
        "scientific_changes": len(semantic),
        "unresolved_changes": len(unresolved),
        "created_at": utc_now(),
    }
    if decision_receipt_id and decision_receipt_sha256:
        receipt.update({
            "decision_receipt_id": decision_receipt_id,
            "decision_receipt_sha256": decision_receipt_sha256,
        })
    receipt["receipt_sha256"] = _hash(receipt)
    atomic_write_json(path.parent / "reconciliation_receipt.json", receipt)
    updated = dict(active)
    updated["reconciliation_status"] = status
    updated["closed_candidate_generation"] = packet.get("generation") if status == "reconciled" else None
    updated["revision_generation"] = int(updated.get("revision_generation") or 1) + 1
    updated["updated_at"] = utc_now()
    updated = _seal_revision_cycle_record(updated)
    state_path = root / REVISION_DIR / f"{active['revision_cycle_id']}-reconciled-{updated['revision_generation']:04d}.json"
    atomic_write_json(state_path, updated)
    atomic_write_json(root / ACTIVE_POINTER, {"schema_version": "dpl.active_revision_cycle.v1", "revision_cycle_id": updated["revision_cycle_id"], "revision_cycle_sha256": updated["revision_cycle_sha256"], "path": str(state_path.relative_to(root).as_posix()), "updated_at": utc_now()})
    return {
        "status": "reconciled" if status == "reconciled" else "awaiting_scientific_decision" if status == "awaiting_decision" else "repair_required",
        "project_path": str(root),
        "reconciliation_id": reconciliation_id,
        "reconciliation_status": status,
        "receipt": str((path.parent / "reconciliation_receipt.json").resolve()),
        "scientific_changes": len(semantic),
        "unresolved_changes": len(unresolved),
        "candidate_reconciled": status == "reconciled",
        "release_eligible": False,
        "release_eligibility_scope": "local_reconciliation_only",
    }


def load_active_revision_cycle(project: str | Path) -> dict[str, Any] | None:
    root = project_root(project)
    pointer_path = root / ACTIVE_POINTER
    if not pointer_path.exists():
        return None
    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise RevisionCycleError("Active revision cycle pointer is unreadable or corrupt.") from exc
    if not isinstance(pointer, dict) or pointer.get("schema_version") != "dpl.active_revision_cycle.v1":
        raise RevisionCycleError("Active revision cycle pointer has an unsupported schema.")
    relative_path = pointer.get("path")
    if not isinstance(relative_path, str) or not relative_path.strip():
        raise RevisionCycleError("Active revision cycle pointer has no record path.")
    try:
        path = (root / relative_path).resolve()
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise RevisionCycleError("Active revision cycle path escapes the project root.") from exc
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise RevisionCycleError("Active revision cycle record is not valid JSON.") from exc
    except OSError as exc:
        raise RevisionCycleError("Active revision cycle record is unavailable.") from exc
    if not isinstance(payload, dict):
        raise RevisionCycleError("Active revision cycle record must be a JSON object.")
    schema_version = payload.get("schema_version")
    if schema_version not in {LEGACY_REVISION_SCHEMA, REVISION_SCHEMA}:
        raise RevisionCycleError(f"Active revision cycle uses an unsupported schema: {schema_version or 'missing'}.")
    try:
        _validate_revision_cycle_record(payload, str(schema_version))
    except RevisionCycleError as exc:
        raise RevisionCycleError(f"Active revision cycle failed schema validation: {exc}") from exc
    expected_hash = payload.get("revision_cycle_sha256")
    actual_hash = _hash({key: value for key, value in payload.items() if key != "revision_cycle_sha256"})
    if expected_hash != actual_hash:
        raise RevisionCycleError("Active revision cycle content hash does not match its record.")
    if pointer.get("revision_cycle_id") != payload.get("revision_cycle_id") or pointer.get("revision_cycle_sha256") != payload.get("revision_cycle_sha256"):
        raise RevisionCycleError("Active revision cycle pointer does not match its immutable record.")
    if schema_version == LEGACY_REVISION_SCHEMA:
        try:
            return _migrate_legacy_revision_cycle(payload)
        except RevisionCycleError as exc:
            raise RevisionCycleError(f"Active revision cycle v1 migration failed: {exc}") from exc
    return payload


def close_revision_cycle(
    project: str | Path,
    *,
    decision_receipt_id: str,
    candidate_baseline_id: str | None = None,
    status: str = "closed",
) -> dict[str, Any]:
    if status not in {"closed", "superseded", "rejected"}:
        raise RevisionCycleError("Invalid revision cycle close status.")
    root = project_root(project)
    active = load_active_revision_cycle(root)
    if not active:
        raise RevisionCycleError("No active revision cycle.")
    reconciliation_status = str(active.get("reconciliation_status") or "pending")
    if status in {"closed", "superseded"}:
        # A cycle can be opened before the author edits a file.  Recheck the
        # live workspace at close time so an external edit cannot hide behind
        # the cycle's initial ``reconciled`` status.
        from .stale_sync import detect_artifact_drift

        live_drift = detect_artifact_drift(root)
        if live_drift.get("requires_reconciliation"):
            raise RevisionCycleError(
                "An unreconciled live artifact drift is present; prepare and "
                "apply reconciliation before closing the revision cycle."
            )
    if (
        status in {"closed", "superseded"}
        and reconciliation_status != "reconciled"
    ):
        raise RevisionCycleError(
            "An unreconciled revision candidate cannot be closed or superseded. "
            "Apply reconciliation first, or reject the cycle while preserving its receipt."
        )
    if status in {"closed", "superseded"} and active.get("mode") == "author_edit":
        raise RevisionCycleError(
            "An author_edit candidate must be finalized with commit-revision-candidate, "
            "which validates the exact candidate, baseline, and decision receipt."
        )
    if status == "rejected":
        candidate_baseline_id = None
    active["status"] = status
    active["candidate_baseline_id"] = candidate_baseline_id
    active["closed_by_decision_receipt"] = decision_receipt_id
    active["closed_at"] = utc_now()
    active = _seal_revision_cycle_record(active)
    # The immutable input is kept intact; a superseding cycle record is used
    # for closure metadata so history cannot be silently rewritten.
    closed_path = root / REVISION_DIR / f"{active['revision_cycle_id']}-closed.json"
    atomic_write_json(closed_path, active)
    pointer = {
        "schema_version": "dpl.active_revision_cycle.v1",
        "revision_cycle_id": active["revision_cycle_id"],
        "revision_cycle_sha256": active["revision_cycle_sha256"],
        "path": str(closed_path.relative_to(root).as_posix()),
        "updated_at": utc_now(),
    }
    atomic_write_json(root / ACTIVE_POINTER, pointer)
    return {"status": status, "project_path": str(root), "revision_cycle": active, "closed_record": str(closed_path.resolve()), "active_pointer": str((root / ACTIVE_POINTER).resolve())}


def _find_decision_receipt(root: Path, receipt_id: str) -> Path | None:
    wanted = str(receipt_id or "").strip()
    if not wanted or Path(wanted).name != wanted or wanted in {".", ".."}:
        return None
    matches: list[Path] = []
    for base in (root / "review", root / ".draftpaper"):
        if not base.is_dir():
            continue
        for receipt_dir in base.rglob("review_decision_receipts"):
            path = receipt_dir / f"{wanted}.json"
            if path.is_file():
                matches.append(path)
    return matches[0] if len(matches) == 1 else None


@lru_cache(maxsize=1)
def _decision_receipt_validator() -> Draft202012Validator:
    try:
        resource = files("draftpaper_cli").joinpath("resources").joinpath("schemas").joinpath(
            "review_decision_receipt_v2.json"
        )
        schema = json.loads(resource.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
    except (OSError, ValueError) as exc:
        raise RevisionCycleError("The review decision receipt schema resource is unavailable or invalid.") from exc
    return Draft202012Validator(schema)


def _validate_applied_candidate(
    root: Path,
    active: dict[str, Any],
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    cycle_id = str(active.get("revision_cycle_id") or "")
    candidate_hash = str(active.get("candidate_packet_sha256") or "")
    generation = active.get("candidate_generation")
    if (
        not candidate_hash
        or active.get("reconciliation_status") != "reconciled"
        or active.get("closed_candidate_generation") != generation
    ):
        raise RevisionCycleError(
            "The active revision has no applied reconciliation for its current candidate generation."
        )

    matches: list[tuple[Path, dict[str, Any]]] = []
    packet_root = root / "review" / "revision_reconciliation" / cycle_id
    if packet_root.is_dir():
        for path in packet_root.rglob("reconciliation.json"):
            try:
                packet = json.loads(path.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError):
                continue
            if not isinstance(packet, dict):
                continue
            packet_body = {key: value for key, value in packet.items() if key != "packet_sha256"}
            if (
                isinstance(packet, dict)
                and packet.get("packet_sha256") == candidate_hash
                and _hash(packet_body) == candidate_hash
            ):
                matches.append((path, packet))
    if len(matches) != 1:
        raise RevisionCycleError("The active candidate reconciliation packet is missing, ambiguous, or has an invalid hash.")

    packet_path, packet = matches[0]
    if (
        packet.get("revision_cycle_id") != cycle_id
        or packet.get("generation") != generation
        or packet.get("change_set_sha256") != _hash(packet.get("changes") or [])
    ):
        raise RevisionCycleError("The active reconciliation packet does not match the current cycle generation.")

    try:
        receipt = json.loads((packet_path.parent / "reconciliation_receipt.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise RevisionCycleError("The applied reconciliation receipt is missing or invalid.") from exc
    if not isinstance(receipt, dict):
        raise RevisionCycleError("The applied reconciliation receipt is not a JSON object.")
    receipt_body = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    if (
        receipt.get("schema_version") != "dpl.revision_reconciliation_receipt.v1"
        or receipt.get("reconciliation_id") != packet.get("reconciliation_id")
        or receipt.get("packet_sha256") != candidate_hash
        or receipt.get("status") != "reconciled"
        or receipt.get("unresolved_changes") != 0
        or receipt.get("receipt_sha256") != _hash(receipt_body)
    ):
        raise RevisionCycleError("The applied reconciliation receipt does not authorize this candidate generation.")
    scientific_changes = receipt.get("scientific_changes")
    if not isinstance(scientific_changes, int) or isinstance(scientific_changes, bool) or scientific_changes < 0:
        raise RevisionCycleError("The applied reconciliation receipt has an invalid scientific-change count.")
    decision_receipt_id = str(receipt.get("decision_receipt_id") or "")
    decision_receipt_sha256 = str(receipt.get("decision_receipt_sha256") or "")
    if scientific_changes > 0 or decision_receipt_id:
        if not decision_receipt_id or not decision_receipt_sha256:
            raise RevisionCycleError("Scientific changes require a candidate-bound user decision receipt.")
        decision_path = _find_decision_receipt(root, decision_receipt_id)
        if decision_path is None:
            raise RevisionCycleError("The scientific decision receipt applied to reconciliation is missing.")
        verified_hash = _validate_candidate_decision_receipt(
            root,
            decision_path,
            receipt_id=decision_receipt_id,
            active=active,
            baseline_id=str(active.get("parent_baseline_id") or ""),
            candidate_hash=candidate_hash,
        )
        if verified_hash != decision_receipt_sha256:
            raise RevisionCycleError("The scientific decision receipt changed after reconciliation was applied.")
    return candidate_hash, packet, receipt


def _validate_candidate_decision_receipt(
    root: Path,
    receipt_path: Path,
    *,
    receipt_id: str,
    active: dict[str, Any],
    baseline_id: str,
    candidate_hash: str,
) -> str:
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise RevisionCycleError("The candidate decision receipt cannot be read.") from exc
    errors = list(_decision_receipt_validator().iter_errors(receipt)) if isinstance(receipt, dict) else []
    if not isinstance(receipt, dict) or errors:
        raise RevisionCycleError("The candidate decision receipt does not satisfy the v2 receipt schema.")
    from .review_policy import DECISION_RECEIPT_SCHEMA, _decision_hash

    if (
        receipt.get("schema_version") != DECISION_RECEIPT_SCHEMA
        or receipt.get("receipt_id") != receipt_id
        or receipt.get("receipt_sha256") != _decision_hash(receipt)
        or receipt.get("project_id") != _project_id(root)
        or receipt.get("decision") != "approve"
        or receipt.get("decision_status") != "user_confirmed"
        or receipt.get("actor_type") != "user"
        or receipt.get("risk_class") != "C3"
        or receipt.get("revision_cycle_id") != active.get("revision_cycle_id")
        or receipt.get("baseline_id") != baseline_id
        or receipt.get("revision_candidate_sha256") != candidate_hash
        or not isinstance(receipt.get("checkpoint_hash"), str)
        or not receipt.get("checkpoint_hash")
        or not isinstance(receipt.get("summary_sha256"), str)
        or not receipt.get("summary_sha256")
    ):
        raise RevisionCycleError(
            "The decision receipt is invalid, not user-approved, or not bound to this project, baseline, cycle, and candidate."
        )
    return str(receipt["receipt_sha256"])


def commit_revision_candidate(
    project: str | Path,
    *,
    candidate_id: str,
    expected_baseline_id: str,
    decision_receipt_id: str,
) -> dict[str, Any]:
    """Atomically promote one reconciled candidate and its decision receipt.

    This is the strict finalization API.  The legacy close function remains
    available for read-compatible integrations, while new release paths must
    use this function so a free-form receipt string cannot certify a candidate.
    """
    root = project_root(project)
    active = load_active_revision_cycle(root)
    if not active or active.get("status") != "open":
        raise RevisionCycleError("No open revision cycle is available for commit.")
    baseline_state = read_active_baseline_state(root)
    if baseline_state.get("status") != "valid":
        raise RevisionCycleError("Cannot commit while the scientific baseline is not valid.")
    baseline = baseline_state["baseline"]
    if not expected_baseline_id or baseline.get("baseline_id") != expected_baseline_id:
        raise RevisionCycleError("The active scientific baseline changed before commit.")
    if active.get("parent_baseline_id") != baseline.get("baseline_id"):
        raise RevisionCycleError("Revision cycle parent baseline no longer matches the active baseline.")
    from .stale_sync import detect_artifact_drift

    drift = detect_artifact_drift(root)
    if drift.get("requires_reconciliation"):
        raise RevisionCycleError("An unreconciled live artifact drift is present; prepare and apply reconciliation first.")
    if active.get("reconciliation_status") != "reconciled":
        raise RevisionCycleError("The active revision candidate is not reconciled.")
    candidate_hash, _candidate_packet, applied_reconciliation_receipt = _validate_applied_candidate(root, active)
    if (
        int(applied_reconciliation_receipt.get("scientific_changes") or 0) > 0
        and applied_reconciliation_receipt.get("decision_receipt_id") != decision_receipt_id
    ):
        raise RevisionCycleError(
            "The scientific approval receipt consumed during reconciliation must also authorize candidate promotion."
        )
    if candidate_id != candidate_hash:
        raise RevisionCycleError("The requested candidate ID must exactly match the active reconciliation packet hash.")
    receipt_path = _find_decision_receipt(root, decision_receipt_id)
    if receipt_path is None:
        raise RevisionCycleError("The immutable decision receipt is missing or ambiguous in this project.")
    decision_receipt_sha256 = _validate_candidate_decision_receipt(
        root,
        receipt_path,
        receipt_id=decision_receipt_id,
        active=active,
        baseline_id=str(baseline.get("baseline_id") or ""),
        candidate_hash=candidate_hash,
    )
    result: dict[str, Any] = {}
    with ScopedProjectTransaction(root, ("lineage/**", ".draftpaper/active_scientific_baseline.json", ".draftpaper/active_revision_cycle.json")) as transaction:
        baseline_result = create_scientific_baseline(
            root,
            decision_receipt_id=decision_receipt_id,
            revision_cycle_id=str(active["revision_cycle_id"]),
            reason="revision_cycle_commit",
        )
        committed = dict(active)
        committed.update({
            "status": "closed",
            "candidate_baseline_id": baseline_result["baseline"]["baseline_id"],
            "closed_by_decision_receipt": decision_receipt_id,
            "closed_at": utc_now(),
            "commit_receipt_path": str(receipt_path.relative_to(root).as_posix()),
            "reconciliation_status": "reconciled",
        })
        committed = _seal_revision_cycle_record(committed)
        commit_record = {
            "schema_version": "dpl.revision_candidate_commit.v1",
            "commit_id": "commit-" + uuid.uuid4().hex,
            "revision_cycle_id": active["revision_cycle_id"],
            "parent_baseline_id": baseline["baseline_id"],
            "candidate_baseline_id": committed["candidate_baseline_id"],
            "candidate_packet_sha256": candidate_hash or None,
            "decision_receipt_id": decision_receipt_id,
            "decision_receipt_sha256": decision_receipt_sha256,
            "decision_receipt_path": str(receipt_path.relative_to(root).as_posix()),
            "created_at": utc_now(),
        }
        commit_record["commit_sha256"] = _hash(commit_record)
        commit_path = root / REVISION_DIR / f"{active['revision_cycle_id']}-commit.json"
        atomic_write_json(commit_path, commit_record)
        closed_path = root / REVISION_DIR / f"{active['revision_cycle_id']}-closed.json"
        atomic_write_json(closed_path, committed)
        atomic_write_json(root / ACTIVE_POINTER, {
            "schema_version": "dpl.active_revision_cycle.v1",
            "revision_cycle_id": committed["revision_cycle_id"],
            "revision_cycle_sha256": committed["revision_cycle_sha256"],
            "path": str(closed_path.relative_to(root).as_posix()),
            "updated_at": utc_now(),
        })
        # The state writes above and immutable commit record are treated as one
        # bounded transaction; an interrupted write rolls back the projection.
        transaction.commit()
        result = {
            "status": "committed",
            "project_path": str(root),
            "commit_record": str(commit_path.resolve()),
            "closed_record": str(closed_path.resolve()),
            "candidate_baseline_id": committed["candidate_baseline_id"],
            "release_eligible": True,
        }
    return result


def _project_id(root: Path) -> str | None:
    try:
        payload = json.loads((root / "project.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    return str(payload.get("project_id") or "") or None


__all__ = [
    "ACTIVE_POINTER",
    "REVISION_SCHEMA",
    "RevisionCycleError",
    "begin_revision_cycle",
    "apply_revision_reconciliation",
    "close_revision_cycle",
    "commit_revision_candidate",
    "load_active_revision_cycle",
    "prepare_revision_reconciliation",
    "set_revision_mode",
    "update_reconciliation_preview_pdf",
    "update_revision_cycle_review_state",
]
