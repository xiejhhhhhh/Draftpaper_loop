"""Read-only publication readiness for a complete C3 revision round."""

from __future__ import annotations

import hashlib
import html
import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from .artifact_identity import canonical_json, compute_artifact_identity
from .core_evidence_batch import (
    CORE_EVIDENCE_OPERATION_LOCK,
    _REVISION_TASK_SCOPES,
    _write_revision,
    load_core_evidence_batch,
)
from .evidence_snapshot import EvidenceSnapshotMismatch, evidence_confirmation_subject
from .passport import load_project_passport, overlay_checkpoint_batch_association, project_root, read_jsonl, utc_now
from .revision_cycle import load_active_revision_cycle, _seal_revision_cycle_record
from .state_kernel import atomic_write_json, atomic_write_text, file_lock


READINESS_SCHEMA = "dpl.core_evidence_readiness.v1"
MAX_DIRECT_EVIDENCE_BYTES = 64 * 1024 * 1024
SUPPORTED_COMPLETION_CHECKS = frozenset({"matching_artifact_hash"})


class CoreEvidenceReadinessError(RuntimeError):
    """The exact frozen C3 candidate is no longer eligible for a decision."""


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        result = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    return result if isinstance(result, dict) else {}


def _confined_artifact(root: Path, relative: str) -> Path | None:
    try:
        path = (root / relative).resolve()
        path.relative_to(root.resolve())
    except (OSError, ValueError):
        return None
    return path if path.is_file() and path.stat().st_size <= MAX_DIRECT_EVIDENCE_BYTES else None


def _receipt_current(root: Path, task: dict[str, Any]) -> bool:
    declared = sorted({
        str(value)
        for field in ("expected_artifacts", "evidence_refs")
        for value in task.get(field) or []
    })
    if not declared:
        return False
    receipts = {
        str(row.get("path")): row
        for row in task.get("completion_receipts") or []
        if isinstance(row, dict)
    }
    for relative in declared:
        path = _confined_artifact(root, relative)
        receipt = receipts.get(relative)
        if path is None or not isinstance(receipt, dict):
            return False
        byte_match = receipt.get("sha256") == hashlib.sha256(path.read_bytes()).hexdigest()
        semantic_match = (
            isinstance(receipt.get("semantic_sha256"), str)
            and receipt["semantic_sha256"] == compute_artifact_identity(path, relative)["semantic_sha256"]
        )
        if not byte_match and not semantic_match:
            return False
    return True


def validate_core_evidence_candidate(project: str | Path, *, candidate_generation: int) -> dict[str, Any]:
    """Inspect in-scope prose candidates without installing them as formal sections."""
    root = project_root(project)
    cycle = load_active_revision_cycle(root) or {}
    if int(cycle.get("candidate_generation") or 0) != candidate_generation:
        return {"status": "blocked", "issues": ["candidate_generation_changed"], "candidate_hashes": {}}
    expected = {
        relative
        for task in cycle.get("pending_tasks") or []
        if isinstance(task, dict) and task.get("checkpoint_scope") == "core_evidence"
        for relative in task.get("expected_artifacts") or []
        if str(relative).startswith("writing/candidates/") and str(relative).endswith(".tex")
    }
    issues: list[str] = []
    hashes: dict[str, str] = {}
    for relative in sorted(expected):
        candidate = root / relative
        if not candidate.is_file():
            issues.append(f"missing_candidate:{relative}")
            continue
        if candidate.stat().st_size > MAX_DIRECT_EVIDENCE_BYTES:
            issues.append(f"candidate_too_large_for_direct_validation:{relative}")
            continue
        digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
        hashes[relative] = digest
        section = candidate.stem
        validation = _read_json(root / "writing" / "section_validation" / f"{section}.json")
        bindings = _read_json(root / "writing" / "claim_bindings" / f"{section}.json")
        if validation.get("decision") not in {"pass", "passed"} or validation.get("candidate_hash") != digest:
            issues.append(f"candidate_validation_stale:{relative}")
        if bindings.get("status") not in {"pass", "passed"} or bindings.get("candidate_hash") != digest:
            issues.append(f"candidate_binding_stale:{relative}")
    return {"status": "blocked" if issues else "passed", "issues": issues, "candidate_hashes": hashes}


