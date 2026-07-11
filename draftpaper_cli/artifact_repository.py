"""Single containment-safe repository for structured project artifacts."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .state_kernel import append_jsonl_locked, atomic_write_json, atomic_write_text
from .structured_io import read_mapping


class ArtifactRepositoryError(RuntimeError):
    pass


class ArtifactRepository:
    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()

    def resolve(self, relative: str | Path) -> Path:
        target = (self.root / relative).resolve()
        try:
            target.relative_to(self.root)
        except ValueError as exc:
            raise ArtifactRepositoryError(f"Artifact path escapes project root: {relative}") from exc
        return target

    def read_mapping(self, relative: str | Path) -> dict[str, Any]:
        return read_mapping(self.resolve(relative))

    def read_text(self, relative: str | Path, default: str = "") -> str:
        target = self.resolve(relative)
        if not target.exists():
            return default
        return target.read_text(encoding="utf-8-sig", errors="replace")

    def write_json(self, relative: str | Path, payload: dict[str, Any]) -> Path:
        target = self.resolve(relative)
        atomic_write_json(target, payload)
        return target

    def write_text(self, relative: str | Path, text: str) -> Path:
        target = self.resolve(relative)
        atomic_write_text(target, text)
        return target

    def append_event(self, relative: str | Path, payload: dict[str, Any]) -> Path:
        target = self.resolve(relative)
        append_jsonl_locked(target, payload)
        return target

    def sha256(self, relative: str | Path) -> str:
        target = self.resolve(relative)
        return hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() else ""
