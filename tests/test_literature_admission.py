from __future__ import annotations

import json
from pathlib import Path

import pytest

from draftpaper_cli.literature_admission import (
    ACTIVE_LITERATURE_PATH,
    ADMISSION_DECISION_SCHEMA,
    ADMISSION_PACKET_PATH,
    LiteratureAdmissionError,
    activate_literature_corpus,
    build_literature_admission_packet,
)
from draftpaper_cli.project_scaffold import create_project


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _project(tmp_path: Path) -> Path:
    project = create_project(
        root=tmp_path / "projects",
        idea="Auditable wheat evidence workflow",
        field="crop remote sensing",
    ).path
    references = project / "references"
    _write(
        references / "literature_items.json",
        {
            "items": [
                {
                    "bibtex_key": "Accepted2024",
                    "canonical_work_id": "doi:10.1000/accepted",
                    "title": "A crop evidence paper",
                    "year": "2024",
                    "candidate_state": "relevance_passed",
                    "gate_state": "review_required",
                    "citation_eligibility": "not_eligible_pending_review",
                    "role_evidence": {"method": {"supported": True}},
                },
                {
                    "bibtex_key": "Rejected2024",
                    "canonical_work_id": "doi:10.1000/rejected",
                    "title": "A quarantined candidate",
                    "year": "2024",
                    "candidate_state": "review_required",
                    "gate_state": "rejected",
                    "citation_eligibility": "not_eligible_pending_review",
                },
            ]
        },
    )
    _write(
        references / "reference_registry.json",
        {
            "schema_version": "dpl.reference_registry.v1",
            "project_id": "fixture",
            "records": [
                {
                    "citation_key": "Accepted2024",
                    "canonical_work_id": "doi:10.1000/accepted",
                    "title_original": "A crop evidence paper",
                    "year": "2024",
                },
                {
                    "citation_key": "Rejected2024",
                    "canonical_work_id": "doi:10.1000/rejected",
                    "title_original": "A quarantined candidate",
                    "year": "2024",
                },
            ],
        },
    )
    _write(
        references / "reference_usage_plan.json",
        {
            "entries": [
                {
                    "citation_key": "Accepted2024",
                    "required": True,
                    "citation_role": "method_or_tool_background",
                    "target_section": "methods",
                    "citation_intent": "defines the auditable method context",
                },
                {
                    "citation_key": "Rejected2024",
                    "citation_role": "method_or_tool_background",
                    "target_section": "methods",
                },
            ]
        },
    )
    _write(references / "literature_snapshot.json", {"snapshot_hash": "sha256:fixture"})
    return project


def _decisions(packet_hash: str, *, accept_rejected: bool = False) -> dict[str, object]:
    rejected = {
        "citation_key": "Rejected2024",
        "decision": "accept" if accept_rejected else "exclude",
        "reason": "保留或排除该候选的项目角色和证据边界已明确记录。",
    }
    if accept_rejected:
        rejected["gate_override"] = True
    return {
        "schema_version": ADMISSION_DECISION_SCHEMA,
        "packet_hash": packet_hash,
        "decision_mode": "test_explicit_manifest",
        "decided_by": "test-agent",
        "decisions": [
            {
                "citation_key": "Accepted2024",
                "decision": "accept",
                "reason": "与当前研究方法角色直接相关，保留其方法证据边界。",
            },
            rejected,
        ],
    }


def test_prepare_packet_requires_explicit_decisions_and_hash_binds_sources(tmp_path: Path) -> None:
    project = _project(tmp_path)

    result = build_literature_admission_packet(project)

    packet = json.loads((project / ADMISSION_PACKET_PATH).read_text(encoding="utf-8"))
    assert result["candidate_count"] == 2
    assert packet["packet_hash"] == result["packet_hash"]
    assert packet["source_binding"]["literature_items.json"].startswith("sha256:")
    assert {row["recommended_decision"] for row in packet["candidates"]} == {"review_required", "exclude"}


def test_activation_writes_only_explicitly_accepted_items(tmp_path: Path) -> None:
    project = _project(tmp_path)
    packet = build_literature_admission_packet(project)
    decision_path = tmp_path / "decisions.json"
    _write(decision_path, _decisions(str(packet["packet_hash"])))

    result = activate_literature_corpus(
        project,
        packet_hash=str(packet["packet_hash"]),
        decision_file=str(decision_path),
    )

    active = json.loads((project / ACTIVE_LITERATURE_PATH).read_text(encoding="utf-8"))
    receipt = json.loads((project / "references" / "literature_admission_receipt.json").read_text(encoding="utf-8"))
    assert result["accepted_work_count"] == 1
    assert [item["bibtex_key"] for item in active["items"]] == ["Accepted2024"]
    assert receipt["excluded_citation_keys"] == ["Rejected2024"]
    assert active["policy"]["requires_confirm_literature_corpus"] is True


def test_activation_rejects_incomplete_decision_manifest(tmp_path: Path) -> None:
    project = _project(tmp_path)
    packet = build_literature_admission_packet(project)
    decision_path = tmp_path / "decisions.json"
    _write(
        decision_path,
        {
            "schema_version": ADMISSION_DECISION_SCHEMA,
            "packet_hash": packet["packet_hash"],
            "decisions": [],
        },
    )

    with pytest.raises(LiteratureAdmissionError, match="missing"):
        activate_literature_corpus(project, packet_hash=str(packet["packet_hash"]), decision_file=str(decision_path))


def test_gate_rejected_acceptance_requires_explicit_override(tmp_path: Path) -> None:
    project = _project(tmp_path)
    packet = build_literature_admission_packet(project)
    decision_path = tmp_path / "decisions.json"
    _write(decision_path, _decisions(str(packet["packet_hash"]), accept_rejected=True))

    result = activate_literature_corpus(
        project,
        packet_hash=str(packet["packet_hash"]),
        decision_file=str(decision_path),
    )

    active = json.loads((project / ACTIVE_LITERATURE_PATH).read_text(encoding="utf-8"))
    assert result["accepted_work_count"] == 2
    assert all(item["admission_gate_override"] for item in active["items"] if item["bibtex_key"] == "Rejected2024")
