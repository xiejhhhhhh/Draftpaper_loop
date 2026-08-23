"""Structured alignment checks between figures, captions, and claim statements."""

from __future__ import annotations

import hashlib
from typing import Any

from .artifact_identity import canonical_json


FIGURE_CLAIM_MAP_SCHEMA = "dpl.figure_claim_map.v1"


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    return str(value or "").strip()


def build_figure_claim_map(summary: dict[str, Any], brief: dict[str, Any]) -> dict[str, Any]:
    figures = [
        item
        for item in summary.get("stage_deliverables") or []
        if isinstance(item, dict) and _text(item.get("deliverable_group")) == "figure"
    ]
    brief_claims = {
        _text(item.get("project_relative_path")): item
        for item in brief.get("figure_claims") or []
        if isinstance(item, dict) and _text(item.get("project_relative_path"))
    }
    metric = summary.get("core_metrics") if isinstance(summary.get("core_metrics"), dict) else {}
    rows: list[dict[str, Any]] = []
    for index, figure in enumerate(sorted(figures, key=lambda item: _text(item.get("project_relative_path")))):
        path = _text(figure.get("project_relative_path"))
        claim = brief_claims.get(path) or {}
        statement = claim.get("statement") if isinstance(claim.get("statement"), dict) else {}
        rows.append(
            {
                "map_id": f"figure-map-{index + 1}",
                "figure_id": _text(figure.get("figure_id") or figure.get("title_zh")) or f"figure-{index + 1}",
                "project_relative_path": path,
                "figure_semantic_sha256": figure.get("after_semantic_sha256") or figure.get("evidence_sha256"),
                "caption": _text(figure.get("caption")),
                "interpretation": _text(figure.get("interpretation_summary") or figure.get("scientific_relevance_zh")),
                "claim_statement_id": statement.get("statement_id"),
                "claim_fact_refs": statement.get("fact_refs") or [],
                "claim_evidence_refs": statement.get("evidence_refs") or [],
                "expected_split_id": metric.get("split_id"),
                "expected_cohort_id": metric.get("cohort_id"),
                "caption_split_id": figure.get("caption_split_id"),
                "caption_cohort_id": figure.get("caption_cohort_id"),
                "figure_split_id": figure.get("split_id"),
                "figure_cohort_id": figure.get("cohort_id"),
            }
        )
    payload = {
        "schema_version": FIGURE_CLAIM_MAP_SCHEMA,
        "checkpoint_type": summary.get("checkpoint_type") or summary.get("completed_stage"),
        "entries": rows,
        "claim_boundary_statement_ids": [item.get("statement_id") for item in brief.get("claim_boundaries") or [] if isinstance(item, dict)],
    }
    payload["figure_claim_map_sha256"] = _hash(payload)
    return payload


def validate_figure_claim_map(payload: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if payload.get("schema_version") != FIGURE_CLAIM_MAP_SCHEMA:
        return [{"code": "invalid_schema", "detail_zh": "FigureClaimMap schema 不受支持。"}]
    for row in payload.get("entries") or []:
        if not isinstance(row, dict):
            issues.append({"code": "invalid_entry", "detail_zh": "FigureClaimMap 包含非对象条目。"})
            continue
        figure_id = _text(row.get("figure_id")) or "未知图"
        if not _text(row.get("project_relative_path")) or not _text(row.get("figure_semantic_sha256")):
            issues.append({"code": "missing_figure_semantic_identity", "figure_id": figure_id, "detail_zh": f"{figure_id} 缺少图表语义身份，不能用于科学确认。"})
        if not _text(row.get("claim_statement_id")):
            issues.append({"code": "missing_claim_binding", "figure_id": figure_id, "detail_zh": f"{figure_id} 没有可追溯的决定页论断绑定。"})
        for prefix, expected_key, actual_key in (
            ("split", "expected_split_id", "caption_split_id"),
            ("split", "expected_split_id", "figure_split_id"),
            ("cohort", "expected_cohort_id", "caption_cohort_id"),
            ("cohort", "expected_cohort_id", "figure_cohort_id"),
        ):
            expected = _text(row.get(expected_key))
            actual = _text(row.get(actual_key))
            if expected and actual and expected != actual:
                issues.append(
                    {
                        "code": f"{prefix}_identity_mismatch",
                        "figure_id": figure_id,
                        "detail_zh": f"{figure_id} 的 {actual_key} 与当前证据身份不一致。",
                    }
                )
    return issues


__all__ = ["FIGURE_CLAIM_MAP_SCHEMA", "build_figure_claim_map", "validate_figure_claim_map"]
