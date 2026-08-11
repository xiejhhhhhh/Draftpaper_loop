"""Runtime/source/wheel/skill handshake used before high-risk project work."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

from .plugin_catalog import catalog_hash
from .project_scaffold import _write_json, utc_now
from .schema_registry import load_schema_registry
from .skill_sync import canonical_contract, canonical_skill_hash


RUNTIME_LOCK = ".draftpaper/runtime_lock.json"
RUNTIME_PREFLIGHT = ".draftpaper/runtime_preflight.json"
SCHEMA_VERSION = "dpl.runtime_lock.v1"
IDENTITY_FIELDS = (
    "source_commit",
    "distribution_version",
    "python_version",
    "command_registry_sha256",
    "schema_registry_sha256",
    "skill_sha256",
    "skill_copy_parity",
    "plugin_catalog_hash",
)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str | None:
    try:
        return _sha256_bytes(path.read_bytes())
    except OSError:
        return None


def _git_root() -> Path:
    package_root = Path(__file__).resolve().parent
    try:
        completed = subprocess.run(
            ["git", "-C", str(package_root), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError:
        return package_root.parent
    if completed.returncode == 0 and completed.stdout.strip():
        return Path(completed.stdout.strip()).resolve()
    return package_root.parent


def _git_commit(root: Path) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError:
        return None
    return completed.stdout.strip() or None if completed.returncode == 0 else None


def _resource_hash(relative: str) -> str | None:
    path = Path(__file__).resolve().parent / relative
    return _sha256_file(path)


def _skill_copy_parity(root: Path) -> str:
    canonical = Path(__file__).resolve().parent / "resources" / "draftpaper_workflow" / "SKILL.md"
    if not canonical.is_file():
        return "not_applicable"
    targets = (
        root / "codex_skills" / "draftpaper-workflow" / "SKILL.md",
        root / ".claude" / "skills" / "draftpaper-workflow" / "SKILL.md",
        root / "tools" / "claude_code_payload" / "dot_claude" / "skills" / "draftpaper-workflow" / "SKILL.md",
    )
    if not all(path.is_file() for path in targets):
        return "missing_copy"
    expected = _sha256_file(canonical)
    return "passed" if all(_sha256_file(path) == expected for path in targets) else "mismatch"


def _registry_hash() -> str | None:
    try:
        payload = load_schema_registry()
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    return _sha256_bytes(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def runtime_identity() -> dict[str, Any]:
    """Return stable identity fields for the current installed/runtime source."""
    root = _git_root()
    try:
        distribution_version = importlib.metadata.version("draftpaper-cli")
    except importlib.metadata.PackageNotFoundError:
        distribution_version = "editable-or-uninstalled"
    try:
        command_registry_hash = _sha256_file(Path(__file__).with_name("command_registry.py"))
    except OSError:
        command_registry_hash = None
    return {
        "schema_version": SCHEMA_VERSION,
        "observed_at": utc_now(),
        "source_root": str(root),
        "source_commit": _git_commit(root),
        "distribution_version": distribution_version,
        "python_version": platform.python_version(),
        "python_executable": str(Path(sys.executable).resolve()),
        "platform": platform.platform(),
        "command_registry_sha256": command_registry_hash,
        "schema_registry_sha256": _registry_hash(),
        "skill_sha256": canonical_skill_hash(),
        "skill_version": str(canonical_contract().get("skill_version") or ""),
        "skill_copy_parity": _skill_copy_parity(root),
        "plugin_catalog_hash": catalog_hash(),
    }


def _identity_view(payload: dict[str, Any]) -> dict[str, Any]:
    return {field: payload.get(field) for field in IDENTITY_FIELDS}


def _mismatches(previous: dict[str, Any], current: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"field": field, "previous": previous.get(field), "current": current.get(field)}
        for field in IDENTITY_FIELDS
        if previous.get(field) != current.get(field)
    ]


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def session_preflight(
    project: str | Path,
    *,
    write: bool = True,
    accept_runtime_update: bool = False,
) -> dict[str, Any]:
    """Compare the active project lock with the current runtime.

    A first invocation initializes the lock. A mismatch never overwrites the
    previous lock; this preserves the evidence needed to explain the drift.
    """
    root = Path(project).expanduser().resolve()
    lock_path = root / RUNTIME_LOCK
    report_path = root / RUNTIME_PREFLIGHT
    current = runtime_identity()
    previous = _read_json(lock_path)
    mismatches = _mismatches(previous, current) if previous else []
    migration_receipt: str | None = None
    if not previous:
        status = "initialized"
        reason = "runtime_lock_created"
    elif mismatches:
        if accept_runtime_update and write:
            migration_root = root / ".draftpaper" / "runtime_migrations"
            migration_root.mkdir(parents=True, exist_ok=True)
            migration_receipt_path = migration_root / f"runtime-{_sha256_bytes(json.dumps(current, sort_keys=True).encode('utf-8'))[:12]}.json"
            migration_receipt = str(migration_receipt_path)
            _write_json(
                migration_receipt_path,
                {
                    "schema_version": "dpl.runtime_migration_receipt.v1",
                    "project_path": str(root),
                    "previous_identity": _identity_view(previous),
                    "current_identity": _identity_view(current),
                    "mismatches": mismatches,
                    "reason": "explicit_runtime_update",
                    "created_at": utc_now(),
                },
            )
            status = "updated"
            reason = "runtime_identity_updated"
        else:
            status = "blocked"
            reason = "runtime_identity_mismatch"
    else:
        status = "passed"
        reason = "runtime_identity_matches"
    report = {
        "schema_version": "dpl.runtime_preflight.v1",
        "status": status,
        "reason": reason,
        "project_path": str(root),
        "lock_path": str(lock_path),
        "report_path": str(report_path),
        "previous_identity": _identity_view(previous) if previous else None,
        "current_identity": _identity_view(current),
        "mismatches": mismatches,
        "next_command": (
            None
            if status in {"initialized", "passed", "updated"}
            else f'draftpaper session-preflight --project "{root}" --accept-runtime-update'
        ),
        "migration_receipt": migration_receipt,
    }
    if write:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(report_path, report)
        if status in {"initialized", "passed", "updated"}:
            lock = {**current, "last_verified_at": utc_now()}
            if migration_receipt:
                lock["last_migration_receipt"] = migration_receipt
            _write_json(lock_path, lock)
    return report


def check_runtime_for_command(project: str | Path, command: str) -> dict[str, Any]:
    """Return a non-mutating guard result for a command transaction."""
    root = Path(project).expanduser().resolve()
    lock = _read_json(root / RUNTIME_LOCK)
    if not lock:
        return {
            "status": "uninitialized",
            "command": command,
            "reason": "runtime_lock_missing",
            "next_command": f'draftpaper session-preflight --project "{root}"',
        }
    current = runtime_identity()
    mismatches = _mismatches(lock, current)
    return {
        "status": "blocked" if mismatches else "passed",
        "command": command,
        "reason": "runtime_identity_mismatch" if mismatches else "runtime_identity_matches",
        "mismatches": mismatches,
        "next_command": f'draftpaper session-preflight --project "{root}"' if mismatches else None,
    }
