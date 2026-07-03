# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


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
