"""Content-aware relevance, discipline and role evidence gates."""

from __future__ import annotations

import re
from typing import Any

from .literature_discipline_policy import assess_discipline_compatibility, discipline_evidence
from .literature_language import classify_query_terms, discipline_hypotheses, distinctive_terms, tokenize_multilingual


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


def _normalized(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").casefold()).strip()


def _contains(text: str, term: str) -> bool:
    value = _normalized(term)
    if not value:
        return False
    if re.search(r"[\u3400-\u9fff]", value):
        return value in text
    escaped = re.escape(value).replace(r"\ ", r"\s+")
    return re.search(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", text) is not None


def _term_coverage(text: str, terms: list[str]) -> tuple[float, list[str]]:
    if not terms:
        return 0.0, []
    hits = [term for term in terms if _contains(text, term)]
    return len(hits) / len(terms), hits


def _entity_coverage(text: str, terms: list[str]) -> tuple[float, list[str]]:
    if not terms:
        return 0.0, []
    scores: list[float] = []
    hits: list[str] = []
    text_terms = tokenize_multilingual(text)
    for term in terms:
        if _contains(text, term):
            scores.append(1.0)
            hits.append(term)
            continue
        components = distinctive_terms(term)
        overlap = components & text_terms
        score = len(overlap) / max(1, len(components))
        scores.append(score)
        hits.extend(sorted(overlap))
    return sum(scores) / len(scores), list(dict.fromkeys(hits))


def _entity_group_coverage(text: str, groups: list[list[str]]) -> tuple[float, list[str]]:
    if not groups:
        return 0.0, []
    scores: list[float] = []
    hits: list[str] = []
    for group in groups:
        group_score, group_hits = _entity_coverage(text, group)
        exact_hits = [term for term in group if _contains(text, term)]
        scores.append(1.0 if exact_hits else group_score)
        hits.extend(exact_hits or group_hits)
    return sum(scores) / len(scores), list(dict.fromkeys(hits))


def _tiered_contract_terms(contract: dict[str, Any]) -> dict[str, list[str]]:
    explicit = {
        key: [str(value) for value in contract.get(key) or [] if str(value).strip()]
        for key in ("entity_anchors", "discipline_anchors", "method_anchors", "generic_terms")
    }
    if any(explicit.values()):
        return explicit
    legacy = [str(value) for value in contract.get("must_preserve_terms") or [] if str(value).strip()]
    inferred = classify_query_terms(" ".join(legacy))
    if not inferred["entity_anchors"] and legacy:
        inferred["entity_anchors"] = legacy
    return inferred


def _topic_score(item: dict[str, Any], contract: dict[str, Any]) -> tuple[float, list[str], dict[str, Any]]:
    title = str(item.get("title") or "")
    abstract = " ".join(str(item.get(key) or "") for key in ("abstract", "evidence_notes", "pdf_text_excerpt"))
    title_text = _normalized(title)
    combined = _normalized(" ".join([title, abstract]))
    tiers = _tiered_contract_terms(contract)
    aliases = [str(value) for value in contract.get("optional_terms") or [] if str(value).strip()]
    raw_groups = contract.get("entity_anchor_groups") if isinstance(contract.get("entity_anchor_groups"), list) else []
    entity_groups = [
        [str(value) for value in group if str(value).strip()]
        for group in raw_groups
        if isinstance(group, list)
    ]
    entity_score, entity_hits = (
        _entity_group_coverage(combined, entity_groups)
        if entity_groups
        else _entity_coverage(combined, tiers["entity_anchors"])
    )
    discipline_score, discipline_hits = _term_coverage(combined, tiers["discipline_anchors"])
    method_score, method_hits = _term_coverage(combined, tiers["method_anchors"])
    alias_score, alias_hits = _term_coverage(combined, aliases)
    title_entity_score, title_entity_hits = (
        _entity_group_coverage(title_text, entity_groups)
        if entity_groups
        else _entity_coverage(title_text, tiers["entity_anchors"])
    )
    score = (
        (0.60 * entity_score)
        + (0.20 * discipline_score)
        + (0.15 * method_score)
        + (0.05 * alias_score)
        + (0.10 if title_entity_hits else 0.0)
    )
    if not tiers["entity_anchors"]:
        score = (0.55 * discipline_score) + (0.35 * method_score) + (0.10 * alias_score)
    generic_hits = [term for term in tiers["generic_terms"] if _contains(combined, term)]
    high_value_hits = [*entity_hits, *discipline_hits, *method_hits, *alias_hits]
    generic_only = bool(generic_hits) and not high_value_hits
    if generic_only:
        score = min(score, 0.34)
    details = {
        "entity_anchor_coverage": round(entity_score, 4),
        "title_entity_anchor_coverage": round(title_entity_score, 4),
        "discipline_anchor_coverage": round(discipline_score, 4),
        "method_anchor_coverage": round(method_score, 4),
        "optional_alias_coverage": round(alias_score, 4),
        "entity_hits": entity_hits,
        "discipline_hits": discipline_hits,
        "method_hits": method_hits,
        "alias_hits": alias_hits,
        "generic_hits": generic_hits,
        "generic_only_match": generic_only,
    }
    return round(max(0.0, min(1.0, score)), 4), sorted(set(high_value_hits) | set(generic_hits)), details


def score_reference(item: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    topic_score, topic_hits, topic_evidence = _topic_score(item, contract)
    target_disciplines = set(str(value) for value in contract.get("discipline_hypotheses") or ["discipline_unknown"])
    item_text = _text(item)
    item_disciplines = set(discipline_hypotheses(item_text))
    item_discipline_evidence = discipline_evidence(item_text)
    discipline_assessment = assess_discipline_compatibility(
        target_disciplines,
        item_disciplines,
        candidate_evidence=item_discipline_evidence,
        item=item,
    )
    discipline_score = float(discipline_assessment["score"])
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
        "topic_evidence": topic_evidence,
        "discipline_hypotheses": sorted(item_disciplines),
        "discipline_evidence": item_discipline_evidence,
        "discipline_assessment": discipline_assessment,
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
            item["gate_state"] = "review_required"
            item["review_codes"] = ["user_curated_requires_evidence_review"]
            accepted.append(item)
            continue
        rejection_codes: list[str] = []
        review_codes: list[str] = []
        topic_score = float(scores["topic_relevance_score"])
        if topic_score < 0.35:
            rejection_codes.append("topic_mismatch")
        elif topic_score < 0.55:
            review_codes.append("topic_borderline")
        if scores["topic_evidence"].get("generic_only_match"):
            rejection_codes.append("generic_terms_only")
        discipline_state = str(scores["discipline_assessment"].get("state") or "review_required")
        if discipline_state == "rejected":
            rejection_codes.append("discipline_mismatch")
        elif discipline_state == "review_required":
            review_codes.extend(str(value) for value in scores["discipline_assessment"].get("reason_codes") or [])
        if not item.get("title"):
            rejection_codes.append("metadata_unresolved")
        elif not item.get("authors"):
            review_codes.append("authors_unresolved")
        if rejection_codes:
            item["candidate_state"] = "rejected"
            item["gate_state"] = "rejected"
            item["rejection_codes"] = list(dict.fromkeys(rejection_codes))
            rejected.append(item)
        elif review_codes:
            item["candidate_state"] = "review_required"
            item["gate_state"] = "review_required"
            item["review_codes"] = list(dict.fromkeys(review_codes))
            accepted.append(item)
        else:
            item["candidate_state"] = "relevance_passed"
            item["gate_state"] = "accepted"
            accepted.append(item)
    return accepted, rejected