def _active_write_jobs(root: Path, batch_id: str, task_ids: set[str]) -> tuple[list[str], list[str]]:
    database = root / ".draftpaper" / "jobs.sqlite3"
    if not database.is_file():
        return [], []
    try:
        with sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True, timeout=2) as connection:
            rows = connection.execute(
                "SELECT job_id, command, arguments_json FROM jobs WHERE status IN ('submitted', 'running')"
            ).fetchall()
    except (sqlite3.Error, OSError):
        return [], ["job_registry_unavailable"]
    from .command_registry import command_spec

    blockers: list[str] = []
    for job_id, command, arguments_json in rows:
        spec = command_spec(str(command))
        if spec is not None and not spec.mutates_project:
            continue
        try:
            arguments = json.loads(arguments_json)
        except (TypeError, ValueError):
            arguments = {}
        if not isinstance(arguments, dict):
            arguments = {}
        scope = str(arguments.get("batch_id") or "")
        task = str(arguments.get("task_id") or "")
        if scope and scope != batch_id and task not in task_ids:
            continue
        blockers.append(str(job_id))
    return sorted(blockers), []


def assess_core_evidence_readiness(project: str | Path) -> dict[str, Any]:
    root = project_root(project)
    cycle = load_active_revision_cycle(root)
    batch = load_core_evidence_batch(root)
    if not cycle or not batch:
        legacy_blockers = [
            str(task.get("task_id") or task.get("task") or "unclassified_task")
            for task in (cycle or {}).get("pending_tasks") or []
            if not isinstance(task, dict)
            or task.get("status") != "completed"
            or not _receipt_current(root, task)
        ]
        return {
            "schema_version": READINESS_SCHEMA,
            "status": "blocked",
            "publishable": False,
            "batch_id": None,
            "candidate_generation": None,
            "base_decision_receipt_id": None,
            "scope_sha256": None,
            "input_manifest_sha256": None,
            "blocking_tasks": sorted(set(legacy_blockers)),
            "active_job_ids": [],
            "reason_codes": ["batch_scope_not_registered", *(["legacy_tasks_pending"] if legacy_blockers else [])],
            "next_action": {"command": "prepare-core-evidence-batch"},
        }
    pending_tasks = cycle.get("pending_tasks") or []
    blocking_tasks: list[str] = []
    reasons: set[str] = set()
    for index, task in enumerate(pending_tasks):
        scope = task.get("checkpoint_scope") if isinstance(task, dict) else None
        if isinstance(scope, str) and scope in _REVISION_TASK_SCOPES:
            continue
        identifier = str(task.get("task_id") or f"unclassified_task_{index + 1}") if isinstance(task, dict) else f"unclassified_task_{index + 1}"
        blocking_tasks.append(identifier)
        reasons.add("unclassified_checkpoint_scope")
    tasks = [
        task for task in pending_tasks
        if isinstance(task, dict) and task.get("checkpoint_scope") == "core_evidence"
    ]
    statuses = {str(task.get("task_id")): str(task.get("status")) for task in tasks}
    for task in tasks:
        identifier = str(task["task_id"])
        required = bool(task.get("required_before_publication"))
        if not required:
            continue
        if task.get("status") != "completed":
            blocking_tasks.append(identifier)
            reasons.add("batch_tasks_pending")
        elif set(task.get("completion_checks") or []) - SUPPORTED_COMPLETION_CHECKS:
            blocking_tasks.append(identifier)
            reasons.add("unsupported_completion_check")
        elif any(
            (root / str(relative)).is_file()
            and (root / str(relative)).stat().st_size > MAX_DIRECT_EVIDENCE_BYTES
            for field in ("expected_artifacts", "evidence_refs")
            for relative in task.get(field) or []
        ):
            blocking_tasks.append(identifier)
            reasons.add("oversized_direct_evidence_ref")
        elif not _receipt_current(root, task):
            blocking_tasks.append(identifier)
            reasons.add("stale_completion_receipt")
        elif any(statuses.get(predecessor) != "completed" for predecessor in task.get("depends_on") or []):
            blocking_tasks.append(identifier)
            reasons.add("batch_dependency_incomplete")
        if task.get("effect_class") == "unknown":
            if identifier not in blocking_tasks:
                blocking_tasks.append(identifier)
            reasons.add("unclassified_scientific_change")

    generation = int(cycle.get("candidate_generation") or 1)
    candidate = validate_core_evidence_candidate(root, candidate_generation=generation)
    if candidate["issues"]:
        reasons.add("candidate_validation_incomplete")
    active_jobs, job_errors = _active_write_jobs(root, str(batch["batch_id"]), set(statuses))
    reasons.update(job_errors)
    if active_jobs:
        reasons.add("batch_jobs_active")
    subject: dict[str, Any] = {}
    try:
        subject = evidence_confirmation_subject(root)
    except (EvidenceSnapshotMismatch, OSError, ValueError):
        reasons.add("core_evidence_incomplete")

    task_artifacts: dict[str, str] = {}
    for task in tasks:
        for field in ("expected_artifacts", "evidence_refs"):
            for relative in task.get(field) or []:
                path = _confined_artifact(root, relative)
                if path is not None:
                    task_artifacts[relative] = compute_artifact_identity(path, relative)["semantic_sha256"]
    manifest = {
        "scope_sha256": batch["scope_sha256"],
        "subject": subject,
        "task_artifacts": task_artifacts,
        "candidate_hashes": candidate["candidate_hashes"],
    }
    input_hash = _digest(manifest)
    phase = str(batch.get("phase") or "collecting")
    frozen = _read_json(root / str(batch.get("frozen_candidate_ref") or "")) if batch.get("frozen_candidate_ref") else {}
    if phase in {"ready_for_review", "awaiting_decision"} and (
        frozen.get("input_manifest_sha256") != input_hash
        or frozen.get("scope_sha256") != batch["scope_sha256"]
        or frozen.get("candidate_generation") != generation
    ):
        reasons.add("frozen_candidate_changed")
    if phase in {"closed", "abandoned"}:
        reasons.add("batch_not_open_for_publication")
    if not reasons and phase == "collecting":
        reasons.add("batch_not_finalized")
    publishable = not reasons and phase == "ready_for_review"
    if blocking_tasks:
        status = "collecting"
        next_command = "agent_action_required"
    elif reasons and reasons == {"batch_not_finalized"}:
        status = "validating"
        next_command = "finalize-core-evidence-batch"
    elif publishable:
        status = "ready"
        next_command = "checkpoint"
    elif phase == "awaiting_decision" and not reasons:
        status = "awaiting_confirmation"
        next_command = "resume"
    elif phase == "closed" and reasons == {"batch_not_open_for_publication"}:
        status = "confirmed"
        next_command = "continue"
    else:
        status = "blocked"
        next_command = "agent_action_required"
    return {
        "schema_version": READINESS_SCHEMA,
        "status": status,
        "publishable": publishable,
        "batch_id": batch["batch_id"],
        "candidate_generation": generation,
        "base_decision_receipt_id": batch.get("base_decision_receipt_id"),
        "scope_sha256": batch["scope_sha256"],
        "input_manifest_sha256": input_hash,
        "confirmation_subject_id": subject.get("confirmation_subject_id"),
        "evidence_snapshot_id": subject.get("evidence_snapshot_id"),
        "blocking_tasks": sorted(set(blocking_tasks)),
        "active_job_ids": active_jobs,
        "reason_codes": sorted(reasons),
        "candidate_check": candidate,
        "next_action": {"command": next_command},
    }


