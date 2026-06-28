# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def normalize_backbone_metadata(
    *,
    model_name: str,
    source: str,
    embedding_dim: int | None = None,
    patch_size: int | None = None,
    input_channels: int = 3,
    checkpoint_path: str | None = None,
) -> dict[str, Any]:
    return {
        "model_name": model_name,
        "source": source,
        "embedding_dim": embedding_dim,
        "patch_size": patch_size,
        "input_channels": input_channels,
        "checkpoint_path_provided": bool(checkpoint_path),
        "checkpoint_path": "{{checkpoint_path}}" if checkpoint_path else "",
    }


def write_backbone_metadata(metadata: dict[str, Any], output_json: Path) -> dict[str, Any]:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "written", "model_name": metadata.get("model_name", "")}
