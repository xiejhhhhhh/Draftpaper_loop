# Copyright (c) 2026 xiejhhhhhh
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations


def build_pdp_ice_plan(*, features: list[str], target_column: str, grid_resolution: int = 50) -> dict[str, object]:
    return {
        "template_id": "partial_dependence_ice_analysis",
        "features": list(features),
        "target_column": target_column,
        "grid_resolution": grid_resolution,
        "requires_packages": ["scikit-learn", "matplotlib"],
        "required_artifacts": ["partial_dependence", "ice_curves", "pdp_ice_figure"],
    }
