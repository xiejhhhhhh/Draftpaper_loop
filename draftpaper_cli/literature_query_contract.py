"""Versioned query contract for multilingual, discipline-aware literature search."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .literature_discipline_policy import generated_conflict_terms, ontology_snapshot
from .literature_language import alias_groups, alias_terms, classify_query_terms, discipline_hypotheses, language_codes, topic_anchor_terms
from .project_scaffold import _write_json
from .project_state import load_project


QUERY_CONTRACT_SCHEMA = "dpl.literature_query.v3"
DEFAULT_ROLES = ("problem_gap", "data_provenance", "method", "evaluation_standard", "baseline", "limitations")


def build_query_contract(project: str | Path, query: str | None = None) -> dict[str, Any]:
    state = load_project(project)
    idea = str(state.metadata.get("idea") or "").strip()
    field = str(state.metadata.get("field") or "").strip()
    original = str(query or idea).strip()
    anchors = topic_anchor_terms(original, idea, field)
    aliases = alias_terms(anchors)
    hypotheses = discipline_hypotheses(" ".join([original, idea, field]))
    languages = language_codes(" ".join([original, idea, field]))
    tiered_terms = classify_query_terms(original, idea, field)
    ontology = ontology_snapshot()
    negative_terms, negative_evidence = generated_conflict_terms(hypotheses)
    return {
        "schema_version": QUERY_CONTRACT_SCHEMA,
        "original_query": original,
        "project_idea": idea,
        "field": field,
        "languages": languages,
        "discipline_hypotheses": hypotheses,
        "must_preserve_terms": anchors,
        "optional_terms": aliases,
        "entity_anchor_groups": alias_groups(tiered_terms["entity_anchors"]),
        **tiered_terms,
        "negative_terms": negative_terms,
        "negative_term_evidence": negative_evidence,
        "roles": list(DEFAULT_ROLES),
        "expansion_mode": "balanced",
        "user_query_is_authoritative": bool(query),
        "discipline_ontology_schema": ontology["schema_version"],
    }


def write_query_contract(project: str | Path, contract: dict[str, Any]) -> str:
    state = load_project(project)
    path = state.path / "references" / "query_contract.json"
    _write_json(path, contract)
    return path.relative_to(state.path).as_posix()


def load_query_contract(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    path = state.path / "references" / "query_contract.json"
    if not path.is_file():
        contract = build_query_contract(project)
        write_query_contract(project, contract)
        return contract
    try:
        import json

        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        payload = build_query_contract(project)
        write_query_contract(project, payload)
    return payload if isinstance(payload, dict) else build_query_contract(project)
