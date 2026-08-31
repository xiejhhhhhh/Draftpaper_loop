"""Structured alignment checks between figures, captions, and claim statements."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .artifact_identity import canonical_json


FIGURE_CLAIM_MAP_SCHEMA = "dpl.figure_claim_map.v1"


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _tokens(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    tokens = []
    for item in value:
        if isinstance(item, dict):
            item = item.get("series_id") or item.get("id") or item.get("label") or item.get("name")
        text = _text(item)
        if text:
            tokens.append(text)
    return sorted(set(tokens))


def _canonical_figure_path(path: str) -> str:
    """Return the shared identity for PDF/PNG renderings of one figure."""

    suffix = Path(path).suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".pdf"}:
        return Path(path).with_suffix("").as_posix()
    return path


def scientific_figure_claim_subject(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the figure-to-claim facts that affect a scientific decision.

    The rendered-file path and generated map row ID are package presentation
    details.  The plotted semantic identity, cohort/split, series and quantity
    contracts, and linked manuscript claim are the parts an author is actually
    approving, so only those participate in the scientific fingerprint.
    """

    # `claim_fact_refs` point to generated brief fact IDs.  They are valuable
    # audit locators, but a regenerated brief can legitimately renumber them
    # without changing a figure's scientific meaning or its manuscript claim.
    keys = (
        "figure_id",
        "figure_semantic_sha256",
        "claim_statement_id",
        "expected_split_id",
        "expected_cohort_id",
        "caption_split_id",
        "caption_cohort_id",
        "figure_split_id",
        "figure_cohort_id",
        "plotted_series_ids",
        "caption_series_ids",
        "claim_series_ids",
        "figure_quantity_kind",
        "caption_quantity_kind",
        "claim_quantity_kind",
    )
    rows = []
    for entry in payload.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        rows.append({key: entry.get(key) for key in keys})
    return sorted(rows, key=lambda item: canonical_json(item))


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
    brief_claims_by_canonical_path = {
        _canonical_figure_path(path): item
        for path, item in brief_claims.items()
    }
    metric = summary.get("core_metrics") if isinstance(summary.get("core_metrics"), dict) else {}
    manuscript_claims = summary.get("manuscript_figure_claims") if isinstance(summary.get("manuscript_figure_claims"), dict) else {}
    rows: list[dict[str, Any]] = []
    for index, figure in enumerate(sorted(figures, key=lambda item: _text(item.get("project_relative_path")))):
        path = _text(figure.get("project_relative_path"))
        claim = brief_claims.get(path) or brief_claims_by_canonical_path.get(_canonical_figure_path(path)) or {}
        statement = claim.get("statement") if isinstance(claim.get("statement"), dict) else {}
        manuscript_claim = manuscript_claims.get(path) if isinstance(manuscript_claims.get(path), dict) else {}
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
                "plotted_series_ids": _tokens(figure.get("series") or figure.get("series_ids")),
                "caption_series_ids": _tokens(figure.get("caption_series_ids")),
                "claim_series_ids": _tokens(figure.get("claim_series_ids") or manuscript_claim.get("series_ids")),
                "figure_quantity_kind": _text(figure.get("quantity_kind")),
                "caption_quantity_kind": _text(figure.get("caption_quantity_kind")),
                "claim_quantity_kind": _text(figure.get("claim_quantity_kind") or manuscript_claim.get("quantity_kind")),
            }
        )
    payload = {
        "schema_version": FIGURE_CLAIM_MAP_SCHEMA,
        "checkpoint_type": summary.get("checkpoint_type") or summary.get("completed_stage"),
        "entries": rows,
        "claim_boundary_statement_ids": [item.get("statement_id") for item in brief.get("claim_boundaries") or [] if isinstance(item, dict)],
    }
    payload["scientific_figure_claim_subject"] = scientific_figure_claim_subject(payload)
    payload["scientific_figure_claim_sha256"] = _hash(payload["scientific_figure_claim_subject"])
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
        plotted = set(row.get("plotted_series_ids") or [])
        caption = set(row.get("caption_series_ids") or [])
        claim = set(row.get("claim_series_ids") or [])
        if plotted and caption and not caption <= plotted:
            issues.append(
                {
                    "code": "caption_series_not_plotted",
                    "figure_id": figure_id,
                    "detail_zh": f"{figure_id} 的图注引用了图面不存在的系列或类别。",
                }
            )
        if plotted and claim and not claim <= plotted:
            issues.append(
                {
                    "code": "manuscript_series_not_plotted",
                    "figure_id": figure_id,
                    "detail_zh": f"{figure_id} 的正文论断引用了图面不存在的系列或类别。",
                }
            )
        figure_quantity = _text(row.get("figure_quantity_kind"))
        for label, actual in (("caption", _text(row.get("caption_quantity_kind"))), ("claim", _text(row.get("claim_quantity_kind")))):
            if figure_quantity and actual and figure_quantity != actual:
                issues.append(
                    {
                        "code": f"{label}_quantity_kind_mismatch",
                        "figure_id": figure_id,
                        "detail_zh": f"{figure_id} 的{label}数值口径与图面不一致，不能混淆绝对计数与条件比例。",
                    }
                )
    return issues


__all__ = [
    "FIGURE_CLAIM_MAP_SCHEMA",
    "build_figure_claim_map",
    "scientific_figure_claim_subject",
    "validate_figure_claim_map",
]
