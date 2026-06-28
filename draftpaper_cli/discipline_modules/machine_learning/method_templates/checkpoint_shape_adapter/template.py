# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def expected_token_count(img_size: int, patch_size: int) -> int:
    if img_size % patch_size != 0:
        raise ValueError("img_size must be divisible by patch_size")
    grid = img_size // patch_size
    return grid * grid + 1


def compare_checkpoint_shapes(checkpoint_shapes: dict[str, list[int]], model_shapes: dict[str, list[int]]) -> dict[str, Any]:
    compatible = []
    resizable_position_embeddings = []
    skipped = []
    for key, ckpt_shape in checkpoint_shapes.items():
        model_shape = model_shapes.get(key)
        if model_shape is None:
            skipped.append({"key": key, "reason": "missing_in_model", "checkpoint_shape": ckpt_shape})
        elif ckpt_shape == model_shape:
            compatible.append(key)
        elif "pos" in key.lower() and len(ckpt_shape) == 3 and len(model_shape) == 3 and ckpt_shape[-1] == model_shape[-1]:
            resizable_position_embeddings.append({"key": key, "checkpoint_shape": ckpt_shape, "model_shape": model_shape})
        else:
            skipped.append({"key": key, "reason": "shape_mismatch", "checkpoint_shape": ckpt_shape, "model_shape": model_shape})
    return {"compatible": compatible, "resizable_position_embeddings": resizable_position_embeddings, "skipped": skipped}


def write_shape_report(report: dict[str, Any], output_json: Path) -> dict[str, int]:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "compatible_count": len(report.get("compatible", [])),
        "resizable_count": len(report.get("resizable_position_embeddings", [])),
        "skipped_count": len(report.get("skipped", [])),
    }
