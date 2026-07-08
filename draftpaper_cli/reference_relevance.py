# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import re
from typing import Any


_BROAD_TOKENS = {
    "study",
    "paper",
    "research",
    "analysis",
    "method",
    "methods",
    "model",
    "models",
    "data",
    "using",
    "based",
    "with",
    "from",
    "field",
    "astronomy",
    "machine",
    "learning",
    "domain",
    "time",
    "long",
    "term",
    "source",
    "sources",
}
_SHORT_KEYWORDS = {"ep", "wxt", "fxt", "agn", "xrb", "tde", "xray", "roc", "auc"}


def keyword_tokens(text: str) -> set[str]:
    normalized = str(text or "").lower().replace("x-ray", "xray").replace("time-domain", "timedomain")
    tokens = set(re.findall(r"[a-z0-9]+", normalized))
    return {
        token
        for token in tokens
        if (len(token) >= 4 or token in _SHORT_KEYWORDS)
        and token not in _BROAD_TOKENS
    }


def project_relevance_tokens(project_meta: dict[str, Any]) -> set[str]:
    return keyword_tokens(" ".join([
        str(project_meta.get("idea") or ""),
        str(project_meta.get("title") or ""),
        str(project_meta.get("field") or ""),
    ]))


def reference_relevance_score(reference: dict[str, Any], project_tokens: set[str]) -> int:
    text = " ".join(
        str(reference.get(key) or "")
        for key in ["claim", "intended_use", "evidence_summary", "title", "citation_key"]
    )
    return len(keyword_tokens(text) & project_tokens)


def filter_relevant_references(references: list[dict[str, Any]], project_meta: dict[str, Any]) -> list[dict[str, Any]]:
    project_tokens = project_relevance_tokens(project_meta)
    if not project_tokens:
        return references
    relevant = [item for item in references if reference_relevance_score(item, project_tokens) >= 1]
    return relevant or references

