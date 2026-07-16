"""Rollback-capable transactions for a bounded set of project artifacts."""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Iterable

from .state_kernel import atomic_write_bytes


def _matches(relative: str, patterns: tuple[str, ...]) -> bool:
    return any(
        fnmatch.fnmatchcase(relative, pattern)
        or fnmatch.fnmatchcase(relative, pattern.replace("/**", "/*"))
        for pattern in patterns
    )


class ScopedProjectTransaction:
    """Restore every matching artifact when a bounded operation fails."""

    def __init__(self, project: str | Path, patterns: Iterable[str]) -> None:
        self.root = Path(project).expanduser().resolve(strict=True)
        self.patterns = tuple(dict.fromkeys(str(pattern).replace("\\", "/") for pattern in patterns))
        self._baseline = self._snapshot()
        self._committed = False

    def _snapshot(self) -> dict[str, bytes]:
        snapshot: dict[str, bytes] = {}
        for path in self.root.rglob("*"):
            if not path.is_file() or path.is_symlink():
                continue
            relative = path.relative_to(self.root).as_posix()
            if _matches(relative, self.patterns):
                snapshot[relative] = path.read_bytes()
        return snapshot

    def commit(self) -> None:
        self._committed = True

    def rollback(self) -> None:
        current = self._snapshot()
        for relative in sorted(set(current) - set(self._baseline), reverse=True):
            path = self.root / relative
            if path.is_file() and not path.is_symlink():
                path.unlink()
        for relative, content in self._baseline.items():
            path = self.root / relative
            if not path.exists() or path.read_bytes() != content:
                atomic_write_bytes(path, content)

    def __enter__(self) -> "ScopedProjectTransaction":
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if exc_type is not None or not self._committed:
            self.rollback()
        return False
