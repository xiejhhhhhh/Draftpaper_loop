# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .state_kernel import atomic_write_json, atomic_write_text


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return default


def read_text(path: Path, default: str = "", *, limit: int | None = None) -> str:
    if not path.exists():
        return default
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return default
    return text[:limit] if limit is not None else text


def read_json_object(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    fallback = {} if default is None else default
    payload = read_json(path, fallback)
    return payload if isinstance(payload, dict) else fallback


def read_json_list(path: Path, default: list[Any] | None = None) -> list[Any]:
    fallback = [] if default is None else default
    payload = read_json(path, fallback)
    return payload if isinstance(payload, list) else fallback


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in read_text(path).splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def write_json(path: Path, payload: Any) -> None:
    atomic_write_json(path, payload)


def write_text(path: Path, text: str) -> None:
    atomic_write_text(path, text)
