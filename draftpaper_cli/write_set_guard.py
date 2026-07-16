"""Project/repository confinement and post-command write-set attribution."""

from __future__ import annotations

import fnmatch
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .command_registry import CommandSpec
from .state_kernel import atomic_write_bytes


class BoundaryViolation(RuntimeError):
    """Raised when a path or actual command write escapes its declared boundary."""


def _looks_unsafe_absolute(raw: str) -> bool:
    normalized = raw.replace("/", "\\")
    return normalized.startswith(("\\\\", "\\?\\", "\\.\\"))


def _is_reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        attributes = int(getattr(path.lstat(), "st_file_attributes", 0))
    except OSError:
        return False
    return bool(attributes & int(getattr(os, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)))


def resolve_confined_path(root: str | Path, candidate: str | Path, *, must_exist: bool = False) -> Path:
    root_path = Path(root).expanduser().resolve(strict=True)
    raw = str(candidate)
    if _looks_unsafe_absolute(raw) or any(part == ".." for part in Path(raw).parts):
        raise BoundaryViolation(f"Unsafe path syntax is not allowed: {raw}")
    value = Path(candidate).expanduser()
    target = (value if value.is_absolute() else root_path / value).resolve(strict=must_exist)
    try:
        relative = target.relative_to(root_path)
    except ValueError as exc:
        raise BoundaryViolation(f"Path escapes the allowed root: {raw}") from exc
    cursor = root_path
    for part in relative.parts:
        cursor = cursor / part
        if cursor.exists() and _is_reparse(cursor):
            raise BoundaryViolation(f"Symlink or reparse-point traversal is not allowed: {cursor}")
    return target


@dataclass(frozen=True)
class FileStamp:
    size: int
    mtime_ns: int
    sha256: str | None


def _stamp(path: Path) -> FileStamp:
    stat = path.stat()
    digest = hashlib.sha256(path.read_bytes()).hexdigest() if stat.st_size <= 2 * 1024 * 1024 else None
    return FileStamp(size=stat.st_size, mtime_ns=stat.st_mtime_ns, sha256=digest)


def snapshot_tree(root: Path) -> dict[str, FileStamp]:
    rows: dict[str, FileStamp] = {}
    for path in root.rglob("*"):
        if not path.is_file() or _is_reparse(path):
            continue
        relative = path.relative_to(root).as_posix()
        rows[relative] = _stamp(path)
    return rows


def _matches(path: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) or fnmatch.fnmatchcase(path, pattern.replace("/**", "/*")) for pattern in patterns)


class WriteSetGuard:
    """Capture a project baseline and attribute only writes from one command."""

    def __init__(self, project: str | Path, spec: CommandSpec) -> None:
        self.root = resolve_confined_path(Path(project).expanduser().resolve(), ".", must_exist=True)
        self.spec = spec
        self.baseline = snapshot_tree(self.root)
        self.rollback_content = {
            relative: (self.root / relative).read_bytes()
            for relative, stamp in self.baseline.items()
            if stamp.size <= 8 * 1024 * 1024
        }

    def assess(self) -> dict[str, Any]:
        current = snapshot_tree(self.root)
        created = sorted(set(current) - set(self.baseline))
        deleted = sorted(set(self.baseline) - set(current))
        modified = sorted(path for path in set(current) & set(self.baseline) if current[path] != self.baseline[path])
        changed = sorted(set(created + deleted + modified))
        forbidden = sorted(path for path in changed if _matches(path, self.spec.forbidden_globs))
        outside = sorted(path for path in changed if not _matches(path, self.spec.allowed_write_globs))
        violations = sorted(set(forbidden + outside))
        return {
            "schema_version": "dpl.write_set_assessment.v1",
            "command": self.spec.name,
            "status": "boundary_violation" if violations else "passed",
            "created": created,
            "modified": modified,
            "deleted": deleted,
            "actual_write_set": changed,
            "allowed_write_globs": list(self.spec.allowed_write_globs),
            "forbidden_globs": list(self.spec.forbidden_globs),
            "violations": violations,
        }

    def rollback_violations(self, assessment: dict[str, Any] | None = None) -> dict[str, Any]:
        """Remove or restore project-local writes outside the command contract."""
        report = assessment or self.assess()
        violations = set(str(path) for path in report.get("violations") or [])
        restored: list[str] = []
        removed: list[str] = []
        unrecoverable: list[str] = []
        for relative in sorted(violations):
            path = self.root / relative
            if relative in set(report.get("created") or []):
                if path.is_file() and not path.is_symlink():
                    path.unlink()
                removed.append(relative)
                continue
            content = self.rollback_content.get(relative)
            if content is None:
                unrecoverable.append(relative)
                continue
            atomic_write_bytes(path, content)
            restored.append(relative)
        return {
            "status": "rolled_back" if not unrecoverable else "rollback_incomplete",
            "restored": restored,
            "removed": removed,
            "unrecoverable": unrecoverable,
        }
