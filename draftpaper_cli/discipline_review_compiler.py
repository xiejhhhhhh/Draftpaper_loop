"""Compile post-Results discipline rules from the current semantic evidence graph."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


def _read(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def compile_discipline_review_inputs(project: str | Path) -> dict[str, Any]:
    root = Path(project)
    claim_map = _read(root / "writing" / "claim_maps" / "results.json") or _read(root / "writing" / "claim_bindings" / "results.json")
    figure_gate = _read(root / "results" / "figure_contract_gate_report.json")
    result_manifest = _read(root / "results" / "result_manifest.yaml")
    trace = _read(root / "results" / "figure_plugin_trace_report.json")
    registry = _read(root / "writing" / "scientific_evidence_registry.json")
    analysis = _read(root / "methods" / "executable_analysis_spec.json")
    outline = _read(root / "writing" / "section_outlines" / "results.json")
    results_path = root / "results" / "results.tex"
    results_text = results_path.read_text(encoding="utf-8-sig") if results_path.exists() else ""
    results_hash = hashlib.sha256(results_path.read_bytes()).hexdigest() if results_path.exists() else ""
    evidence_index = {str(item.get("evidence_id")): item for item in registry.get("records") or [] if isinstance(item, dict) and item.get("evidence_id")}
    figure_index = {str(item.get("figure_id")): item for item in figure_gate.get("contract_checks") or [] if isinstance(item, dict) and item.get("figure_id")}
    figure_aliases = {}
    for item in result_manifest.get("figures") or result_manifest.get("main_figures") or []:
        if not isinstance(item, dict):
            continue
        artifact_id = str(item.get("id") or "").strip()
        storyboard_id = str(item.get("storyboard_id") or item.get("figure_group") or "").strip()
        if artifact_id and storyboard_id:
            figure_aliases[artifact_id] = storyboard_id
    trace_index = {str(item.get("figure_id")): item for item in trace.get("figure_checks") or [] if isinstance(item, dict) and item.get("figure_id")}
    spec_index = {str(item.get("analysis_spec_id")): item for item in analysis.get("analysis_specs") or [] if isinstance(item, dict) and item.get("analysis_spec_id")}
    outline_rows = [item for item in outline.get("paragraphs") or [] if isinstance(item, dict)]
    ordered_figure_ids = list(figure_index)
    sentence_figure_ids: dict[str, str] = {}
    for paragraph in [item.strip() for item in re.split(r"\n\s*\n", results_text) if item.strip()]:
        match = re.search(r"Figure\s*~?\s*(\d+)", paragraph, flags=re.I)
        if not match:
            continue
        position = int(match.group(1)) - 1
        if not 0 <= position < len(ordered_figure_ids):
            continue
        figure_id = ordered_figure_ids[position]
        for sentence in [item.strip() for item in re.split(r"(?<=[.!?])\s+|\n\s*\n", paragraph) if item.strip()]:
            sentence_figure_ids[hashlib.sha256(sentence.encode("utf-8")).hexdigest()] = figure_id
    binding_evidence_by_sentence: dict[str, list[str]] = {}
    for binding in claim_map.get("bindings") or []:
        if not isinstance(binding, dict) or not binding.get("sentence"):
            continue
        sentence_hash = hashlib.sha256(str(binding["sentence"]).strip().encode("utf-8")).hexdigest()
        evidence_id = binding.get("evidence_id") or (
            (binding.get("binding") or {}).get("evidence_id")
            if isinstance(binding.get("binding"), dict) else None
        )
        if evidence_id:
            binding_evidence_by_sentence.setdefault(sentence_hash, []).append(str(evidence_id))
    rows = []
    for claim in claim_map.get("section_claims") or []:
        if not isinstance(claim, dict):
            continue
        sentence_hash = str(claim.get("sentence_hash") or "")
        evidence_ids = list(dict.fromkeys([
            *[str(item) for item in claim.get("evidence_ids") or []],
            *binding_evidence_by_sentence.get(sentence_hash, []),
        ]))
        evidence = [evidence_index[item] for item in evidence_ids if item in evidence_index]
        figure_ids = sorted({
            figure_aliases.get(str(figure_id), str(figure_id))
            for item in evidence
            for figure_id in item.get("figure_ids") or []
            if figure_id
        })
        if not figure_ids and sentence_hash in sentence_figure_ids:
            figure_ids = [sentence_figure_ids[sentence_hash]]
        if not figure_ids and evidence_ids and outline_rows:
            # Result evidence records can predate figure-level semantic IDs.
            # Recover the binding only when the claim's evidence intersects one
            # paragraph-level outline row unambiguously; broad union evidence
            # (section headings and introductory framing) is omitted rather
            # than assigned to an arbitrary figure.
            overlaps = []
            evidence_set = set(evidence_ids)
            for row in outline_rows:
                required = {str(item) for item in row.get("required_evidence_ids") or [] if str(item).strip()}
                links = [
                    figure_aliases.get(str(item), str(item))
                    for item in row.get("figure_or_table_links") or []
                    if str(item).startswith("fig_")
                ]
                overlap = evidence_set & required
                if overlap and links:
                    overlaps.append((len(overlap), links))
            if overlaps:
                best = max(score for score, _links in overlaps)
                winners = [links for score, links in overlaps if score == best]
                winner_ids = sorted({figure_id for links in winners for figure_id in links})
                if len(winner_ids) == 1:
                    figure_ids = winner_ids
        # Claim-map rows for section framing or unlinked layout commands may
        # carry a union of all evidence IDs. They are not discipline claims and
        # cannot satisfy the required figure-level semantic identity.
        if not figure_ids:
            continue
        for figure_id in figure_ids or [""]:
            figure = figure_index.get(figure_id, {})
            plugin_trace = trace_index.get(figure_id, {})
            analysis_spec_id = str(figure.get("analysis_spec_id") or next((item.get("analysis_spec_id") for item in evidence if item.get("analysis_spec_id")), ""))
            spec = spec_index.get(analysis_spec_id, {})
            rows.append({
                "claim_id": claim.get("section_claim_id"),
                "results_sentence_hash": claim.get("sentence_hash"),
                "figure_id": figure_id or None,
                "panel_ids": list(figure.get("panel_ids") or []),
                "cohort_view_id": figure.get("cohort_view_id") or spec.get("cohort_view_id"),
                "estimand_id": figure.get("estimand_id") or spec.get("estimand_id"),
                "analysis_spec_id": analysis_spec_id or None,
                "run_ids": sorted({str(item.get("run_id")) for item in evidence if item.get("run_id")}),
                "data_plugin_ids": list(plugin_trace.get("data_plugin_ids") or []),
                "method_plugin_ids": list(plugin_trace.get("method_plugin_ids") or []),
                "evidence_ids": evidence_ids,
                "threshold_source": spec.get("threshold_selection") or "analysis_spec",
            })
    issues = []
    for row in rows:
        for field in ("claim_id", "results_sentence_hash", "cohort_view_id", "estimand_id", "analysis_spec_id"):
            if not row.get(field):
                issues.append({"code": f"missing_{field}", "claim_id": row.get("claim_id"), "figure_id": row.get("figure_id")})
    return {
        "schema_version": "dpl.discipline_review_compiler.v1",
        "results_sha256": results_hash,
        "decision": "repair_required" if issues else "pass",
        "claim_inputs": rows,
        "issues": issues,
        "policy": "Discipline rules consume claim-level IDs compiled from the current Results, figure contract, capability trace, analysis spec, run and evidence registry. They are not rerun later with inferred role aliases.",
    }
