# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

"""Small, strict readers for Draftpaper JSON and YAML artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


class StructuredArtifactError(RuntimeError):
    """Raised when a required structured artifact cannot be decoded."""


def read_mapping(path: str | Path, *, strict: bool = False) -> dict[str, Any]:
    """Read a JSON or YAML object without changing its on-disk representation."""
    target = Path(path)
    if not target.exists():
        if strict:
            raise StructuredArtifactError(f"Structured artifact does not exist: {target}")
        return {}
    try:
        text = target.read_text(encoding="utf-8-sig")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = yaml.safe_load(text)
    except (OSError, yaml.YAMLError, UnicodeError) as exc:
        if strict:
            raise StructuredArtifactError(f"Cannot read structured artifact {target}: {exc}") from exc
        return {}
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        if strict:
            raise StructuredArtifactError(f"Structured artifact must contain an object: {target}")
        return {}
    return payload


def read_list(path: str | Path, *, strict: bool = False) -> list[Any]:
    """Read a top-level JSON/YAML list when an artifact intentionally uses one."""
    target = Path(path)
    if not target.exists():
        if strict:
            raise StructuredArtifactError(f"Structured artifact does not exist: {target}")
        return []
    try:
        payload = yaml.safe_load(target.read_text(encoding="utf-8-sig"))
    except (OSError, yaml.YAMLError, UnicodeError) as exc:
        if strict:
            raise StructuredArtifactError(f"Cannot read structured artifact {target}: {exc}") from exc
        return []
    return payload if isinstance(payload, list) else []
