"""Composable research capability packs and held-out routing evaluation."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


PACK_SCHEMA = "dpl.research_capability_pack.v1"
PACK_ROOT = Path(__file__).resolve().parent / "capability_packs"
REQUIRED_FIELDS = {
    "pack_id",
    "version",
    "owner_discipline",
    "capability_family",
    "data_plugin_ids",
    "method_plugin_ids",
    "review_plugin_ids",
    "input_roles",
    "output_roles",
    "minimum_runtime_level",
    "routing_triggers",
    "forbidden_triggers",
    "failure_modes",
    "provenance",
}


class CapabilityPackError(RuntimeError):
    """Raised when a capability pack or routing evaluation is invalid."""


def _tokens(value: object) -> set[str]:
    normalized = re.sub(r"[^a-z0-9]+", " ", str(value or "").lower())
    return {item for item in normalized.split() if len(item) > 1}


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CapabilityPackError(f"Invalid capability pack manifest {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise CapabilityPackError(f"Capability pack manifest must be an object: {path}")
    return payload


def validate_capability_pack(payload: dict[str, Any], *, source: str = "<memory>") -> list[str]:
    issues = [f"missing:{field}" for field in sorted(REQUIRED_FIELDS) if payload.get(field) in (None, "", [])]
    if payload.get("schema_version") != PACK_SCHEMA:
        issues.append("unsupported_schema")
    if payload.get("minimum_runtime_level") not in {
        "contract_only",
        "code_generator",
        "fixture_executed",
        "project_validated",
        "live_validated",
    }:
        issues.append("invalid_minimum_runtime_level")
    if issues:
        raise CapabilityPackError(f"Invalid capability pack {source}: {', '.join(issues)}")
    return issues


def discover_capability_packs(root: str | Path | None = None) -> list[dict[str, Any]]:
    base = Path(root).expanduser().resolve() if root else PACK_ROOT
    packs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in sorted(base.glob("*/manifest.json")):
        payload = _load_json(path)
        validate_capability_pack(payload, source=str(path))
        pack_id = str(payload["pack_id"])
        if pack_id in seen:
            raise CapabilityPackError(f"Duplicate capability pack id: {pack_id}")
        seen.add(pack_id)
        payload["manifest_path"] = path.relative_to(base.parent).as_posix()
        packs.append(payload)
    return packs


def capability_ownership_map(packs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    resolved = packs or discover_capability_packs()
    plugin_disciplines: dict[str, str] = {}
    discipline_root = Path(__file__).resolve().parent / "discipline_modules"
    for manifest_path in discipline_root.glob("*/*/*/manifest.json"):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        for key in ("connector_id", "template_id", "rule_id", "rule_group_id"):
            if manifest.get(key):
                plugin_disciplines[str(manifest[key])] = str(manifest.get("discipline") or manifest_path.parts[-4])
    ownership: dict[str, dict[str, Any]] = {}
    conflicts: list[dict[str, Any]] = []
    for pack in resolved:
        for kind, key in (("data", "data_plugin_ids"), ("method", "method_plugin_ids"), ("review", "review_plugin_ids")):
            for plugin_id in pack.get(key) or []:
                value = str(plugin_id)
                owner = ownership.get(value)
                record = {
                    "plugin_id": value,
                    "kind": kind,
                    "authoritative_owner": plugin_disciplines.get(value, str(pack["owner_discipline"])),
                    "consumer_packs": [pack["pack_id"]],
                }
                if owner and owner["kind"] != kind:
                    conflicts.append({"plugin_id": value, "reason": "plugin_kind_conflict", "kinds": sorted({owner["kind"], kind})})
                    continue
                if owner:
                    owner["consumer_packs"] = sorted(set(owner["consumer_packs"] + [pack["pack_id"]]))
                    owner["shared_capability"] = len(owner["consumer_packs"]) > 1
                else:
                    record["shared_capability"] = False
                    ownership[value] = record
    return {"ownership": ownership, "conflicts": conflicts}


def route_capability_requirement(
    requirement: dict[str, Any],
    *,
    primary_discipline: str,
    secondary_disciplines: list[str] | None = None,
    packs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    resolved = packs or discover_capability_packs()
    disciplines = {primary_discipline, *(secondary_disciplines or [])}
    target_text = " ".join(
        str(requirement.get(key) or "")
        for key in ("role", "method_family", "research_question", "kind")
    )
    target_tokens = _tokens(target_text)
    ranked: list[dict[str, Any]] = []
    for pack in resolved:
        triggers = {str(item).lower() for item in pack.get("routing_triggers") or []}
        forbidden = {str(item).lower() for item in pack.get("forbidden_triggers") or []}
        trigger_tokens = set().union(*(_tokens(item) for item in triggers)) if triggers else set()
        forbidden_hits = sorted(item for item in forbidden if item and item in target_text.lower())
        if forbidden_hits:
            continue
        overlap = target_tokens & trigger_tokens
        discipline_score = 5 if pack.get("owner_discipline") in disciplines else 0
        secondary_score = sum(2 for item in pack.get("secondary_disciplines") or [] if item in disciplines)
        role_score = 3 * len(overlap)
        exact_match = any(item and item in target_text.lower() for item in triggers)
        exact_score = 8 if exact_match else 0
        if not discipline_score and not secondary_score and not exact_match and len(overlap) < 2:
            continue
        score = discipline_score + secondary_score + role_score + exact_score
        if score and (role_score or exact_score):
            ranked.append(
                {
                    "pack_id": pack["pack_id"],
                    "score": score,
                    "owner_discipline": pack["owner_discipline"],
                    "matched_tokens": sorted(overlap),
                    "minimum_runtime_level": pack["minimum_runtime_level"],
                    "plugin_ids": {
                        "data": list(pack.get("data_plugin_ids") or []),
                        "method": list(pack.get("method_plugin_ids") or []),
                        "review": list(pack.get("review_plugin_ids") or []),
                    },
                }
            )
    ranked.sort(key=lambda item: (-int(item["score"]), str(item["pack_id"])))
    if not ranked:
        return {"status": "unrouted", "selected_pack_id": None, "alternatives": []}
    ambiguous = len(ranked) > 1 and ranked[0]["score"] == ranked[1]["score"]
    return {
        "status": "ambiguous" if ambiguous else "routed",
        "selected_pack_id": None if ambiguous else ranked[0]["pack_id"],
        "selected": None if ambiguous else ranked[0],
        "alternatives": ranked[:5],
    }


def evaluate_capability_routing(root: str | Path | None = None) -> dict[str, Any]:
    base = Path(root).expanduser().resolve() if root else PACK_ROOT
    packs = discover_capability_packs(base)
    cases: list[dict[str, Any]] = []
    for path in sorted(base.glob("*/routing_eval.jsonl")):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                case = json.loads(line)
            except json.JSONDecodeError as exc:
                raise CapabilityPackError(f"Invalid routing eval {path}:{line_number}: {exc}") from exc
            routed = route_capability_requirement(
                dict(case.get("requirement") or {}),
                primary_discipline=str(case.get("primary_discipline") or "default"),
                secondary_disciplines=[str(item) for item in case.get("secondary_disciplines") or []],
                packs=packs,
            )
            expected = case.get("expected_pack_id")
            cases.append(
                {
                    "case_id": case.get("case_id") or f"{path.parent.name}:{line_number}",
                    "expected_pack_id": expected,
                    "selected_pack_id": routed.get("selected_pack_id"),
                    "passed": routed.get("selected_pack_id") == expected,
                    "routing_status": routed.get("status"),
                }
            )
    passed = sum(item["passed"] for item in cases)
    true_positive = sum(bool(item["expected_pack_id"]) and item["passed"] for item in cases)
    false_positive = sum(not item["expected_pack_id"] and bool(item["selected_pack_id"]) for item in cases)
    false_negative = sum(bool(item["expected_pack_id"]) and not item["selected_pack_id"] for item in cases)
    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 1.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 1.0
    return {
        "status": "passed" if cases and passed == len(cases) else "failed",
        "case_count": len(cases),
        "passed_count": passed,
        "accuracy": passed / len(cases) if cases else 0.0,
        "precision": precision,
        "recall": recall,
        "cases": cases,
        "ownership": capability_ownership_map(packs),
    }
