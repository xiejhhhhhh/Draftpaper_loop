"""Project-confined, read-only artifact access for compatible extensions."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..project_system_of_record import managed_artifact_contracts


_FORBIDDEN_PREFIXES = (".git/", "guidance/", "guidance_reviews/", "tmp/")


@dataclass(frozen=True)
class ArtifactView:
    relative_path: str
    sha256: str
    artifact_id: str | None
    owner_stage: str | None
    category: str | None
    content: bytes

    def text(self, *, encoding: str = "utf-8") -> str:
        return self.content.decode(encoding)

    def json(self) -> Any:
        return json.loads(self.text())


class ScopedArtifactReader:
    """Read only declared project artifacts; the raw capability token is never persisted."""

    def __init__(self, project_root: str | Path, *, allowed_globs: tuple[str, ...]) -> None:
        self.root = Path(project_root).expanduser().resolve()
        self.allowed_globs = tuple(allowed_globs)
        self._token = secrets.token_urlsafe(24)
        self.token_sha256 = hashlib.sha256(self._token.encode("utf-8")).hexdigest()
        try:
            contracts = managed_artifact_contracts(self.root)
        except Exception:
            contracts = []
        self._contracts = {str(item.get("path")): item for item in contracts if item.get("path")}

    @property
    def capability_token(self) -> str:
        return self._token

    def _relative(self, path: str | Path) -> str:
        candidate = (self.root / Path(path)).resolve()
        try:
            relative = candidate.relative_to(self.root).as_posix()
        except ValueError as exc:
            raise PermissionError("artifact path escapes the project root") from exc
        if relative.startswith(_FORBIDDEN_PREFIXES):
            raise PermissionError(f"artifact path is outside the extension evidence boundary: {relative}")
        if not any(fnmatch.fnmatchcase(relative, pattern) for pattern in self.allowed_globs):
            raise PermissionError(f"artifact path is outside the extension grant: {relative}")
        return relative

    def read(self, relative_path: str, *, token: str) -> ArtifactView:
        if not secrets.compare_digest(token, self._token):
            raise PermissionError("invalid scoped artifact capability token")
        relative = self._relative(relative_path)
        path = self.root / relative
        if not path.is_file():
            raise FileNotFoundError(relative)
        content = path.read_bytes()
        contract = self._contracts.get(relative) or {}
        return ArtifactView(
            relative_path=relative,
            sha256=hashlib.sha256(content).hexdigest(),
            artifact_id=str(contract.get("artifact_id")) if contract.get("artifact_id") else None,
            owner_stage=str(contract.get("owner_stage")) if contract.get("owner_stage") else None,
            category=str(contract.get("category")) if contract.get("category") else None,
            content=content,
        )

    def paths_for_role(self, role: str, *, token: str) -> tuple[str, ...]:
        if not secrets.compare_digest(token, self._token):
            raise PermissionError("invalid scoped artifact capability token")
        normalized = str(role).strip().casefold().replace("-", "_")
        matches = []
        for relative, contract in self._contracts.items():
            haystack = " ".join(
                str(contract.get(key) or "") for key in ("artifact_id", "owner_stage", "category", "path")
            ).casefold().replace("-", "_")
            if normalized in haystack:
                try:
                    self._relative(relative)
                except PermissionError:
                    continue
                matches.append(relative)
        return tuple(sorted(matches))
