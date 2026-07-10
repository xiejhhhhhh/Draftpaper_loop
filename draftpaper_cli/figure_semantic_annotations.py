# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

"""Explicit, auditable semantic mappings for legacy rendered figures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .project_scaffold import _write_json, utc_now
from .project_state import load_project


ANNOTATIONS_PATH = "results/figure_semantic_annotations.json"
RECEIPT_PATH = "results/figure_semantic_annotation_receipt.json"


class FigureSemanticAnnotationError(RuntimeError):
    """Raised when an external semantic annotation is incomplete."""


def submit_figure_semantic_annotations(project: str | Path, input_path: str | Path) -> dict[str, Any]:
    """Store reviewer-supplied semantics without inferring them from a legacy PNG."""

    state = load_project(project)
    source = Path(input_path).expanduser().resolve()
    if not source.is_file():
        raise FigureSemanticAnnotationError(f"Semantic annotation file does not exist: {source}")
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise FigureSemanticAnnotationError(f"Semantic annotation input must be valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise FigureSemanticAnnotationError("Semantic annotation input must be a JSON object.")

    annotations = payload.get("annotations")
    if not isinstance(annotations, list) or not annotations:
        raise FigureSemanticAnnotationError("Semantic annotation input requires a non-empty annotations list.")

    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(annotations, start=1):
        if not isinstance(raw, dict):
            raise FigureSemanticAnnotationError(f"Annotation {index} must be a JSON object.")
        annotation = {str(key): value for key, value in raw.items()}
        figure_id = str(annotation.get("figure_id") or annotation.get("storyboard_id") or annotation.get("id") or "").strip()
        path = str(annotation.get("path") or "").strip().replace("\\", "/")
        if not figure_id and not path:
            raise FigureSemanticAnnotationError(f"Annotation {index} requires figure_id or path.")
        plot_grammar = str(annotation.get("plot_grammar") or "").strip()
        if not plot_grammar:
            raise FigureSemanticAnnotationError(f"Annotation {index} requires plot_grammar.")
        roles = annotation.get("variable_roles") or annotation.get("required_variable_roles") or []
        if not isinstance(roles, list) or not [str(role).strip() for role in roles if str(role).strip()]:
            raise FigureSemanticAnnotationError(f"Annotation {index} requires at least one variable role.")
        evidence_ids = annotation.get("evidence_source_ids")
        if not isinstance(evidence_ids, list) or not [str(item).strip() for item in evidence_ids if str(item).strip()]:
            raise FigureSemanticAnnotationError(f"Annotation {index} requires non-empty evidence_source_ids.")
        key = figure_id or path
        if key in seen:
            raise FigureSemanticAnnotationError(f"Semantic annotations duplicate figure identity: {key}")
        seen.add(key)
        annotation["figure_id"] = figure_id or None
        annotation["path"] = path or None
        annotation["plot_grammar"] = plot_grammar
        annotation["variable_roles"] = [str(role).strip() for role in roles if str(role).strip()]
        annotation["evidence_source_ids"] = [str(item).strip() for item in evidence_ids if str(item).strip()]
        normalized.append(annotation)

    output = {
        "schema_version": "1.0",
        "generated_at": utc_now(),
        "source": str(source),
        "annotations": normalized,
    }
    _write_json(state.path / ANNOTATIONS_PATH, output)
    receipt = {
        "status": "accepted",
        "generated_at": utc_now(),
        "annotation_count": len(normalized),
        "annotation_path": ANNOTATIONS_PATH,
        "source": str(source),
        "message": "Semantic annotations were explicitly supplied and remain subject to figure-contract validation.",
    }
    _write_json(state.path / RECEIPT_PATH, receipt)
    return receipt
