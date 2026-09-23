from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from draftpaper_cli.evidence_binding import EvidenceBindingError, prepare_evidence_rebind
from draftpaper_cli.project_scaffold import create_project


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _row(source: Path, locator: object, value: object) -> dict[str, object]:
    return {
        "source_artifact": source.relative_to(source.parents[2]).as_posix(),
        "source_hash": _sha256(source),
        "source_locator": locator,
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


def test_json_pointer_locator_is_recorded_as_verified(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="json source", field="astronomy").path
    source = project / "results" / "tables" / "metrics.json"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text('{"model-a": {"macro_f1": 0.81}}\n', encoding="utf-8")
    binding_file = tmp_path / "binding.json"
    row = _row(source, {"kind": "json_pointer", "pointer": "/model-a/macro_f1"}, 0.81)
    binding_file.write_text(json.dumps({"bindings": [row]}), encoding="utf-8")
    result = prepare_evidence_rebind(project, binding_file=str(binding_file))
    packet = json.loads(Path(result["packet_path"]).read_text(encoding="utf-8"))
    assert packet["bindings"][0]["source_value_verification"]["status"] == "verified"


def test_csv_duplicate_key_is_rejected(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="csv source", field="astronomy").path
    source = project / "results" / "tables" / "metrics.csv"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("model,split,macro_f1\nmodel-a,test,0.81\nmodel-a,test,0.81\n", encoding="utf-8")
    binding_file = tmp_path / "binding.json"
    row = _row(source, {"kind": "csv_row", "key_columns": {"model": "model-a", "split": "test"}, "value_column": "macro_f1"}, 0.81)
    binding_file.write_text(json.dumps({"bindings": [row]}), encoding="utf-8")
    with pytest.raises(EvidenceBindingError, match="source_locator_invalid"):
        prepare_evidence_rebind(project, binding_file=str(binding_file))


def test_declared_run_identity_cannot_override_source_identity(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="identity source", field="astronomy").path
    source = project / "results" / "tables" / "metrics.json"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text('{"macro_f1": 0.81, "run_id": "run-source"}\n', encoding="utf-8")
    binding_file = tmp_path / "binding.json"
    row = _row(source, "/macro_f1", 0.81)
    row["run_id"] = "run-fabricated"
    binding_file.write_text(json.dumps({"bindings": [row]}), encoding="utf-8")
    with pytest.raises(EvidenceBindingError, match="source_identity_mismatch"):
        prepare_evidence_rebind(project, binding_file=str(binding_file))
