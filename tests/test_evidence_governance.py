from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from draftpaper_cli.evidence_binding import (
    EvidenceBindingError,
    apply_evidence_rebind,
    prepare_evidence_rebind,
)
from draftpaper_cli.governance_contract import evaluate_governance
from draftpaper_cli.passport import refresh_project_passport
from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.revision_cycle import (
    RevisionCycleError,
    begin_revision_cycle,
    close_revision_cycle,
    prepare_revision_reconciliation,
)
from draftpaper_cli.scientific_baseline import (
    ACTIVE_POINTER,
    ScientificBaselineError,
    create_scientific_baseline,
    read_baseline_state,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _binding_input(source: Path, value: float) -> dict[str, object]:
    return {
        "bindings": [
            {
                "source_artifact": "results/tables/metrics.json",
                "source_hash": _sha256(source),
                "source_locator": "/macro_f1",
                "entity_role": "result_metric_macro_f1",
                "value": value,
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


def test_tex_numeric_change_requires_scientific_review(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="numeric edit", field="astronomy").path
    source = project / "latex" / "main.tex"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("Accuracy is 0.81.\n", encoding="utf-8")
    refresh_project_passport(project, event="fixture")
    begin_revision_cycle(project, mode="author_edit")
    source.write_text("Accuracy is 0.98.\n", encoding="utf-8")

    prepared = prepare_revision_reconciliation(project)
    packet = json.loads(Path(prepared["reconciliation_path"]).read_text(encoding="utf-8"))
    row = next(item for item in packet["changes"] if item["path"] == "latex/main.tex")

    assert row["scientific_semantics_changed"] is True
    assert prepared["reconciliation_status"] == "awaiting_decision"


def test_tex_formatting_wrapper_does_not_reopen_science(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="style edit", field="astronomy").path
    source = project / "latex" / "main.tex"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("Accuracy is 0.81.\n", encoding="utf-8")
    refresh_project_passport(project, event="fixture")
    begin_revision_cycle(project, mode="author_edit")
    source.write_text(r"\textbf{Accuracy} is 0.81." + "\n", encoding="utf-8")
    prepared = prepare_revision_reconciliation(project)
    packet = json.loads(Path(prepared["reconciliation_path"]).read_text(encoding="utf-8"))
    row = next(item for item in packet["changes"] if item["path"] == "latex/main.tex")
    assert row["scientific_semantics_changed"] is False


def test_corrupt_baseline_is_not_reinitialized(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="corrupt baseline", field="astronomy").path
    original = create_scientific_baseline(project)["baseline"]["baseline_id"]
    pointer = project / ACTIVE_POINTER
    pointer.write_text("{broken", encoding="utf-8")

    with pytest.raises(ScientificBaselineError):
        begin_revision_cycle(project, mode="author_edit")

    assert pointer.read_text(encoding="utf-8") == "{broken"
    assert original


def test_missing_pointer_with_history_is_not_first_initialization(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="missing baseline pointer", field="astronomy").path
    create_scientific_baseline(project)
    (project / ACTIVE_POINTER).unlink()
    state = read_baseline_state(project)
    assert state["status"] == "missing"
    with pytest.raises(ScientificBaselineError):
        begin_revision_cycle(project, mode="author_edit")


def test_direct_edit_invalidates_close(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="close gate", field="astronomy").path
    source = project / "methods" / "probe.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("value = 1\n", encoding="utf-8")
    refresh_project_passport(project, event="fixture")
    begin_revision_cycle(project, mode="author_edit")
    source.write_text("value = 2\n", encoding="utf-8")

    report = evaluate_governance(project, purpose="audit")
    checks = {item["rule_id"]: item for item in report["checks"]}
    assert checks["DG-02"]["outcome"] == "failed"
    assert report["action_eligibility"]["allow_release"] is False

    with pytest.raises(RevisionCycleError, match="unreconciled"):
        close_revision_cycle(project, decision_receipt_id="unverified-fixture")


def test_binding_value_mismatch_is_rejected_before_receipt(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="binding value", field="astronomy").path
    source = project / "results" / "tables" / "metrics.json"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text('{"macro_f1": 0.81}\n', encoding="utf-8")
    binding_input = tmp_path / "bindings.json"
    _write_json(binding_input, _binding_input(source, 0.99))

    with pytest.raises(EvidenceBindingError, match="source_value_mismatch"):
        prepare_evidence_rebind(project, binding_file=str(binding_input))


def test_rebinding_does_not_absorb_unrelated_method_edit(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="scoped rebind", field="astronomy").path
    source = project / "results" / "tables" / "metrics.json"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text('{"macro_f1": 0.81}\n', encoding="utf-8")
    method = project / "methods" / "probe.py"
    method.parent.mkdir(parents=True, exist_ok=True)
    method.write_text("value = 1\n", encoding="utf-8")
    refresh_project_passport(project, event="fixture")
    begin_revision_cycle(project, mode="author_edit")
    method.write_text("value = 2\n", encoding="utf-8")

    binding_input = tmp_path / "bindings.json"
    _write_json(binding_input, _binding_input(source, 0.81))
    prepared_binding = prepare_evidence_rebind(project, binding_file=str(binding_input))
    apply_evidence_rebind(
        project,
        packet_path=str(prepared_binding["packet_path"]),
        packet_hash=str(prepared_binding["packet_hash"]),
    )

    prepared_revision = prepare_revision_reconciliation(project)
    packet = json.loads(Path(prepared_revision["reconciliation_path"]).read_text(encoding="utf-8"))
    changed_paths = {str(item["path"]) for item in packet["changes"]}

    assert "methods/probe.py" in changed_paths
