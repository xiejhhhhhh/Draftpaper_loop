from __future__ import annotations

import hashlib
import json

from draftpaper_cli.orchestrator import _gate_failure_action
from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.project_state import update_stage_status
from draftpaper_cli.writing_coordinator import section_lifecycle_action


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write_json(path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _accepted_results_project(tmp_path, *, active_text: str, candidate_text: str):
    project = create_project(root=tmp_path, idea="Accepted Results lifecycle", field="machine learning").path
    snapshot_id = "snapshot-current"
    candidate_hash = _sha256(candidate_text)
    (project / "research_plan" / "research_capability_contract.json").write_text("{}\n", encoding="utf-8")
    (project / "results" / "result_manifest.yaml").write_text('{"figures": []}\n', encoding="utf-8")
    (project / "results" / "results.tex").write_text(active_text, encoding="utf-8")
    (project / "results" / "figure_plugin_trace_report.json").write_text('{"decision": "pass"}\n', encoding="utf-8")
    (project / "writing" / "candidates").mkdir(parents=True, exist_ok=True)
    (project / "writing" / "candidates" / "results.tex").write_text(candidate_text, encoding="utf-8")
    _write_json(project / "results" / "promoted_evidence_snapshot.json", {"snapshot_id": snapshot_id})
    _write_json(
        project / "core_evidence" / "core_evidence_report.json",
        {"decision": "pass", "promoted_evidence_snapshot_id": snapshot_id},
    )
    _write_json(
        project / "writing" / "section_packets" / "results.json",
        {"promoted_evidence_snapshot": {"snapshot_id": snapshot_id}},
    )
    _write_json(
        project / "writing" / "section_validation" / "results.json",
        {
            "composition_mode": "codex_free_candidate",
            "decision": "pass",
            "quality_parity_eligible": True,
            "candidate_hash": candidate_hash,
            "evidence_snapshot_id": snapshot_id,
        },
    )
    _write_json(
        project / "writing" / "claim_bindings" / "results.json",
        {"status": "passed", "candidate_hash": candidate_hash, "evidence_snapshot_id": snapshot_id},
    )
    _write_json(
        project / "writing" / "scientific_editor" / "results.json",
        {"source_hash": candidate_hash, "decision": "pass"},
    )
    _write_json(
        project / "writing" / "section_acceptance" / "results.json",
        {
            "status": "accepted",
            "formal_release_eligible": True,
            "candidate_hash": candidate_hash,
            "evidence_snapshot_id": snapshot_id,
        },
    )
    update_stage_status(project, "results", "draft")
    return project


def test_accepted_candidate_must_be_installed_as_active_section(tmp_path) -> None:
    project = _accepted_results_project(
        tmp_path,
        active_text="Historical Results.\n",
        candidate_text="Accepted evidence-bound Results.\n",
    )

    action = section_lifecycle_action(project, "results")

    assert action is not None
    assert action["command"] == "write-results"
    assert action["writing_state"] == "accepted_candidate_installation_required"
    assert action["active_artifact"] == "results/results.tex"
    assert action["active_hash"] != action["candidate_hash"]


def test_discipline_review_cannot_run_against_stale_active_results(tmp_path) -> None:
    project = _accepted_results_project(
        tmp_path,
        active_text="Historical Results.\n",
        candidate_text="Accepted evidence-bound Results.\n",
    )

    action = _gate_failure_action(project)

    assert action is not None
    assert action["command"] == "write-results"


def test_matching_active_section_completes_candidate_lifecycle(tmp_path) -> None:
    text = "Accepted evidence-bound Results.\n"
    project = _accepted_results_project(tmp_path, active_text=text, candidate_text=text)

    assert section_lifecycle_action(project, "results") is None


def test_passed_results_review_routes_data_writing_before_methods_context(tmp_path) -> None:
    text = "Accepted evidence-bound Results.\n"
    project = _accepted_results_project(tmp_path, active_text=text, candidate_text=text)
    result_manifest = project / "results" / "result_manifest.yaml"
    trace = project / "results" / "figure_plugin_trace_report.json"
    _write_json(
        project / "review" / "result_discipline_review_report.json",
        {
            "decision": "pass",
            "results_sha256": hashlib.sha256((project / "results" / "results.tex").read_bytes()).hexdigest(),
            "evidence_snapshot_id": "snapshot-current",
            "result_manifest_sha256": hashlib.sha256(result_manifest.read_bytes()).hexdigest(),
            "figure_plugin_trace_sha256": hashlib.sha256(trace.read_bytes()).hexdigest(),
        },
    )
    intro = "Accepted Introduction.\n"
    intro_hash = _sha256(intro)
    (project / "introduction" / "introduction.tex").write_text(intro, encoding="utf-8")
    (project / "writing" / "candidates" / "introduction.tex").write_text(intro, encoding="utf-8")
    for relative, payload in {
        "writing/section_packets/introduction.json": {
            "promoted_evidence_snapshot": {"snapshot_id": "snapshot-current"}
        },
        "writing/section_validation/introduction.json": {
            "composition_mode": "codex_free_candidate",
            "decision": "pass",
            "quality_parity_eligible": True,
            "candidate_hash": intro_hash,
            "evidence_snapshot_id": "snapshot-current",
        },
        "writing/claim_bindings/introduction.json": {
            "status": "passed",
            "candidate_hash": intro_hash,
            "evidence_snapshot_id": "snapshot-current",
        },
        "writing/scientific_editor/introduction.json": {"source_hash": intro_hash, "decision": "pass"},
        "writing/section_acceptance/introduction.json": {
            "status": "accepted",
            "formal_release_eligible": True,
            "candidate_hash": intro_hash,
            "evidence_snapshot_id": "snapshot-current",
        },
    }.items():
        _write_json(project / relative, payload)
    _write_json(project / "data" / "data_writing_context.json", {"status": "written"})
    (project / "data" / "data.tex").write_text("Historical Data.\n", encoding="utf-8")
    update_stage_status(project, "data_writing", "draft")

    action = _gate_failure_action(project)

    assert action is not None
    assert action["command"] == "prepare-section-writing"
    assert action["section"] == "data"
