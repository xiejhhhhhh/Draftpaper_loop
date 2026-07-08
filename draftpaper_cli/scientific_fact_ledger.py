# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .io_utils import read_json
from .observations import load_observations
from .project_scaffold import _write_json, utc_now
from .project_state import load_project


SCIENTIFIC_FACT_LEDGER_JSON = "writing/scientific_fact_ledger.json"


def _read_dict(path: Path) -> dict[str, Any]:
    payload = read_json(path, {})
    return payload if isinstance(payload, dict) else {}


def _compact_text(value: Any, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rsplit(" ", 1)[0].rstrip() + "..."


def _normalize_number(value: str) -> str:
    return str(value or "").replace(",", "").strip()


def _fact_id(role: str, text: str) -> str:
    stem = re.sub(r"[^a-z0-9]+", "_", f"{role}_{text}".lower()).strip("_")
    return stem[:90] or role


def _add_fact(
    facts: list[dict[str, Any]],
    *,
    role: str,
    text: str,
    value: str | int | float | None = None,
    target_sections: list[str] | None = None,
    evidence_source: str,
    must_preserve: bool = True,
) -> None:
    clean_text = _compact_text(text)
    if not clean_text:
        return
    clean_value = _normalize_number(str(value if value is not None else clean_text))
    identifier = _fact_id(role, clean_text)
    for item in facts:
        if item.get("id") == identifier or (item.get("role") == role and item.get("text") == clean_text):
            sources = item.setdefault("evidence_sources", [])
            if evidence_source not in sources:
                sources.append(evidence_source)
            return
    facts.append({
        "id": identifier,
        "role": role,
        "text": clean_text,
        "value": clean_value,
        "must_preserve": must_preserve,
        "target_sections": target_sections or ["data", "methods"],
        "evidence_sources": [evidence_source],
        "match_terms": _match_terms(role, clean_text, clean_value),
    })


def _match_terms(role: str, text: str, value: str) -> list[str]:
    terms = [text]
    if value:
        terms.append(value)
    if role == "class_balance":
        terms.extend(re.findall(r"\b\d+\s+(?:AGN|XRB|TDE)\b", text, flags=re.I))
    return list(dict.fromkeys(term for term in terms if term))


def _observation_blob(project_path: Path) -> str:
    records = load_observations(project_path)
    return " ".join(str(item.get("text") or "") for item in records if isinstance(item, dict))


def _extract_text_facts(facts: list[dict[str, Any]], blob: str, *, evidence_source: str) -> None:
    for role, pattern, suffix in [
        ("event_count", r"\b(\d[\d,]*)\s+(?:events?|event-level samples?)\b", "events"),
        ("source_count", r"\b(\d[\d,]*)\s+(?:sources?|objects?)\b", "sources"),
    ]:
        match = re.search(pattern, blob, flags=re.I)
        if match:
            value = _normalize_number(match.group(1))
            _add_fact(facts, role=role, value=value, text=f"{value} {suffix}", evidence_source=evidence_source)
    token_match = re.search(r"\b(\d+(?:\.\d+)?\s*(?:M|million)|\d[\d,]*)\s+(?:token bins?|tokens?)\b", blob, flags=re.I)
    if token_match:
        token_text = re.sub(r"\s+", "", token_match.group(1)).replace("million", "M")
        _add_fact(
            facts,
            role="token_bin_count",
            value=token_text,
            text=f"{token_text} token bins",
            evidence_source=evidence_source,
        )
    balance = re.search(r"\b(\d+)\s*AGN\s*(?:/|and|,)?\s*(\d+)\s*XRB\b", blob, flags=re.I)
    if balance:
        _add_fact(
            facts,
            role="class_balance",
            value=f"{balance.group(1)}:{balance.group(2)}",
            text=f"{balance.group(1)} AGN and {balance.group(2)} XRB sources",
            evidence_source=evidence_source,
        )
    if re.search(r"\bTDE\b", blob, flags=re.I):
        _add_fact(
            facts,
            role="stress_test_boundary",
            value="TDE",
            text="TDE cases are used only as stress-testing or boundary-evaluation evidence unless the verified design states otherwise",
            target_sections=["data", "methods", "discussion"],
            evidence_source=evidence_source,
        )


def _extract_key_fact_file(facts: list[dict[str, Any]], payload: dict[str, Any]) -> None:
    mapping = {
        "event_count": ("event_count", "events"),
        "source_count": ("source_count", "sources"),
        "token_bin_count": ("token_bin_count", "token bins"),
        "main_modeling_sample": ("main_modeling_sample", "main modeling records"),
        "token_record_count": ("token_record_count", "token-level records"),
    }
    for key, (role, suffix) in mapping.items():
        value = payload.get(key)
        if value:
            _add_fact(facts, role=role, value=value, text=f"{value} {suffix}", evidence_source="data/data_key_facts.json")
    if payload.get("class_balance"):
        _add_fact(facts, role="class_balance", text=str(payload.get("class_balance")), evidence_source="data/data_key_facts.json")
    if payload.get("stress_test_boundary"):
        _add_fact(
            facts,
            role="stress_test_boundary",
            value="stress_test_boundary",
            text=str(payload.get("stress_test_boundary")),
            target_sections=["data", "methods", "discussion"],
            evidence_source="data/data_key_facts.json",
        )


def _extract_result_facts(facts: list[dict[str, Any]], manifest: dict[str, Any]) -> None:
    entries = list(manifest.get("main_figures") or manifest.get("figures") or [])
    entries.extend(manifest.get("tables") or [])
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        metrics = entry.get("metrics") if isinstance(entry.get("metrics"), dict) else {}
        for key, label in [("f1", "F1"), ("f1_macro", "macro F1"), ("auc", "AUC"), ("roc_auc", "AUC"), ("accuracy", "accuracy")]:
            value = metrics.get(key)
            if value not in {None, ""}:
                try:
                    rendered = f"{float(value):.3g}"
                except (TypeError, ValueError):
                    rendered = str(value)
                _add_fact(
                    facts,
                    role=f"result_metric_{key}",
                    value=rendered,
                    text=f"{label}={rendered}",
                    target_sections=["results", "discussion"],
                    evidence_source="results/result_manifest.yaml",
                )


def build_scientific_fact_ledger(project: str | Path) -> dict[str, Any]:
    """Build a manuscript-facing ledger of scientific facts that writers must preserve."""
    state = load_project(project)
    facts: list[dict[str, Any]] = []
    data_key_facts = _read_dict(state.path / "data" / "data_key_facts.json")
    if data_key_facts:
        _extract_key_fact_file(facts, data_key_facts)
    inventory = _read_dict(state.path / "data" / "data_inventory.json")
    for key in ["description", "summary"]:
        if inventory.get(key):
            _extract_text_facts(facts, str(inventory.get(key)), evidence_source="data/data_inventory.json")
    blob = _observation_blob(state.path)
    if blob:
        _extract_text_facts(facts, blob, evidence_source="observations/observations.jsonl")
    result_manifest = _read_dict(state.path / "results" / "result_manifest.yaml")
    if result_manifest:
        _extract_result_facts(facts, result_manifest)
    ledger = {
        "status": "written",
        "schema_version": "v0.17.0",
        "generated_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "fact_count": len(facts),
        "must_preserve_count": sum(1 for item in facts if item.get("must_preserve")),
        "facts": facts,
    }
    output_path = state.path / SCIENTIFIC_FACT_LEDGER_JSON
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(output_path, ledger)
    return ledger


def load_or_build_scientific_fact_ledger(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    path = state.path / SCIENTIFIC_FACT_LEDGER_JSON
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            pass
    return build_scientific_fact_ledger(state.path)


def fact_summary_for_sections(ledger: dict[str, Any], sections: set[str]) -> str:
    parts: list[str] = []
    for item in ledger.get("facts") or []:
        if not isinstance(item, dict) or not item.get("must_preserve"):
            continue
        targets = {str(section) for section in item.get("target_sections") or []}
        if targets and not (targets & sections):
            continue
        text = str(item.get("text") or "").strip()
        if text and text not in parts:
            parts.append(text)
    if not parts:
        return ""
    return "The manuscript must preserve these scientific facts: " + "; ".join(parts[:8]) + "."

