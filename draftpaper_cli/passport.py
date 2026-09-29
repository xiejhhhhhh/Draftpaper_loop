# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .artifact_identity import canonical_json, compute_artifact_identity
from .provenance import DPL_SCHEMAS, dpl_block, generated_by_block
from .state_kernel import append_jsonl_locked, atomic_write_json


PASSPORT_FILES = {
    "passport": "project_passport.yaml",
    "artifact_ledger": "artifact_ledger.jsonl",
    "checkpoint_ledger": "checkpoint_ledger.jsonl",
    "integrity_ledger": "integrity_ledger.jsonl",
    "transaction_ledger": "transaction_ledger.jsonl",
    "token_ledger": "token_ledger.jsonl",
}

ROOT_ARTIFACTS = [
    "project.json",
    "project.yaml",
    "idea/idea.md",
    "project_system_of_record.json",
    "project_lineage.json",
    "lineage/asset_import_plan.json",
    "lineage/import_ledger.json",
]

CODE_MANIFEST_ARTIFACTS = [
    "code/stage_code_manifest.json",
    "code/code_ownership_manifest.json",
    "data/data_code_manifest.json",
    "methods/method_code_manifest.json",
    "methods/analysis_code_manifest.json",
    "methods/model_provenance.json",
]

# A project can contain scientific files created directly in an editor, not
# only files named by a stage manifest. Discover those files inside the known
# project work areas so direct edits enter the same drift/reconciliation path
# as managed writes. Large raw data and model assets remain an explicit
# manifest responsibility; hashing them on every status call would make the
# passport a new source of latency.
DIRECT_DISCOVERY_ROOTS = (
    "idea",
    "research_plan",
    "research_feasibility",
    "research_plan_feasibility",
    "references",
    "journal_profile",
    "data",
    "observations",
    "method_plan",
    "method_feasibility",
    "figure_plan",
    "figure_contracts",
    "methods",
    "code",
    "result_validity",
    "result_support",
    "core_evidence",
    "results",
    "writing",
    "data_writing",
    "methods_writing",
    "introduction",
    "discussion",
    "latex",
    "integrity",
    "quality_checks",
)
DIRECT_DISCOVERY_EXTENSIONS = frozenset(
    {
        ".bib",
        ".csv",
        ".css",
        ".html",
        ".ipynb",
        ".jl",
        ".json",
        ".jpeg",
        ".jpg",
        ".md",
        ".parquet",
        ".pdf",
        ".png",
        ".py",
        ".r",
        ".sh",
        ".svg",
        ".tex",
        ".toml",
        ".tsv",
        ".txt",
        ".xml",
        ".yaml",
        ".yml",
    }
)
DIRECT_DISCOVERY_EXCLUDED_DIRS = frozenset(
    {
        ".git",
        ".draftpaper",
        "__pycache__",
        "cache",
        "caches",
        "checkpoints",
        "compiled",
        "evidence_snapshots",
        "evidence_binding_receipts",
        "tmp",
        "temporary",
        "revision_reconciliation",
        "evidence_bindings",
        "run_evidence_bundles",
        "blind_reviews",
    }
)
DIRECT_DISCOVERY_EXCLUDED_FILES = frozenset(
    {
        "evidence_snapshot_reopen_report.json",
        "promoted_evidence_snapshot.json",
    }
)
DIRECT_DISCOVERY_EXCLUDED_SUFFIXES = frozenset(
    {
        ".aux",
        ".bbl",
        ".bcf",
        ".blg",
        ".fdb_latexmk",
        ".fls",
        ".log",
        ".out",
        ".run.xml",
        ".synctex.gz",
        ".toc",
    }
)
DIRECT_DISCOVERY_MAX_BYTES = 64 * 1024 * 1024


