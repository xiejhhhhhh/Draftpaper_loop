"""Discipline and language routing for optional literature providers."""

from __future__ import annotations

from typing import Any, Iterable


PROVIDER_PROFILES: dict[str, dict[str, Any]] = {
    "openalex": {
        "disciplines": ["general", "discipline_unknown"],
        "wildcard": True,
        "priority": 90,
        "languages": ["zh-CN", "en"],
        "roles": ["problem_gap", "data_provenance", "method", "baseline"],
    },
    "pubmed": {
        "disciplines": ["medicine", "public_health", "life_science", "ecology", "bioinformatics"],
        "priority": 10,
        "languages": ["en"],
        "roles": ["problem_gap", "data_provenance", "method", "evaluation_standard"],
    },
    "europe_pmc": {
        "disciplines": ["medicine", "public_health", "life_science", "ecology", "bioinformatics"],
        "priority": 20,
        "languages": ["en"],
        "roles": ["problem_gap", "data_provenance", "method", "baseline"],
    },
    "dblp": {
        "disciplines": ["computer_science", "machine_learning"],
        "priority": 10,
        "languages": ["en"],
        "roles": ["method", "baseline", "evaluation_standard"],
    },
    "nasa_ads": {
        "disciplines": ["astronomy", "astrophysics", "physics"],
        "priority": 0,
        "languages": ["en"],
        "roles": ["problem_gap", "data_provenance", "method", "baseline"],
    },
}


def plan_provider_ids(contract: dict[str, Any], available: Iterable[str]) -> tuple[list[str], dict[str, str]]:
    disciplines = {str(value) for value in contract.get("discipline_hypotheses") or ["discipline_unknown"]}
    languages = {str(value) for value in contract.get("languages") or ["en"]}
    ranked: list[tuple[int, str]] = []
    decisions: dict[str, str] = {}
    for provider_id in available:
        profile = PROVIDER_PROFILES.get(provider_id, {})
        provider_disciplines = set(profile.get("disciplines") or [])
        provider_languages = set(profile.get("languages") or [])
        if not provider_disciplines:
            decisions[provider_id] = "unknown_provider_profile"
            continue
        exact_match = bool(disciplines & provider_disciplines)
        wildcard = bool(profile.get("wildcard"))
        if not (exact_match or wildcard):
            decisions[provider_id] = "skipped_discipline_mismatch"
            continue
        if provider_languages and not (languages & provider_languages):
            decisions[provider_id] = "skipped_language_mismatch"
            continue
        priority = int(profile.get("priority") or 50) + (0 if exact_match else 100)
        ranked.append((priority, provider_id))
        decisions[provider_id] = "planned_primary" if exact_match else "planned_supplemental"
    selected = [provider_id for _, provider_id in sorted(ranked)]
    return selected, decisions
