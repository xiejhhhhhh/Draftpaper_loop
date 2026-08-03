"""Discipline and language routing for optional literature providers."""

from __future__ import annotations

from typing import Any, Iterable


PROVIDER_PROFILES: dict[str, dict[str, Any]] = {
    "openalex": {"disciplines": ["general", "social_science", "economics", "humanities", "geography", "law", "materials_science"], "languages": ["zh-CN", "en"], "roles": ["problem_gap", "data_provenance", "method", "baseline"]},
    "pubmed": {"disciplines": ["medicine", "life_science", "bioinformatics"], "languages": ["en"], "roles": ["problem_gap", "data_provenance", "method", "evaluation_standard"]},
    "europe_pmc": {"disciplines": ["medicine", "life_science", "bioinformatics"], "languages": ["en"], "roles": ["problem_gap", "data_provenance", "method", "baseline"]},
    "dblp": {"disciplines": ["computer_science", "machine_learning"], "languages": ["en"], "roles": ["method", "baseline", "evaluation_standard"]},
    "nasa_ads": {"disciplines": ["astronomy", "astrophysics", "physics"], "languages": ["en"], "roles": ["problem_gap", "data_provenance", "method", "baseline"]},
}


def plan_provider_ids(contract: dict[str, Any], available: Iterable[str]) -> tuple[list[str], dict[str, str]]:
    disciplines = {str(value) for value in contract.get("discipline_hypotheses") or ["general"]}
    languages = {str(value) for value in contract.get("languages") or ["en"]}
    selected: list[str] = []
    decisions: dict[str, str] = {}
    for provider_id in available:
        profile = PROVIDER_PROFILES.get(provider_id, {})
        provider_disciplines = set(profile.get("disciplines") or [])
        provider_languages = set(profile.get("languages") or [])
        if not provider_disciplines:
            decisions[provider_id] = "unknown_provider_profile"
            continue
        if not (disciplines & provider_disciplines or "general" in provider_disciplines):
            decisions[provider_id] = "skipped_discipline_mismatch"
            continue
        if provider_languages and not (languages & provider_languages):
            decisions[provider_id] = "skipped_language_mismatch"
            continue
        selected.append(provider_id)
        decisions[provider_id] = "planned"
    return selected, decisions