def assert_current_batch_checkpoint(project: str | Path, *, checkpoint_hash: str) -> None:
    """Guard every decision writer, including calls that bypass the orchestrator."""
    root = project_root(project)
    checkpoint = next((
        event for event in reversed(read_jsonl(root / "checkpoint_ledger.jsonl"))
        if event.get("kind") == "checkpoint" and event.get("hash") == checkpoint_hash
    ), None)
    if not checkpoint or checkpoint.get("stage") != "core_evidence":
        return
    if not checkpoint.get("batch_id"):
        checkpoint = overlay_checkpoint_batch_association(root, checkpoint)
        if not checkpoint.get("batch_id"):
            raise CoreEvidenceReadinessError(
                "Legacy core-evidence checkpoint has no registered batch scope; inspect the migration shadow and reconcile its full scope before deciding."
            )
    awaiting = load_project_passport(root).get("awaiting_checkpoint") or {}
    readiness = assess_core_evidence_readiness(root)
    batch = load_core_evidence_batch(root) or {}
    if (
        awaiting.get("hash") != checkpoint_hash
        or readiness.get("status") not in {"ready", "awaiting_confirmation"}
        or checkpoint.get("batch_id") != readiness.get("batch_id")
        or checkpoint.get("scope_sha256") != readiness.get("scope_sha256")
        or checkpoint.get("input_manifest_sha256") != readiness.get("input_manifest_sha256")
        or checkpoint.get("candidate_generation") != readiness.get("candidate_generation")
        or checkpoint.get("frozen_candidate_ref") != batch.get("frozen_candidate_ref")
        or checkpoint.get("base_decision_receipt_id") != batch.get("base_decision_receipt_id")
    ):
        raise CoreEvidenceReadinessError("The core-evidence batch candidate is no longer the current frozen request.")


