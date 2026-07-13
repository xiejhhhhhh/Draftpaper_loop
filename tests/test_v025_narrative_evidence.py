from __future__ import annotations

import json
from pathlib import Path

import pytest

from draftpaper_cli.evidence_resolver import EvidenceResolutionError, resolve_paragraph_evidence
from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.reference_usage import build_reference_usage_plan


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_formal_paragraph_resolution_rejects_first_n_fallback(tmp_path: Path) -> None:
    project = create_project(root=tmp_path, idea="No fallback", field="medicine").path
    _write(project / "writing" / "scientific_evidence_registry.json", {"records": [{"evidence_id": "unrelated", "entity_role": "result_metric_auc", "value": 0.8, "target_sections": ["discussion"]}]})
    with pytest.raises(EvidenceResolutionError, match="outline_evidence_gap"):
        resolve_paragraph_evidence(project, "discussion", outline={"evidence_resolution_mode": "strict", "paragraphs": [{"paragraph_id": "p1", "objective": "Write prose."}]})


def test_repeated_evidence_uses_content_address_refs_and_delta_packets(tmp_path: Path) -> None:
    project = create_project(root=tmp_path, idea="Evidence cache", field="engineering").path
    record = {"evidence_id": "metric-1", "entity_role": "result_metric_r2", "value": 0.8, "run_id": "run-1", "cohort_id": "main", "sample_unit": "sample", "model_id": "m1", "target_sections": ["discussion"]}
    _write(project / "writing" / "scientific_evidence_registry.json", {"records": [record]})
    outline = {"paragraphs": [{"paragraph_id": "p1", "required_evidence_ids": ["metric-1"]}, {"paragraph_id": "p2", "required_evidence_ids": ["metric-1"]}]}
    first = resolve_paragraph_evidence(project, "discussion", outline=outline)
    assert first["naive_estimated_tokens"] > first["estimated_tokens"]
    second = resolve_paragraph_evidence(project, "discussion", outline=outline)
    assert second["delta_paragraph_ids"] == []


def test_reference_usage_assigns_prewrite_v2_roles(tmp_path: Path) -> None:
    project = create_project(root=tmp_path, idea="Citation roles", field="astronomy").path
    (project / "references" / "library.bib").write_text("@article{Survey2025,title={Survey instrument catalog},year={2025}}", encoding="utf-8")
    _write(project / "references" / "literature_items.json", [{"bibtex_key": "Survey2025", "title": "Survey instrument catalog"}])
    (project / "references" / "citation_evidence.csv").write_text("citation_key,section,claim,evidence_summary\nSurvey2025,data,instrument product definition,The paper defines the detector product\n", encoding="utf-8")
    plan = build_reference_usage_plan(project)
    entry = plan["entries"][0]
    assert plan["citation_role_contract_version"] == "dpl.citation_role.v2"
    assert entry["citation_role"] == "instrument_or_product_definition"
    assert entry["role_assignment_source"] != "posthoc_keyword_inference"


def test_content_addressed_paragraph_packets_reduce_repeated_input_by_35_percent(tmp_path: Path) -> None:
    project = create_project(root=tmp_path, idea="Held-out token benchmark", field="engineering").path
    records = [
        {
            "evidence_id": f"evidence-{index}", "entity_role": "result_metric_validation_score",
            "value": index / 10, "run_id": "run-main", "cohort_id": "main", "sample_unit": "sample",
            "split": "held_out", "model_id": "model-main", "target_sections": ["discussion"],
            "claim_boundary": "Bound to the current held-out cohort and declared scientific interpretation.",
            "allowed_interpretation": "A repeated but necessary evidence description shared across paragraph jobs.",
        }
        for index in range(20)
    ]
    _write(project / "writing" / "scientific_evidence_registry.json", {"records": records})
    outline = {"paragraphs": [
        {"paragraph_id": f"discussion-{index}", "required_evidence_ids": [item["evidence_id"] for item in records]}
        for index in range(5)
    ]}
    report = resolve_paragraph_evidence(project, "discussion", outline=outline)
    assert report["token_reduction_fraction"] >= 0.35
    assert sum(len(item["evidence_ids"]) for item in report["slices"]) == 100
