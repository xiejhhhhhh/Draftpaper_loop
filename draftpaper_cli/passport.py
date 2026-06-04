from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PASSPORT_FILES = {
    "passport": "project_passport.yaml",
    "artifact_ledger": "artifact_ledger.jsonl",
    "checkpoint_ledger": "checkpoint_ledger.jsonl",
    "integrity_ledger": "integrity_ledger.jsonl",
}

ROOT_ARTIFACTS = [
    "project.json",
    "project.yaml",
    "idea/idea.md",
]


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
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        (path.read_text(encoding="utf-8") if path.exists() else "")
        + json.dumps(payload, ensure_ascii=False, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )


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


def collect_artifacts(project: str | Path) -> list[dict[str, Any]]:
    """Collect current project artifacts with stable hashes."""
    project_path = project_root(project)
    metadata = _metadata(project_path)
    candidates = list(ROOT_ARTIFACTS)
    candidates.extend(_stage_manifest_outputs(project_path, metadata))
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
        artifacts.append({
            "artifact_id": hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16],
            "stage": _stage_from_relative(normalized),
            "path": normalized,
            "sha256": _sha256(path),
            "size_bytes": path.stat().st_size,
            "updated_at": utc_now(),
        })
    artifacts.sort(key=lambda item: item["path"])
    return artifacts


def _latest_unconsumed_checkpoint(project_path: Path) -> dict[str, Any] | None:
    events = read_jsonl(project_path / PASSPORT_FILES["checkpoint_ledger"])
    consumed = {str(event.get("consumes_hash")) for event in events if event.get("kind") == "resume"}
    for event in reversed(events):
        if event.get("kind") == "checkpoint" and str(event.get("hash")) not in consumed:
            return event
    return None


def _write_passport(project_path: Path, *, event: str) -> dict[str, Any]:
    metadata = _metadata(project_path)
    for relative in PASSPORT_FILES.values():
        path = project_path / relative
        if not path.exists():
            path.write_text("", encoding="utf-8")
    artifacts = collect_artifacts(project_path)
    awaiting = _latest_unconsumed_checkpoint(project_path)
    passport = {
        "schema_version": 1,
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
    """Refresh passport snapshot and append artifact entries for current files."""
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
            "event": event,
            "recorded_at": now,
            **artifact,
        })
    return _write_passport(project_path, event=event)


def load_project_passport(project: str | Path) -> dict[str, Any]:
    """Load passport, initializing it for older projects when needed."""
    project_path = project_root(project)
    passport_path = project_path / PASSPORT_FILES["passport"]
    if not passport_path.exists() or not passport_path.read_text(encoding="utf-8").strip():
        return initialize_project_passport(project_path)
    payload = _read_json(passport_path, {})
    if not isinstance(payload, dict):
        raise PassportError(f"{passport_path} must contain an object.")
    return payload


def append_checkpoint_event(project: str | Path, event: dict[str, Any]) -> None:
    project_path = project_root(project)
    _append_jsonl(project_path / PASSPORT_FILES["checkpoint_ledger"], event)
    _write_passport(project_path, event=str(event.get("kind") or "checkpoint"))


def append_integrity_event(project: str | Path, event: dict[str, Any]) -> None:
    project_path = project_root(project)
    _append_jsonl(project_path / PASSPORT_FILES["integrity_ledger"], event)
    _write_passport(project_path, event=str(event.get("kind") or "integrity"))
