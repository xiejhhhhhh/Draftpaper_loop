"""Small dependency-free language and discipline helpers for literature search."""

from __future__ import annotations

import re
from typing import Iterable


_CJK_SPAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")
_LATIN_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9-]{1,}")
_GENERIC_TERMS = {
    "analysis", "approach", "based", "data", "framework", "method", "methods", "model", "models",
    "paper", "research", "study", "using", "with", "from", "results", "system", "evaluation",
    "learning", "machine", "science", "scientific", "application", "applications", "new", "review",
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

_DISCIPLINE_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("astronomy", ("astronomy", "astrophysics", "galaxy", "stellar", "x-ray", "transient", "天文学", "星系", "恒星")),
    ("medicine", ("medicine", "medical", "clinical", "patient", "disease", "医学", "临床", "患者", "疾病")),
    ("life_science", ("biology", "genomic", "transcriptomic", "protein", "biology", "生物", "基因", "蛋白")),
    ("computer_science", ("computer science", "software", "algorithm", "programming", "计算机", "算法")),
    ("machine_learning", ("machine learning", "deep learning", "neural network", "transformer", "机器学习", "深度学习")),
    ("social_science", ("social science", "society", "governance", "rural", "village", "社会科学", "治理", "乡村", "农村")),
    ("economics", ("economics", "economic", "finance", "income", "economy", "经济", "金融", "收入")),
    ("geography", ("geography", "geospatial", "remote sensing", "climate", "地理", "遥感", "空间")),
    ("chemistry", ("chemistry", "molecule", "compound", "化学", "分子", "化合物")),
    ("materials_science", ("materials", "material", "crystal", "alloy", "材料", "晶体", "合金")),
    ("law", ("law", "legal", "administrative", "jurisdiction", "法学", "法律", "行政")),
)


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
    value = _normalized(text)
    scores: list[tuple[int, str]] = []
    for discipline, markers in _DISCIPLINE_MARKERS:
        score = sum(1 for marker in markers if marker.lower() in value)
        if score:
            scores.append((score, discipline))
    scores.sort(key=lambda item: (-item[0], item[1]))
    if not scores:
        return ["general"]
    return [discipline for _, discipline in scores[:4]]


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


def contains_topic_anchor(text: str, anchors: Iterable[str], aliases: Iterable[str] = ()) -> bool:
    value = _normalized(text)
    terms = [*anchors, *aliases]
    return any(str(term or "").lower() in value for term in terms if str(term or "").strip())
