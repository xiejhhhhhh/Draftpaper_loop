from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from draftpaper_cli.evidence_binding import (
    EvidenceBindingError,
    apply_evidence_rebind,
    inspect_evidence_bindings,
    prepare_evidence_rebind,
)
from draftpaper_cli.evidence_registry import build_scientific_evidence_registry
from draftpaper_cli.project_scaffold import create_project


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _binding_payload(source: Path, relative: str) -> dict[str, object]:
    return {
        "bindings": [
            {
                "source_artifact": relative,
                "source_hash": _sha256(source),
                "source_locator": "rows[0].macro_f1",
                "entity_role": "result_metric_macro_f1",
                "value": 0.81,
                "estimand_id": "estimand-main",
                "cohort_view_id": "cohort-main",
                "analysis_spec_id": "analysis-v1",
                "run_id": "run-legacy",
                "sample_unit": "source",
                "split_id": "test",
                "model_id": "model-a",
                "metric_dimension": "score",
                "aggregation": "macro",
            }
        ]
    }


def test_binding_receipt_is_immutable_source_of_registry_rows(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="receipt", field="astronomy").path
    source = project / "results" / "tables" / "legacy.json"
    source.write_text('{"macro_f1": 0.81}\n', encoding="utf-8")
    input_file = tmp_path / "bindings.json"
    _write(input_file, _binding_payload(source, "results/tables/legacy.json"))

    prepared = prepare_evidence_rebind(project, binding_file=str(input_file))
    packet_path = Path(prepared["packet_path"])
    applied = apply_evidence_rebind(
        project,
        packet_path=str(packet_path),
        packet_hash=str(prepared["packet_hash"]),
    )

    assert applied["status"] == "applied"
    assert applied["binding_ready"] is True
    assert applied["release_eligible"] is False
    registry = build_scientific_evidence_registry(project)
    rows = [row for row in registry["records"] if row.get("binding_source") == "output_binding_receipt"]
    assert len(rows) == 1
    assert rows[0]["binding_status"] == "verified"
    assert rows[0]["source_hash"] == _sha256(source)
    assert registry["binding_receipt_count"] == 1
    assert inspect_evidence_bindings(project)["status"] == "ready"


def test_changed_source_cannot_reuse_old_binding_packet(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="stale receipt", field="astronomy").path
    source = project / "results" / "tables" / "legacy.json"
    source.write_text('{"macro_f1": 0.81}\n', encoding="utf-8")
    input_file = tmp_path / "bindings.json"
    _write(input_file, _binding_payload(source, "results/tables/legacy.json"))
    prepared = prepare_evidence_rebind(project, binding_file=str(input_file))
    apply_evidence_rebind(
        project,
        packet_path=str(prepared["packet_path"]),
        packet_hash=str(prepared["packet_hash"]),
    )

    source.write_text('{"macro_f1": 0.91}\n', encoding="utf-8")
    inspection = inspect_evidence_bindings(project)
    assert inspection["status"] == "repair_required"
    assert inspection["stale_receipt_count"] == 1
    registry = build_scientific_evidence_registry(project)
    assert registry["binding_receipt_stale_count"] == 1
    stale = [row for row in registry["records"] if row.get("binding_source") == "output_binding_receipt"]
    assert stale[0]["binding_status"] == "stale"
    assert stale[0]["binding_complete"] is False

    with pytest.raises(EvidenceBindingError, match="hash mismatch"):
        apply_evidence_rebind(
            project,
            packet_path=str(prepared["packet_path"]),
            packet_hash=str(prepared["packet_hash"]),
        )


def test_binding_input_hash_mismatch_is_rejected_before_packet_creation(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="invalid receipt", field="astronomy").path
    source = project / "results" / "tables" / "legacy.json"
    source.write_text('{"macro_f1": 0.81}\n', encoding="utf-8")
    input_file = tmp_path / "bindings.json"
    payload = _binding_payload(source, "results/tables/legacy.json")
    payload["bindings"][0]["source_hash"] = "0" * 64
    _write(input_file, payload)

    with pytest.raises(EvidenceBindingError, match="hash mismatch"):
        prepare_evidence_rebind(project, binding_file=str(input_file))


def test_incomplete_binding_blocks_quality_gate_without_becoming_a_scientific_conflict(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="incomplete binding", field="astronomy").path
    _write(
        project / "data" / "data_key_facts.json",
        {
            "evidence_records": [
                {
                    "entity_role": "result_metric_macro_f1",
                    "value": 0.81,
                    "sample_unit": "source",
                    "metric_dimension": "score",
                }
            ]
        },
    )

    from draftpaper_cli.quality_gate import check_scientific_evidence_registry

    report = check_scientific_evidence_registry(project)
    assert report["status"] == "failed"
    assert report["binding_blocked"] is True
    assert report["incomplete_binding_count"] == 1
    assert report["blocking_conflict_count"] == 0
