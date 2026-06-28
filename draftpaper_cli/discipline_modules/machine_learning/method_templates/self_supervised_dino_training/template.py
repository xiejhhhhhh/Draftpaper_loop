# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_dino_training_plan(
    *,
    dataset_manifest: Path,
    output_json: Path,
    model_type: str = "vit_small",
    img_size: int = 224,
    patch_size: int = 16,
    global_crops: int = 2,
    local_crops: int = 2,
    teacher_momentum: float = 0.996,
) -> dict[str, Any]:
    plan = {
        "dataset_manifest": "{{dataset_manifest}}",
        "dataset_manifest_provided": dataset_manifest.exists(),
        "model_type": model_type,
        "img_size": img_size,
        "patch_size": patch_size,
        "global_crops": global_crops,
        "local_crops": local_crops,
        "teacher_momentum": teacher_momentum,
        "validation_outputs": ["training_log.json", "checkpoint_manifest.json", "embedding_health.csv"],
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return plan