def _write_unready_preview(root: Path, report: dict[str, Any]) -> dict[str, str]:
    cycle = load_active_revision_cycle(root) or {}
    directory = (
        root / "review" / "revision_reconciliation" / str(cycle["revision_cycle_id"])
        / f"generation-{int(cycle['candidate_generation']):04d}"
    )
    directory.mkdir(parents=True, exist_ok=True)
    tasks = [
        task for task in cycle.get("pending_tasks") or []
        if isinstance(task, dict)
        and (
            task.get("checkpoint_scope") == "core_evidence"
            or not isinstance(task.get("checkpoint_scope"), str)
            or task.get("checkpoint_scope") not in _REVISION_TASK_SCOPES
        )
    ]
    result: dict[str, str] = {}
    for lang, filename, other, heading, intro, reason_heading, task_heading in (
        (
            "zh-CN", "core_evidence_readiness.zh-CN.html", "core_evidence_readiness.en.html",
            "核心证据本轮收尾", "本轮证据修订尚未满足确认条件。先完成下列工作，再统一提交一次确认。",
            "当前阻断", "本轮任务",
        ),
        (
            "en", "core_evidence_readiness.en.html", "core_evidence_readiness.zh-CN.html",
            "Core Evidence Round", "This revision round is not ready for confirmation. Finish the work below before submitting one consolidated decision.",
            "Current blockers", "Round tasks",
        ),
    ):
        reasons = "".join(f"<li><code>{html.escape(str(value))}</code></li>" for value in report.get("reason_codes") or [])
        rows: list[str] = []
        for task in tasks:
            title = task.get("title_zh") if lang == "zh-CN" else task.get("title_en")
            identifier = str(task.get("task_id") or "")
            status = str(task.get("status") or "unknown")
            scope = str(task.get("checkpoint_scope") or "missing")
            if identifier in report.get("blocking_tasks", []):
                status = "待完成" if lang == "zh-CN" else "Needs work"
            refs = []
            for relative in dict.fromkeys([*(task.get("expected_artifacts") or []), *(task.get("evidence_refs") or [])]):
                artifact = _confined_artifact(root, str(relative))
                label = html.escape(str(relative))
                if artifact is not None:
                    href = html.escape(Path(os.path.relpath(artifact, directory)).as_posix(), quote=True)
                    refs.append(f'<a href="{href}">{label}</a>')
                else:
                    refs.append(f"<span>{label}</span>")
            rows.append(
                f"<li><strong>{html.escape(str(title or identifier))}</strong> "
                f"<code>{html.escape(identifier)}</code> <small>{html.escape(status)} · scope: {html.escape(scope)}</small>"
                f"<div class=refs>{' · '.join(refs)}</div></li>"
            )
        page = (
            '<!doctype html><html lang="' + lang + '"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta name="dpl-readiness-sha256" content="{_digest(report)}">'
            f'<title>{html.escape(heading)}</title>'
            '<style>body{font:16px/1.6 system-ui,sans-serif;color:#20282d;background:#f7f9f8;margin:0}'
            'main{max-width:850px;margin:0 auto;padding:24px 20px 64px}h1{font-size:1.8rem}h2{font-size:1.2rem;margin-top:28px}'
            'nav{display:flex;gap:14px}a{color:#086b68;overflow-wrap:anywhere}li{margin:12px 0}code{overflow-wrap:anywhere}'
            '.refs{font-size:.9rem;margin-top:4px}small{color:#a04a1e}section{border-top:1px solid #cbd4d0}'
            '@media(max-width:600px){main{padding:16px}h1{font-size:1.45rem}}</style>'
            f'<main><nav><a href="{other}">{"English" if lang == "zh-CN" else "中文"}</a></nav>'
            f'<h1>{html.escape(heading)}</h1><p>{html.escape(intro)}</p>'
            f'<section><h2>{html.escape(reason_heading)}</h2><ul>{reasons}</ul></section>'
            f'<section><h2>{html.escape(task_heading)}</h2><ul>{"".join(rows)}</ul></section></main></html>'
        )
        path = directory / filename
        atomic_write_text(path, page)
        result["preview_zh_html" if lang == "zh-CN" else "preview_en_html"] = str(path.resolve())
    return result


