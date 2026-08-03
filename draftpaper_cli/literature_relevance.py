"""Content-aware relevance, discipline and role evidence gates."""

from __future__ import annotations

import re
from typing import Any

from .literature_language import discipline_hypotheses, tokenize_multilingual


ROLE_TERMS: dict[str, tuple[str, ...]] = {
    "problem_gap": ("gap", "lack", "challenge", "unresolved", "remain", "motivat", "问题", "不足", "挑战"),
    "data_provenance": ("dataset", "data release", "catalog", "survey", "cohort", "archive", "sample construction", "数据集", "数据发布", "星表", "样本构建"),
    "method": ("algorithm", "architecture", "method", "model", "regression", "classifier", "estimator", "方法", "算法", "模型"),
    "evaluation_standard": ("metric", "evaluation", "benchmark", "confidence interval", "calibration", "statistical test", "指标", "评估", "基准", "置信区间"),
    "baseline": ("baseline", "comparison", "state of the art", "benchmark", "对比", "基线"),
    "limitations": ("limitation", "uncertainty", "future work", "caveat", "bias", "failure", "局限", "不确定性", "偏差"),
}


def _text(item: dict[str, Any]) -> str:
    summary = item.get("deep_summary") if isinstance(item.get("deep_summary"), dict) else {}
    return " ".join(
        str(item.get(key) or "")
        for key in ("title", "abstract", "evidence_notes", "pdf_text_excerpt", "pdf_text", "claim", "intended_use", "publication")
    ) + " " + " ".join(str(value or "") for value in summary.values())


def classify_content_roles(item: dict[str, Any]) -> dict[str, dict[str, Any]]:
    text = _text(item).lower()
    result: dict[str, dict[str, Any]] = {}
    for role, terms in ROLE_TERMS.items():
        hits = sorted({term for term in terms if term.lower() in text})
        supported = bool(hits)
        if role == "data_provenance":
            provenance_terms = ("source", "access", "release", "archive", "collection", "sample", "来源", "获取", "发布", "档案", "样本")
            supported = supported and any(term in text for term in provenance_terms)
        result[role] = {"supported": supported, "evidence_terms": hits, "status": "content_supported" if supported else "query_intended_only"}
    return result


def _topic_score(item: dict[str, Any], contract: dict[str, Any]) -> tuple[float, list[str]]:
    title = str(item.get("title") or "")
    abstract = " ".join(str(item.get(key) or "") for key in ("abstract", "evidence_notes", "pdf_text_excerpt"))
    anchors = [str(value).lower() for value in contract.get("must_preserve_terms") or [] if str(value).strip()]
    aliases = [str(value).lower() for value in contract.get("optional_terms") or [] if str(value).strip()]
    title_lower, abstract_lower = title.lower(), abstract.lower()
    exact_hits = [term for term in [*anchors, *aliases] if term in title_lower or term in abstract_lower]
    title_exact = [term for term in [*anchors, *aliases] if term in title_lower]
    project_terms = {term for term in tokenize_multilingual(" ".join([*anchors, *aliases])) if len(term) >= 2}
    item_terms = tokenize_multilingual(" ".join([title, abstract]))
    overlap = project_terms & item_terms
    token_score = len(overlap) / max(1, len(project_terms))
    score = max(0.0, min(1.0, (0.85 if title_exact else 0.45 if exact_hits else 0.0) + min(0.35, token_score * 0.35)))
    return round(score, 4), sorted(set(exact_hits) | overlap)


def score_reference(item: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    topic_score, topic_hits = _topic_score(item, contract)
    target_disciplines = set(str(value) for value in contract.get("discipline_hypotheses") or ["general"])
    item_disciplines = set(discipline_hypotheses(_text(item)))
    discipline_score = 1.0 if "general" in target_disciplines or "general" in item_disciplines or target_disciplines & item_disciplines else 0.55
    if target_disciplines & {"medicine", "life_science"} and item_disciplines & {"astronomy", "computer_science", "machine_learning"} and not (target_disciplines & item_disciplines):
        discipline_score = 0.0
    role_evidence = classify_content_roles(item)
    role_score = sum(1 for value in role_evidence.values() if value["supported"]) / max(1, len(role_evidence))
    metadata_fields = ("title", "authors", "year", "doi", "abstract")
    metadata_score = sum(bool(item.get(field)) for field in metadata_fields) / len(metadata_fields)
    evidence_score = 1.0 if item.get("pdf_text_excerpt") or item.get("evidence_passages") or item.get("document_parses") else 0.65 if item.get("abstract") else 0.0
    return {
        "topic_relevance_score": round(topic_score, 4),
        "discipline_match_score": round(discipline_score, 4),
        "role_evidence_score": round(role_score, 4),
        "metadata_completeness_score": round(metadata_score, 4),
        "evidence_readiness_score": round(evidence_score, 4),
        "topic_hits": topic_hits,
        "discipline_hypotheses": sorted(item_disciplines),
        "role_evidence": role_evidence,
    }


def apply_relevance_gate(items: list[dict[str, Any]], contract: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for raw in items:
        item = dict(raw)
        scores = score_reference(item, contract)
        item.update(scores)
        curated = bool(item.get("user_confirmed") or item.get("retained") or item.get("reference_origin") in {"existing_zotero", "local_import", "manual"})
        if curated:
            item["candidate_state"] = "curated_unverified"
            accepted.append(item)
            continue
        reasons: list[str] = []
        if scores["topic_relevance_score"] < 0.25:
            reasons.append("topic_mismatch")
        if scores["discipline_match_score"] == 0:
            reasons.append("discipline_mismatch")
        if not item.get("title") or not item.get("authors"):
            reasons.append("metadata_unresolved")
        if reasons:
            item["candidate_state"] = "rejected"
            item["rejection_codes"] = reasons
            rejected.append(item)
        else:
            item["candidate_state"] = "relevance_passed"
            accepted.append(item)
    return accepted, rejected
