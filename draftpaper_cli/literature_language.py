"""Small dependency-free language and discipline helpers for literature search."""

from __future__ import annotations

import re
from typing import Iterable

from .literature_discipline_policy import (
    DISCIPLINE_ONTOLOGY,
    discipline_hypotheses_from_ontology,
    discipline_marker_terms,
)


_CJK_SPAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")
_LATIN_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9-]{1,}")
_GENERIC_TERMS = {
    "analysis", "approach", "based", "data", "framework", "method", "methods", "model", "models",
    "paper", "research", "study", "using", "with", "from", "results", "system", "evaluation",
    "learning", "machine", "science", "scientific", "application", "applications", "new", "review",
    "population", "classification", "catalog", "catalogue", "diversity", "source", "distribution",
    "survey", "network", "morphology", "embedding", "detection",
}

_METHOD_TERMS = {
    "algorithm", "benchmark", "calibration", "classifier", "deep learning", "embedding",
    "machine learning", "model", "neural network", "representation learning", "regression",
    "split", "transformer", "算法", "基准", "分类器", "深度学习", "机器学习", "模型",
    "神经网络", "表征学习", "回归", "数据划分",
}

_ALIASES: dict[str, tuple[str, ...]] = {
    "数字乡村": ("乡村数字化", "数字农业", "数字治理", "digital village", "rural digitalization", "digital rural governance"),
    "农村治理": ("乡村治理", "rural governance", "rural administration", "rural public governance"),
    "深度学习": ("deep learning", "neural network", "representation learning"),
    "机器学习": ("machine learning", "statistical learning"),
    "遥感": ("remote sensing", "earth observation", "satellite imagery"),
    "天文学": ("astronomy", "astrophysics"),
    "医学": ("medicine", "clinical", "medical"),
    "公共治理": ("public governance", "public administration", "policy implementation"),
}

def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def cjk_terms(text: str) -> set[str]:
    """Return whole CJK spans and short n-grams without a tokenizer dependency."""
    terms: set[str] = set()
    for match in _CJK_SPAN_RE.finditer(str(text or "")):
        span = match.group(0)
        if len(span) >= 2:
            terms.add(span)
        for size in range(2, min(4, len(span)) + 1):
            terms.update(span[index : index + size] for index in range(0, len(span) - size + 1))
    return terms


def tokenize_multilingual(text: str) -> set[str]:
    tokens = {token.lower() for token in _LATIN_TOKEN_RE.findall(str(text or ""))}
    tokens.update(cjk_terms(text))
    return tokens


def language_codes(text: str) -> list[str]:
    value = str(text or "")
    codes: list[str] = []
    if _CJK_SPAN_RE.search(value):
        codes.append("zh-CN")
    if re.search(r"[A-Za-z]", value):
        codes.append("en")
    return codes or ["und"]


def discipline_hypotheses(text: str) -> list[str]:
    return discipline_hypotheses_from_ontology(text)


def distinctive_terms(text: str) -> set[str]:
    return {term for term in tokenize_multilingual(text) if term not in _GENERIC_TERMS and (len(term) >= 2)}


def topic_anchor_terms(*texts: str) -> list[str]:
    """Return ordered terms that must survive query expansion."""
    result: list[str] = []
    seen: set[str] = set()
    for text in texts:
        value = str(text or "").strip()
        for match in _CJK_SPAN_RE.finditer(value):
            span = match.group(0)
            if len(span) >= 2 and span not in seen:
                result.append(span)
                seen.add(span)
        for token in _LATIN_TOKEN_RE.findall(value):
            lowered = token.lower()
            if lowered in _GENERIC_TERMS or lowered in seen:
                continue
            result.append(token)
            seen.add(lowered)
    return result[:12]


def classify_query_terms(*texts: str) -> dict[str, list[str]]:
    """Classify query evidence into entity, discipline, method, and generic tiers."""
    combined = " ".join(str(value or "") for value in texts)
    normalized = _normalized(combined)
    disciplines = discipline_hypotheses(combined)
    discipline_terms = discipline_marker_terms(disciplines, combined)
    method_terms = sorted(term for term in _METHOD_TERMS if term.casefold() in normalized)
    anchors = topic_anchor_terms(*texts)
    discipline_vocab = {
        str(marker).casefold()
        for profile in DISCIPLINE_ONTOLOGY.values()
        for marker in profile.get("markers") or ()
    }
    entity_terms: list[str] = []
    generic_terms: list[str] = []
    for anchor in anchors:
        lowered = anchor.casefold()
        if lowered in _GENERIC_TERMS:
            generic_terms.append(anchor)
        elif lowered in discipline_vocab or any(lowered == term.casefold() for term in discipline_terms):
            continue
        elif any(lowered == term.casefold() for term in method_terms):
            continue
        else:
            entity_terms.append(anchor)
    raw_tokens = tokenize_multilingual(combined)
    generic_terms.extend(sorted(token for token in raw_tokens if token in _GENERIC_TERMS))
    return {
        "entity_anchors": list(dict.fromkeys(entity_terms))[:16],
        "discipline_anchors": list(dict.fromkeys(discipline_terms))[:16],
        "method_anchors": list(dict.fromkeys(method_terms))[:16],
        "generic_terms": list(dict.fromkeys(generic_terms))[:24],
    }


def alias_terms(anchors: Iterable[str]) -> list[str]:
    aliases: list[str] = []
    seen: set[str] = set()
    for anchor in anchors:
        for alias in _ALIASES.get(str(anchor), ()):
            key = alias.lower()
            if key not in seen:
                aliases.append(alias)
                seen.add(key)
    return aliases[:16]


def alias_groups(anchors: Iterable[str]) -> list[list[str]]:
    """Return OR-groups so multilingual aliases do not dilute anchor coverage."""
    groups: list[list[str]] = []
    for anchor in anchors:
        values = [str(anchor), *_ALIASES.get(str(anchor), ())]
        groups.append(list(dict.fromkeys(value for value in values if value))[:8])
    return groups[:12]


def contains_topic_anchor(text: str, anchors: Iterable[str], aliases: Iterable[str] = ()) -> bool:
    value = _normalized(text)
    terms = [*anchors, *aliases]
    return any(str(term or "").lower() in value for term in terms if str(term or "").strip())