def existing_unready_preview_paths(project: str | Path, report: dict[str, Any]) -> dict[str, Any]:
    """Return current-generation preview paths without creating or refreshing files."""
    root = project_root(project)
    if report.get("publishable") or not report.get("reason_codes"):
        return {}
    cycle = load_active_revision_cycle(root)
    batch = load_core_evidence_batch(root)
    if not cycle or not batch or batch.get("phase") in {"closed", "abandoned"}:
        return {}
    directory = (
        root / "review" / "revision_reconciliation" / str(cycle.get("revision_cycle_id") or "")
        / f"generation-{int(cycle.get('candidate_generation') or 0):04d}"
    )
    zh = directory / "core_evidence_readiness.zh-CN.html"
    en = directory / "core_evidence_readiness.en.html"
    try:
        root_resolved = root.resolve()
        zh_resolved = zh.resolve()
        en_resolved = en.resolve()
        zh_relative = zh_resolved.relative_to(root_resolved).as_posix()
        if not zh_resolved.is_file() or not en_resolved.is_file():
            return {}
        marker = f'<meta name="dpl-readiness-sha256" content="{_digest(report)}">'
        if marker not in zh_resolved.read_text(encoding="utf-8") or marker not in en_resolved.read_text(encoding="utf-8"):
            return {}
    except (OSError, ValueError):
        return {}
    return {
        "primary_human_review_html": {
            "project_relative_path": zh_relative,
            "absolute_path": str(zh_resolved),
            "locale": "zh-CN",
        },
        "preview_zh_html": str(zh_resolved),
        "preview_en_html": str(en_resolved),
    }


def finalize_core_evidence_batch(
    project: str | Path, *, expected_scope_sha256: str | None = None,
) -> dict[str, Any]:
    root = project_root(project)
    with file_lock(root / CORE_EVIDENCE_OPERATION_LOCK):
        return _finalize_core_evidence_batch(root, expected_scope_sha256=expected_scope_sha256)


def _finalize_core_evidence_batch(
    project: str | Path, *, expected_scope_sha256: str | None = None,
) -> dict[str, Any]:
    root = project_root(project)
    report = assess_core_evidence_readiness(root)
    batch = load_core_evidence_batch(root)
    if not batch or (expected_scope_sha256 and report["scope_sha256"] != expected_scope_sha256):
        return {"status": "blocked", "reason_codes": ["batch_scope_changed"], "readiness": report}
    if report["status"] == "ready":
        return {"status": "ready", "readiness": report, "batch": batch}
    if report["reason_codes"] != ["batch_not_finalized"]:
        preview = _write_unready_preview(root, report)
        primary_path = Path(preview["preview_zh_html"]).resolve()
        return {
            "status": "needs_work",
            "reason_codes": report["reason_codes"],
            "readiness": report,
            **preview,
            "primary_human_review_html": {
                "project_relative_path": primary_path.relative_to(root).as_posix(),
                "absolute_path": str(primary_path),
                "locale": "zh-CN",
            },
        }
    cycle = load_active_revision_cycle(root)
    generation = int(cycle["candidate_generation"])
    directory = root / "review" / "revision_reconciliation" / cycle["revision_cycle_id"] / f"generation-{generation:04d}"
    path = directory / "core_evidence_readiness.json"
    final = {**report, "status": "ready", "publishable": True, "reason_codes": [], "next_action": {"command": "checkpoint"}}
    if path.is_file():
        if _read_json(path) != final:
            return {"status": "blocked", "reason_codes": ["candidate_readiness_collision"], "readiness": report}
    else:
        atomic_write_json(path, final)
    updated = dict(cycle)
    updated["evidence_batch"] = {
        **batch, "phase": "ready_for_review", "finalization_requested": True,
        "frozen_candidate_ref": path.relative_to(root).as_posix(),
    }
    updated["review_status"] = "ready_for_review"
    updated["revision_generation"] = int(cycle["revision_generation"]) + 1
    updated["updated_at"] = utc_now()
    updated = _seal_revision_cycle_record(updated)
    _write_revision(root, updated)
    verified = assess_core_evidence_readiness(root)
    return {"status": "ready" if verified["publishable"] else "blocked", "readiness": verified, "batch": updated["evidence_batch"]}


__all__ = [
    "READINESS_SCHEMA", "CoreEvidenceReadinessError", "assess_core_evidence_readiness",
    "assert_current_batch_checkpoint", "finalize_core_evidence_batch", "validate_core_evidence_candidate",
]