class PassportError(RuntimeError):
    """Raised when DraftPaper passport or ledger artifacts cannot be read safely."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def project_root(project: str | Path) -> Path:
    path = Path(project).expanduser().resolve()
    if path.is_file() and path.name == "project.json":
        return path.parent
    return path


def _read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise PassportError(f"{path} is not valid JSON-compatible YAML/JSON: {exc}") from exc


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_json(path, payload)


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    append_jsonl_locked(path, payload)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PassportError(f"{path} contains an invalid JSONL entry: {exc}") from exc
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_semantic_fingerprint(path: Path, relative: str) -> dict[str, Any] | None:
    if relative != "references/library.bib":
        return None
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    entries = re.findall(r"@[A-Za-z]+\s*\{\s*([^,\s]+)\s*,(.*?)(?=\n@|\Z)", text, flags=re.S)
    citation_keys: list[str] = []
    work_ids: list[str] = []
    for key, body in entries:
        citation_keys.append(key.strip())
        doi_match = re.search(r"(?im)^\s*doi\s*=\s*[\{\"]([^}\"]+)", body)
        title_match = re.search(r"(?im)^\s*title\s*=\s*[\{\"]([^}\"]+)", body)
        if doi_match:
            doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", doi_match.group(1).strip(), flags=re.I).lower()
            work_ids.append("doi:" + doi)
        elif title_match:
            title = re.sub(r"[^a-z0-9]+", "", title_match.group(1).replace("{", "").replace("}", "").lower())
            work_ids.append("title:" + title)
    key_blob = "\n".join(sorted(set(citation_keys))).encode("utf-8")
    work_blob = "\n".join(sorted(set(work_ids))).encode("utf-8")
    return {
        "kind": "reference_library",
        "citation_key_count": len(set(citation_keys)),
        "work_count": len(set(work_ids)),
        "citation_keys_sha256": hashlib.sha256(key_blob).hexdigest(),
        "work_ids_sha256": hashlib.sha256(work_blob).hexdigest(),
    }


def _metadata(project_path: Path) -> dict[str, Any]:
    metadata = _read_json(project_path / "project.json", {})
    if not isinstance(metadata, dict) or "project_id" not in metadata:
        raise PassportError(f"project.json is missing or invalid under {project_path}")
    return metadata


def _stage_from_relative(relative: str) -> str:
    first = relative.split("/", 1)[0]
    if first == "quality_checks":
        return "quality_checks"
    if first == "project.json" or first == "project.yaml":
        return "project"
    return first


def _stage_manifest_outputs(project_path: Path, metadata: dict[str, Any]) -> list[str]:
    outputs: list[str] = []
    for stage_meta in (metadata.get("stages") or {}).values():
        manifest = str(stage_meta.get("manifest") or "")
        if not manifest:
            continue
        manifest_path = project_path / manifest
        manifest_payload = _read_json(manifest_path, {}) if manifest_path.exists() else {}
        if isinstance(manifest_payload, dict):
            outputs.extend(str(item) for item in (manifest_payload.get("output_files") or []) if str(item).strip())
        outputs.append(manifest)
    return outputs


def _code_manifest_artifacts(project_path: Path) -> list[str]:
    """Collect stage-owned code and declared outputs from code manifests.

    Code is scientific evidence, not an incidental implementation detail. Some
    migrated projects have sparse stage manifests, so relying only on their
    output_files would let method scripts change without passport drift.
    """
    candidates: list[str] = []

    def add(value: Any) -> None:
        text = str(value or "").replace("\\", "/").strip()
        if text and text not in candidates:
            candidates.append(text)

    for relative in CODE_MANIFEST_ARTIFACTS:
        manifest_path = project_path / relative
        if not manifest_path.is_file():
            continue
        add(relative)
        payload = _read_json(manifest_path, {})
        if not isinstance(payload, dict):
            continue
        for key in (
            "canonical_files",
            "formula_source_files",
            "generated_files",
            "compatibility_files",
            "declared_outputs",
            "input_data",
            "output_files",
            "source_files",
            "scripts",
        ):
            values = payload.get(key) or []
            if isinstance(values, str):
                values = [values]
            if isinstance(values, list):
                for item in values:
                    if isinstance(item, dict):
                        for path_key in ("canonical_path", "path", "source_path", "target_path"):
                            if item.get(path_key):
                                add(item[path_key])
                    else:
                        add(item)
        files = payload.get("files") or []
        if isinstance(files, list):
            for item in files:
                if not isinstance(item, dict):
                    add(item)
                    continue
                for path_key in ("canonical_path", "path", "source_path", "target_path"):
                    if item.get(path_key):
                        add(item[path_key])
        for key in ("verify_command_argv", "install_plotting_command_argv"):
            argv = payload.get(key) or []
            if isinstance(argv, list):
                for token in argv:
                    token_text = str(token or "").replace("\\", "/").strip()
                    if token_text and not token_text.startswith("{") and Path(token_text).suffix.lower() in {".py", ".r", ".jl", ".sh"}:
                        add(token_text)
    return candidates


def _direct_workspace_artifacts(
    project_path: Path,
    *,
    declared: set[str],
    include_large: bool = False,
) -> list[str]:
    """Find likely author-edited artifacts without crawling project internals."""

    discovered: list[str] = []
    for root_name in DIRECT_DISCOVERY_ROOTS:
        root = project_path / root_name
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.is_symlink():
                continue
            try:
                relative = path.relative_to(project_path).as_posix()
                size = path.stat().st_size
            except OSError:
                continue
            parts = set(relative.split("/")[:-1])
            if parts & DIRECT_DISCOVERY_EXCLUDED_DIRS:
                continue
            if path.name.startswith((".", "~$")) or path.name.endswith("~"):
                continue
            if path.name.lower() in DIRECT_DISCOVERY_EXCLUDED_FILES:
                continue
            suffix = path.suffix.lower()
            if suffix not in DIRECT_DISCOVERY_EXTENSIONS:
                continue
            if any(relative.lower().endswith(item) for item in DIRECT_DISCOVERY_EXCLUDED_SUFFIXES):
                continue
            if size > DIRECT_DISCOVERY_MAX_BYTES and not include_large:
                # Large data/model assets must be declared in a manifest so
                # passport hashing and provenance can be scheduled explicitly.
                # Governance scope may include them without reading their bytes.
                continue
            if relative not in declared:
                discovered.append(relative)
    return discovered


def collect_artifacts(project: str | Path) -> list[dict[str, Any]]:
    """Collect current project artifacts with stable hashes."""
    project_path = project_root(project)
    metadata = _metadata(project_path)
    candidates = list(ROOT_ARTIFACTS)
    candidates.extend(_stage_manifest_outputs(project_path, metadata))
    candidates.extend(_code_manifest_artifacts(project_path))
    declared = {str(item).replace("\\", "/").strip() for item in candidates if str(item).strip()}
    candidates.extend(_direct_workspace_artifacts(project_path, declared=declared))
    seen: set[str] = set()
    artifacts: list[dict[str, Any]] = []
    for relative in candidates:
        normalized = str(relative).replace("\\", "/").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        path = (project_path / normalized).resolve()
        try:
            path.relative_to(project_path.resolve())
        except ValueError:
            continue
        if not path.is_file():
            continue
        identity = compute_artifact_identity(path, normalized)
        artifact = {
            "artifact_id": hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16],
            "stage": _stage_from_relative(normalized),
            "path": normalized,
            "sha256": identity["byte_sha256"],
            "size_bytes": path.stat().st_size,
            "updated_at": utc_now(),
            **identity,
        }
        artifacts.append(artifact)
    artifacts.sort(key=lambda item: item["path"])
    return artifacts


CHECKPOINT_BATCH_ASSOCIATION_SCHEMA = "dpl.checkpoint_batch_association.v1"


def _valid_checkpoint_batch_association(event: dict[str, Any]) -> bool:
    if event.get("kind") != "checkpoint_batch_associated" or event.get("schema_version") != CHECKPOINT_BATCH_ASSOCIATION_SCHEMA:
        return False
    digest = str(event.get("association_sha256") or "")
    payload = {key: value for key, value in event.items() if key != "association_sha256"}
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        return False
    expected = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    if digest != expected:
        return False
    required_strings = (
        "checkpoint_hash", "checkpoint_package_sha256", "source_cycle_sha256", "batch_id",
        "scope_sha256", "input_manifest_sha256", "candidate_file_sha256", "frozen_candidate_ref",
    )
    if any(not isinstance(event.get(field), str) or not event[field].strip() for field in required_strings):
        return False
    for field in (
        "checkpoint_package_sha256", "source_cycle_sha256", "scope_sha256",
        "input_manifest_sha256", "candidate_file_sha256",
    ):
        if not re.fullmatch(r"[0-9a-f]{64}", str(event[field])):
            return False
    generation = event.get("candidate_generation")
    if not isinstance(generation, int) or generation < 1:
        return False
    reference = Path(str(event.get("frozen_candidate_ref")).replace("\\", "/"))
    if reference.is_absolute() or any(part in {"", ".", ".."} for part in reference.parts) or ":" in str(event.get("frozen_candidate_ref")):
        return False
    return True


def checkpoint_batch_association(project: str | Path, checkpoint_hash: str) -> dict[str, Any] | None:
    """Return one unambiguous, content-sealed legacy-to-batch association."""
    root = project_root(project)
    matches = [
        row for row in read_jsonl(root / PASSPORT_FILES["checkpoint_ledger"])
        if row.get("checkpoint_hash") == checkpoint_hash and _valid_checkpoint_batch_association(row)
    ]
    if not matches:
        return None
    if len({row["association_sha256"] for row in matches}) != 1:
        return None
    return matches[-1]


def overlay_checkpoint_batch_association(project: str | Path, checkpoint: dict[str, Any]) -> dict[str, Any]:
    """Project a verified association onto a legacy checkpoint without rewriting it."""
    result = dict(checkpoint)
    if checkpoint.get("kind") != "checkpoint" or checkpoint.get("stage") != "core_evidence":
        return result
    association = checkpoint_batch_association(project, str(checkpoint.get("hash") or ""))
    if not association:
        return result
    if association.get("checkpoint_package_sha256") != checkpoint.get("stage_summary_sha256"):
        return result
    for key in ("batch_id", "scope_sha256", "input_manifest_sha256", "candidate_generation", "frozen_candidate_ref", "base_decision_receipt_id"):
        original_value = checkpoint.get(key)
        if original_value is not None and original_value != association.get(key):
            return result
    for key in (
        "batch_id", "scope_sha256", "input_manifest_sha256", "candidate_generation",
        "frozen_candidate_ref", "base_decision_receipt_id",
    ):
        result[key] = association.get(key)
    result["legacy_batch_association"] = {
        "association_sha256": association["association_sha256"],
        "source_cycle_sha256": association["source_cycle_sha256"],
        "checkpoint_package_sha256": association["checkpoint_package_sha256"],
    }
    return result


def append_checkpoint_batch_association(project: str | Path, fields: dict[str, Any]) -> dict[str, Any]:
    """Append an idempotent, sealed association and refresh the awaiting projection."""
    root = project_root(project)
    event = {
        "kind": "checkpoint_batch_associated",
        "schema_version": CHECKPOINT_BATCH_ASSOCIATION_SCHEMA,
        **fields,
        "created_at": utc_now(),
    }
    event["association_sha256"] = hashlib.sha256(canonical_json(event).encode("utf-8")).hexdigest()
    if not _valid_checkpoint_batch_association(event):
        raise ValueError("Legacy checkpoint batch association is incomplete or invalid.")
    original = next((
        row for row in reversed(read_jsonl(root / PASSPORT_FILES["checkpoint_ledger"]))
        if row.get("kind") == "checkpoint" and row.get("hash") == event["checkpoint_hash"]
    ), None)
    if not original or original.get("stage") != "core_evidence":
        raise ValueError("Batch association requires an existing core-evidence checkpoint event.")
    if original.get("stage_summary_sha256") != event.get("checkpoint_package_sha256"):
        raise ValueError("Batch association package hash does not match the immutable checkpoint event.")
    for key in ("batch_id", "scope_sha256", "input_manifest_sha256", "candidate_generation", "frozen_candidate_ref", "base_decision_receipt_id"):
        if original.get(key) is not None and original.get(key) != event.get(key):
            raise ValueError("Batch association cannot override a conflicting checkpoint identity.")
    existing = checkpoint_batch_association(root, str(event["checkpoint_hash"]))
    if existing:
        comparable = {key: value for key, value in event.items() if key not in {"created_at", "association_sha256"}}
        prior = {key: value for key, value in existing.items() if key not in {"created_at", "association_sha256"}}
        if comparable != prior:
            raise ValueError("A conflicting legacy checkpoint batch association already exists.")
        _write_passport(root, event="checkpoint_batch_association_recovery")
        return existing
    append_checkpoint_event(root, event)
    return event


def _latest_unconsumed_checkpoint(project_path: Path) -> dict[str, Any] | None:
    events = read_jsonl(project_path / PASSPORT_FILES["checkpoint_ledger"])
    consumed = {str(event.get("consumes_hash")) for event in events if event.get("kind") == "resume"}
    consumed.update(
        str(event.get("supersedes_hash"))
        for event in events
        if event.get("kind") == "checkpoint_superseded"
    )
    for event in reversed(events):
        if event.get("kind") == "checkpoint" and str(event.get("hash")) not in consumed:
            return overlay_checkpoint_batch_association(project_path, event)
    return None


def _build_passport(project_path: Path, *, event: str) -> dict[str, Any]:
    metadata = _metadata(project_path)
    artifacts = collect_artifacts(project_path)
    awaiting = _latest_unconsumed_checkpoint(project_path)
    passport = {
        "schema_version": 1,
        "dpl": dpl_block(
            project_passport_schema=DPL_SCHEMAS["project_passport"],
            artifact_hash_schema=DPL_SCHEMAS["artifact_hash"],
            loop_event_schema=DPL_SCHEMAS["loop_event"],
        ),
        "generated_by": generated_by_block(schema_version=DPL_SCHEMAS["project_passport"]),
        "project_id": metadata.get("project_id"),
        "project_slug": metadata.get("project_slug"),
        "title": metadata.get("title"),
        "generated_at": utc_now(),
        "event": event,
        "current_stage": metadata.get("current_stage"),
        "pipeline_state": "awaiting_confirmation" if awaiting else "ready",
        "awaiting_checkpoint": awaiting,
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "ledgers": dict(PASSPORT_FILES),
    }
    return passport


def _write_passport(project_path: Path, *, event: str) -> dict[str, Any]:
    passport = _build_passport(project_path, event=event)
    _write_json(project_path / PASSPORT_FILES["passport"], passport)
    return passport


def initialize_project_passport(project: str | Path) -> dict[str, Any]:
    """Create the root passport and append an initial artifact snapshot."""
    project_path = project_root(project)
    for relative in PASSPORT_FILES.values():
        path = project_path / relative
        if not path.exists():
            path.write_text("", encoding="utf-8")
    artifacts = collect_artifacts(project_path)
    now = utc_now()
    for artifact in artifacts:
        _append_jsonl(project_path / PASSPORT_FILES["artifact_ledger"], {
            "kind": "artifact",
            "event": "initialize",
            "recorded_at": now,
            **artifact,
        })
    return _write_passport(project_path, event="initialize")


def refresh_project_passport(project: str | Path, *, event: str = "refresh") -> dict[str, Any]:
    """Refresh passport and append only changed, added, or removed artifacts."""
    project_path = project_root(project)
    for relative in PASSPORT_FILES.values():
        path = project_path / relative
        if not path.exists():
            path.write_text("", encoding="utf-8")
    artifacts = collect_artifacts(project_path)
    now = utc_now()
    previous: dict[str, dict[str, Any]] = {}
    for record in read_jsonl(project_path / PASSPORT_FILES["artifact_ledger"]):
        path = str(record.get("path") or "")
        if path:
            previous[path] = record
    current = {str(artifact["path"]): artifact for artifact in artifacts}
    for artifact in artifacts:
        prior = previous.get(str(artifact["path"])) or {}
        if prior.get("sha256") == artifact.get("sha256") and prior.get("kind") != "artifact_removed":
            continue
        _append_jsonl(project_path / PASSPORT_FILES["artifact_ledger"], {
            "kind": "artifact",
            "event": event,
            "recorded_at": now,
            **artifact,
        })
    for path, prior in previous.items():
        if path not in current and prior.get("kind") != "artifact_removed":
            _append_jsonl(project_path / PASSPORT_FILES["artifact_ledger"], {
                "kind": "artifact_removed", "event": event, "recorded_at": now,
                "path": path, "previous_sha256": prior.get("sha256"), "stage": prior.get("stage"),
            })
    return _write_passport(project_path, event=event)


def load_project_passport(project: str | Path) -> dict[str, Any]:
    """Load passport without mutating older projects."""
    project_path = project_root(project)
    passport_path = project_path / PASSPORT_FILES["passport"]
    if not passport_path.exists() or not passport_path.read_text(encoding="utf-8").strip():
        return _build_passport(project_path, event="read_only_snapshot")
    payload = _read_json(passport_path, {})
    if not isinstance(payload, dict):
        raise PassportError(f"{passport_path} must contain an object.")
    return payload


def append_checkpoint_event(project: str | Path, event: dict[str, Any]) -> None:
    project_path = project_root(project)
    _append_jsonl(project_path / PASSPORT_FILES["checkpoint_ledger"], event)
    _write_passport(project_path, event=str(event.get("kind") or "checkpoint"))


def append_integrity_event(project: str | Path, event: dict[str, Any], *, refresh_passport: bool = True) -> None:
    project_path = project_root(project)
    _append_jsonl(project_path / PASSPORT_FILES["integrity_ledger"], event)
    if refresh_passport:
        _write_passport(project_path, event=str(event.get("kind") or "integrity"))
