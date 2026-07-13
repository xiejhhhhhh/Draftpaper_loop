"""Create clean project versions and import legacy assets without active-state leakage."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

from .artifact_repository import ArtifactRepository
from .passport import load_project_passport, refresh_project_passport
from .project_scaffold import create_project, utc_now
from .project_state import load_project, validate_project
from .state_kernel import atomic_write_json
from .structured_io import read_mapping


LINEAGE_PATH = "project_lineage.json"
IMPORT_PLAN_PATH = "lineage/asset_import_plan.json"
IMPORT_LEDGER_PATH = "lineage/import_ledger.json"
LOCATOR_ROOT = "lineage/locators"

MAX_COPY_BYTES = 50 * 1024 * 1024
VERSION_PATTERN = re.compile(r"^v[0-9]+$")

STATE_FILENAMES = {
    "project.json",
    "project.yaml",
    "project_passport.yaml",
    "artifact_ledger.jsonl",
    "checkpoint_ledger.jsonl",
    "integrity_ledger.jsonl",
    "transaction_ledger.jsonl",
    "token_ledger.jsonl",
    "project_system_of_record.json",
}

DERIVED_NAMES = {
    "stage_manifest.json",
    "figure_metadata.json",
    "plugin_sufficiency_report.json",
    "project_local_capability_audit.json",
    "research_capability_contract.json",
    "result_manifest.yaml",
    "result_manifest.json",
    "resolved_result_evidence.json",
    "core_evidence_report.json",
    "promoted_evidence_snapshot.json",
    "final_citation_audit_report.json",
    "citation_audit_report.json",
}

RUNTIME_SUFFIXES = {
    ".aux",
    ".bbl",
    ".blg",
    ".log",
    ".out",
    ".synctex.gz",
    ".tmp",
    ".lock",
}


class ProjectVersioningError(RuntimeError):
    """Raised when a project version cannot be planned or created safely."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _safe_relative(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise ProjectVersioningError(f"Asset escapes source project: {path}") from exc


def _owner_stage(relative: str) -> str:
    first = relative.split("/", 1)[0]
    if first == "latex":
        return "latex"
    if first == "quality":
        return "quality_checks"
    if first == "citation_audit":
        return "quality_checks"
    return first


def _is_runtime_private(relative: str, path: Path) -> bool:
    lowered = relative.lower()
    if lowered.startswith(("tmp/", ".git/", "__pycache__/", "references/fulltext/")):
        return True
    if path.name.startswith(".env"):
        return True
    return any(lowered.endswith(suffix) for suffix in RUNTIME_SUFFIXES)


def _is_derived_report(relative: str, path: Path) -> bool:
    if path.name in DERIVED_NAMES:
        return True
    return relative.startswith(
        (
            "citation_audit/",
            "quality/",
            "quality_checks/",
            "integrity/",
            "result_validity/",
            "result_support/",
            "core_evidence/",
            "writing/section_packets/",
            "writing/section_validation/",
            "writing/scientific_editor/",
            "writing/claim_bindings/",
        )
    )


def _classify_asset(relative: str, path: Path) -> dict[str, Any]:
    lowered = relative.lower()
    if relative in STATE_FILENAMES or lowered.startswith("lineage/"):
        return {
            "asset_class": "project_state",
            "import_mode": "exclude",
            "target_path": None,
            "requires_revalidation": True,
            "activation_policy": "never_import_parent_state",
            "privacy_class": "project_local",
        }
    if _is_runtime_private(relative, path):
        return {
            "asset_class": "runtime_private",
            "import_mode": "exclude",
            "target_path": None,
            "requires_revalidation": True,
            "activation_policy": "reauthorize_or_rebuild",
            "privacy_class": "private",
        }
    if _is_derived_report(relative, path):
        return {
            "asset_class": "legacy_report",
            "import_mode": "legacy_report",
            "target_path": f"lineage/legacy_reports/{relative}",
            "requires_revalidation": True,
            "activation_policy": "baseline_only_never_active",
            "privacy_class": "project_local",
        }
    if lowered.startswith(("results/figures/", "results/tables/", "latex/sections/")) or lowered in {
        "latex/main.pdf",
        "latex/main.tex",
    }:
        return {
            "asset_class": "lineage_baseline",
            "import_mode": "baseline_only",
            "target_path": f"lineage/baseline_assets/{relative}",
            "requires_revalidation": True,
            "activation_policy": "explicit_revalidation_required",
            "privacy_class": "project_local",
        }
    if lowered.startswith(("data/raw/", "observations/")):
        return {
            "asset_class": "scientific_source",
            "import_mode": "read_only_reference",
            "target_path": None,
            "requires_revalidation": True,
            "activation_policy": "validate_locator_before_use",
            "privacy_class": "private",
        }
    if lowered.startswith(("data/scripts/", "methods/src/", "methods/scripts/", "methods/tests/", "code/")):
        return {
            "asset_class": "candidate_code",
            "import_mode": "copy",
            "target_path": f"lineage/imported_code/{relative}",
            "requires_revalidation": True,
            "activation_policy": "audit_then_bind_or_promote",
            "privacy_class": "project_local",
        }
    if lowered.startswith(
        (
            "idea/",
            "references/",
            "data/processed/",
            "journal_profile/",
            "latex/template/",
        )
    ):
        mode = "read_only_reference" if path.stat().st_size > MAX_COPY_BYTES else "copy"
        return {
            "asset_class": "imported_source",
            "import_mode": mode,
            "target_path": None if mode == "read_only_reference" else f"lineage/imported_sources/{relative}",
            "requires_revalidation": relative != "idea/idea.md",
            "activation_policy": "rebuild_or_validate_before_active_use",
            "privacy_class": "project_local",
        }
    return {
        "asset_class": "unclassified",
        "import_mode": "exclude",
        "target_path": None,
        "requires_revalidation": True,
        "activation_policy": "manual_classification_required",
        "privacy_class": "project_local",
    }


def _snapshot_id(project_path: Path) -> str | None:
    for relative in (
        "results/promoted_evidence_snapshot.json",
        "core_evidence/evidence_snapshot.json",
    ):
        payload = read_mapping(project_path / relative)
        if payload:
            value = payload.get("snapshot_id") or payload.get("evidence_snapshot_id")
            if value:
                return str(value)
    return None


def _next_version_target(source: Path, version: str, destination_root: Path) -> Path:
    if not VERSION_PATTERN.fullmatch(version):
        raise ProjectVersioningError("Version label must use v<number>, for example v1.")
    return destination_root / f"{source.name}_{version}"


def plan_project_version(
    project: str | Path,
    *,
    version: str = "v1",
    destination_root: str | Path | None = None,
    change_request: str | Path | None = None,
    output: str | Path | None = None,
) -> dict[str, Any]:
    """Inspect a source project and return a read-only selective import plan."""
    state = load_project(project)
    source = state.path
    destination = Path(destination_root).expanduser().resolve() if destination_root else source.parent
    target = _next_version_target(source, version, destination)
    source_json = source / "project.json"

    assets: list[dict[str, Any]] = []
    for path in sorted(source.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = _safe_relative(source, path)
        classification = _classify_asset(relative, path)
        digest = _sha256(path)
        asset_id = hashlib.sha256(f"{relative}:{digest}".encode("utf-8")).hexdigest()[:20]
        assets.append(
            {
                "asset_id": asset_id,
                "source_path": relative,
                "source_sha256": digest,
                "size_bytes": path.stat().st_size,
                "owner_stage": _owner_stage(relative),
                **classification,
            }
        )

    change_record: dict[str, Any] | None = None
    if change_request:
        request_path = Path(change_request).expanduser().resolve()
        if not request_path.is_file():
            raise ProjectVersioningError(f"Change request does not exist: {request_path}")
        change_record = {
            "filename": request_path.name,
            "sha256": _sha256(request_path),
            "size_bytes": request_path.stat().st_size,
        }

    source_fingerprint = _json_hash(
        [{"path": item["source_path"], "sha256": item["source_sha256"]} for item in assets]
    )
    plan_core = {
        "source_project_id": state.metadata.get("project_id"),
        "source_project_slug": state.metadata.get("project_slug"),
        "source_project_path": str(source),
        "source_project_json_sha256": _sha256(source_json),
        "source_snapshot_id": _snapshot_id(source),
        "source_fingerprint": source_fingerprint,
        "version_label": version,
        "target_project_path": str(target),
        "target_directory_name": target.name,
        "target_project_id": f"{state.metadata.get('project_id')}-{version}-{source_fingerprint[:8]}",
        "idea": state.metadata.get("idea") or state.metadata.get("title"),
        "field": state.metadata.get("field") or "interdisciplinary research",
        "target_journal": state.metadata.get("target_journal") or "General Academic Journal",
        "change_request": change_record,
        "assets": assets,
    }
    plan_id = _json_hash(plan_core)[:20]
    result = {
        "schema_version": "dpl.asset_import_plan.v1",
        "status": "ready" if not target.exists() else "target_exists",
        "generated_at": utc_now(),
        "plan_id": plan_id,
        "old_project_mutated": False,
        **plan_core,
        "summary": {
            "asset_count": len(assets),
            "copy_count": sum(item["import_mode"] == "copy" for item in assets),
            "locator_count": sum(item["import_mode"] == "read_only_reference" for item in assets),
            "baseline_count": sum(item["import_mode"] == "baseline_only" for item in assets),
            "legacy_report_count": sum(item["import_mode"] == "legacy_report" for item in assets),
            "excluded_count": sum(item["import_mode"] == "exclude" for item in assets),
        },
    }
    if output:
        output_path = Path(output).expanduser().resolve()
        try:
            output_path.relative_to(source)
        except ValueError:
            pass
        else:
            raise ProjectVersioningError("The project-version plan cannot be written inside the read-only source project.")
        atomic_write_json(output_path, result)
        result["saved_plan_path"] = str(output_path)
    return result


def _load_plan(plan: str | Path) -> tuple[Path, dict[str, Any]]:
    path = Path(plan).expanduser().resolve()
    payload = read_mapping(path)
    if payload.get("schema_version") != "dpl.asset_import_plan.v1":
        raise ProjectVersioningError("Project version plan has an unsupported schema.")
    if not payload.get("plan_id") or not payload.get("source_project_path") or not payload.get("target_project_path"):
        raise ProjectVersioningError("Project version plan is missing required identifiers.")
    return path, payload


def _verify_source_project(plan: dict[str, Any]) -> Path:
    source = Path(str(plan["source_project_path"])).expanduser().resolve()
    if not (source / "project.json").is_file():
        raise ProjectVersioningError(f"Source project no longer exists: {source}")
    if _sha256(source / "project.json") != str(plan.get("source_project_json_sha256") or ""):
        raise ProjectVersioningError("Source project.json changed after the version plan was created.")
    planned_assets = {
        str(item.get("source_path") or ""): str(item.get("source_sha256") or "")
        for item in (plan.get("assets") or [])
        if isinstance(item, dict) and item.get("source_path")
    }
    current_paths = {
        _safe_relative(source, path): _sha256(path)
        for path in sorted(source.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }
    if current_paths != planned_assets:
        raise ProjectVersioningError("Source project assets changed after the version plan was created.")
    return source


def create_project_version_from_plan(plan: str | Path) -> dict[str, Any]:
    """Create a clean child scaffold without copying parent state or artifacts."""
    plan_path, payload = _load_plan(plan)
    source = _verify_source_project(payload)
    target = Path(str(payload["target_project_path"])).expanduser().resolve()
    if target.exists():
        raise ProjectVersioningError(f"Target project already exists: {target}")
    if target.parent != Path(str(target.parent)).resolve():
        raise ProjectVersioningError("Target project parent could not be resolved safely.")

    lineage_summary = {
        "parent_project_id": payload.get("source_project_id"),
        "parent_snapshot_id": payload.get("source_snapshot_id"),
        "version_label": payload.get("version_label"),
        "fork_plan_id": payload.get("plan_id"),
        "fork_reason": "change_request" if payload.get("change_request") else "project_version",
    }
    created = create_project(
        root=target.parent,
        idea=str(payload.get("idea") or "Versioned research project"),
        field=str(payload.get("field") or "interdisciplinary research"),
        target_journal=str(payload.get("target_journal") or "General Academic Journal"),
        project_slug_override=target.name,
        project_id_override=str(payload.get("target_project_id")),
        metadata_overrides={"lineage": lineage_summary, "version_label": payload.get("version_label")},
    )
    repo = ArtifactRepository(created.path)
    lineage = {
        "schema_version": "dpl.project_lineage.v1",
        "project_id": created.project_id,
        "display_name": target.name,
        "parent_project_id": payload.get("source_project_id"),
        "parent_project_path": str(source),
        "parent_snapshot_id": payload.get("source_snapshot_id"),
        "version_label": payload.get("version_label"),
        "fork_reason": lineage_summary["fork_reason"],
        "fork_plan_id": payload.get("plan_id"),
        "created_at": utc_now(),
        "created_from_sha256_manifest": IMPORT_PLAN_PATH,
        "source_project_json_sha256": payload.get("source_project_json_sha256"),
        "source_fingerprint": payload.get("source_fingerprint"),
        "old_project_mutated": False,
        "import_status": "pending",
    }
    repo.write_json(LINEAGE_PATH, lineage)
    repo.write_json(IMPORT_PLAN_PATH, payload)
    repo.write_json(
        IMPORT_LEDGER_PATH,
        {
            "schema_version": "dpl.asset_import_ledger.v1",
            "project_id": created.project_id,
            "plan_id": payload.get("plan_id"),
            "status": "pending",
            "events": [],
        },
    )
    refresh_project_passport(created.path, event="project_version_created")
    return {
        "status": "created",
        "project_path": str(created.path),
        "project_id": created.project_id,
        "parent_project_path": str(source),
        "parent_project_id": payload.get("source_project_id"),
        "version_label": payload.get("version_label"),
        "lineage": LINEAGE_PATH,
        "import_plan": IMPORT_PLAN_PATH,
        "source_project_mutated": False,
        "source_plan_path": str(plan_path),
    }


def _target_for_asset(project_root: Path, item: dict[str, Any]) -> Path | None:
    relative = item.get("target_path")
    if not relative:
        return None
    target = (project_root / str(relative)).resolve()
    try:
        target.relative_to(project_root.resolve())
    except ValueError as exc:
        raise ProjectVersioningError(f"Import target escapes child project: {relative}") from exc
    return target


def import_version_assets(project: str | Path, plan: str | Path) -> dict[str, Any]:
    """Import only allowlisted parent assets into lineage-owned child locations."""
    state = load_project(project)
    _, payload = _load_plan(plan)
    source = _verify_source_project(payload)
    lineage = read_mapping(state.path / LINEAGE_PATH)
    if lineage.get("fork_plan_id") != payload.get("plan_id"):
        raise ProjectVersioningError("Import plan does not match the child project's lineage.")
    if lineage.get("parent_project_id") != payload.get("source_project_id"):
        raise ProjectVersioningError("Import plan parent does not match the child project.")

    events: list[dict[str, Any]] = []
    for item in payload.get("assets") or []:
        if not isinstance(item, dict):
            continue
        relative = str(item.get("source_path") or "")
        mode = str(item.get("import_mode") or "exclude")
        source_path = (source / relative).resolve()
        if mode == "exclude":
            events.append({"asset_id": item.get("asset_id"), "source_path": relative, "state": "excluded"})
            continue
        try:
            source_path.relative_to(source)
        except ValueError as exc:
            raise ProjectVersioningError(f"Import source escapes parent project: {relative}") from exc
        if not source_path.is_file():
            raise ProjectVersioningError(f"Planned source asset is missing: {relative}")
        current_hash = _sha256(source_path)
        if current_hash != item.get("source_sha256"):
            raise ProjectVersioningError(f"Planned source asset changed before import: {relative}")

        if mode == "read_only_reference":
            locator = {
                "schema_version": "dpl.read_only_asset_locator.v1",
                "asset_id": item.get("asset_id"),
                "source_project_id": payload.get("source_project_id"),
                "source_snapshot_id": payload.get("source_snapshot_id"),
                "source_path": str(source_path),
                "source_relative_path": relative,
                "sha256": current_hash,
                "size_bytes": item.get("size_bytes"),
                "read_only": True,
                "requires_revalidation": True,
                "activation_state": "imported",
            }
            locator_path = f"{LOCATOR_ROOT}/{item.get('asset_id')}.json"
            ArtifactRepository(state.path).write_json(locator_path, locator)
            events.append(
                {
                    "asset_id": item.get("asset_id"),
                    "source_path": relative,
                    "target_path": locator_path,
                    "state": "imported",
                    "import_mode": mode,
                    "sha256": current_hash,
                }
            )
            continue

        target = _target_for_asset(state.path, item)
        if target is None:
            raise ProjectVersioningError(f"Import mode {mode} requires a target path: {relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target)
        if _sha256(target) != current_hash:
            raise ProjectVersioningError(f"Imported asset hash mismatch: {relative}")
        events.append(
            {
                "asset_id": item.get("asset_id"),
                "source_path": relative,
                "target_path": target.relative_to(state.path).as_posix(),
                "state": "baseline_only" if mode in {"baseline_only", "legacy_report"} else "imported",
                "import_mode": mode,
                "sha256": current_hash,
                "requires_revalidation": bool(item.get("requires_revalidation", True)),
            }
        )

    ledger = {
        "schema_version": "dpl.asset_import_ledger.v1",
        "project_id": state.metadata.get("project_id"),
        "plan_id": payload.get("plan_id"),
        "source_project_id": payload.get("source_project_id"),
        "source_fingerprint": payload.get("source_fingerprint"),
        "status": "imported",
        "imported_at": utc_now(),
        "events": events,
        "summary": {
            "imported": sum(event.get("state") == "imported" for event in events),
            "baseline_only": sum(event.get("state") == "baseline_only" for event in events),
            "excluded": sum(event.get("state") == "excluded" for event in events),
        },
    }
    repo = ArtifactRepository(state.path)
    repo.write_json(IMPORT_LEDGER_PATH, ledger)
    lineage["import_status"] = "imported"
    lineage["imported_at"] = ledger["imported_at"]
    repo.write_json(LINEAGE_PATH, lineage)
    refresh_project_passport(state.path, event="project_version_assets_imported")
    return {
        "status": "imported",
        "project_path": str(state.path),
        "source_project_path": str(source),
        "source_project_mutated": False,
        "ledger": IMPORT_LEDGER_PATH,
        **ledger["summary"],
    }


def validate_project_version(project: str | Path) -> dict[str, Any]:
    """Validate lineage isolation, project identity, and imported asset hashes."""
    state = load_project(project)
    issues: list[dict[str, str]] = []
    base = validate_project(state.path)
    if base.get("status") != "passed":
        issues.extend(base.get("issues") or [])
    lineage = read_mapping(state.path / LINEAGE_PATH)
    plan = read_mapping(state.path / IMPORT_PLAN_PATH)
    ledger = read_mapping(state.path / IMPORT_LEDGER_PATH)
    system = read_mapping(state.path / "project_system_of_record.json")
    passport = load_project_passport(state.path)

    if lineage.get("project_id") != state.metadata.get("project_id"):
        issues.append({"severity": "error", "code": "lineage_project_id_mismatch", "message": "Lineage project ID differs from project.json."})
    if lineage.get("parent_project_id") == state.metadata.get("project_id"):
        issues.append({"severity": "error", "code": "child_reuses_parent_project_id", "message": "Child project must have an independent project ID."})
    if plan.get("plan_id") != lineage.get("fork_plan_id"):
        issues.append({"severity": "error", "code": "lineage_plan_mismatch", "message": "Stored import plan differs from lineage."})
    if passport.get("project_id") != state.metadata.get("project_id"):
        issues.append({"severity": "error", "code": "passport_project_id_mismatch", "message": "Passport belongs to another project."})
    if not system.get("categories"):
        issues.append({"severity": "error", "code": "system_of_record_missing", "message": "Project system of record is missing or invalid."})

    forbidden_active = [
        "results/figure_metadata.json",
        "results/plugin_sufficiency_report.json",
        "results/project_local_capability_audit.json",
        "results/promoted_evidence_snapshot.json",
    ]
    for relative in forbidden_active:
        if (state.path / relative).exists():
            issues.append({"severity": "error", "code": "legacy_active_artifact_present", "message": f"Legacy artifact is active in child project: {relative}"})

    for event in ledger.get("events") or []:
        if not isinstance(event, dict) or event.get("state") == "excluded":
            continue
        target_relative = str(event.get("target_path") or "")
        target = (state.path / target_relative).resolve()
        try:
            target.relative_to(state.path)
        except ValueError:
            issues.append({"severity": "error", "code": "import_target_escape", "message": target_relative})
            continue
        if not target.is_file():
            issues.append({"severity": "error", "code": "import_target_missing", "message": target_relative})
            continue
        if event.get("import_mode") != "read_only_reference" and _sha256(target) != event.get("sha256"):
            issues.append({"severity": "error", "code": "import_hash_mismatch", "message": target_relative})

    stage_violations = [
        stage
        for stage, meta in (state.metadata.get("stages") or {}).items()
        if stage != "idea" and (meta.get("status") != "pending" or meta.get("stale"))
    ]
    if stage_violations:
        issues.append(
            {
                "severity": "error",
                "code": "child_inherited_stage_state",
                "message": "Child project contains non-initial downstream stages: " + ", ".join(stage_violations),
            }
        )
    errors = [item for item in issues if item.get("severity") == "error"]
    return {
        "status": "passed" if not errors else "failed",
        "project_path": str(state.path),
        "project_id": state.metadata.get("project_id"),
        "parent_project_id": lineage.get("parent_project_id"),
        "version_label": lineage.get("version_label"),
        "import_status": lineage.get("import_status"),
        "error_count": len(errors),
        "warning_count": sum(item.get("severity") == "warning" for item in issues),
        "issues": issues,
    }
