from __future__ import annotations

import json

from draftpaper_cli.run_evidence_bundle import (
    _bundle_hash,
    build_run_evidence_bundle,
    load_active_run_evidence_bundle,
    publish_run_evidence_bundle,
)
from draftpaper_cli.project_scaffold import create_project


def _run_manifest(project, **extra):
    payload = {
        "status": "success",
        "run_id": "run-1",
        "run_transaction_id": "txn-1",
        "output_files": ["results/tables/canonical.json"],
    }
    payload.update(extra)
    path = project / "methods" / "run_manifest.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _metric_report(status="passed"):
    return {
        "status": status,
        "records": [{"metric_record_id": "metric-1"}],
    }


def _count_report(status="passed"):
    return {
        "status": status,
        "records": [{"count_record_id": "count-1"}],
    }


def test_failed_candidate_does_not_create_active_pointer(tmp_path) -> None:
    project = create_project(root=tmp_path, idea="bundle", field="generic").path
    _run_manifest(project, status="failed")
    (project / "results" / "tables").mkdir(parents=True, exist_ok=True)
    (project / "results" / "tables" / "canonical.json").write_text("{}", encoding="utf-8")
    bundle = build_run_evidence_bundle(project, metric_identity=_metric_report("blocked"), count_identity=_count_report("blocked"))
    assert bundle["status"] == "failed"
    published = publish_run_evidence_bundle(project, bundle)
    assert published["active_pointer_path"] is None
    assert load_active_run_evidence_bundle(project)["status"] == "missing"


def test_validated_bundle_is_atomic_active_source(tmp_path) -> None:
    project = create_project(root=tmp_path, idea="bundle", field="generic").path
    _run_manifest(project)
    (project / "results" / "tables").mkdir(parents=True, exist_ok=True)
    (project / "results" / "tables" / "canonical.json").write_text("{}", encoding="utf-8")
    bundle = build_run_evidence_bundle(project, metric_identity=_metric_report(), count_identity=_count_report())
    assert bundle["status"] == "validated"
    publish_run_evidence_bundle(project, bundle)
    active = load_active_run_evidence_bundle(project)
    assert active["status"] == "active"
    assert active["bundle"]["bundle_sha256"] == bundle["bundle_sha256"]


def test_new_bundle_supersedes_pointer_without_deleting_previous_bundle(tmp_path) -> None:
    project = create_project(root=tmp_path, idea="bundle", field="generic").path
    _run_manifest(project)
    (project / "results" / "tables").mkdir(parents=True, exist_ok=True)
    output = project / "results" / "tables" / "canonical.json"
    output.write_text("{}", encoding="utf-8")
    first = publish_run_evidence_bundle(project, build_run_evidence_bundle(project, metric_identity=_metric_report(), count_identity=_count_report()))
    output.write_text("{\"changed\": true}", encoding="utf-8")
    second = publish_run_evidence_bundle(project, build_run_evidence_bundle(project, metric_identity=_metric_report(), count_identity=_count_report()))
    assert first["bundle_sha256"] != second["bundle_sha256"]
    assert list((project / "results" / "run_evidence_bundles").glob("*-superseded.json"))


def test_candidate_with_same_transaction_cannot_overwrite_validated_bundle(tmp_path) -> None:
    project = create_project(root=tmp_path, idea="bundle", field="generic").path
    _run_manifest(project)
    (project / "results" / "tables").mkdir(parents=True, exist_ok=True)
    output = project / "results" / "tables" / "canonical.json"
    output.write_text("{}", encoding="utf-8")
    first = publish_run_evidence_bundle(
        project,
        build_run_evidence_bundle(project, metric_identity=_metric_report(), count_identity=_count_report()),
    )
    first_path = project / first["bundle_path"]
    original = first_path.read_bytes()
    failed = dict(first)
    failed["status"] = "candidate"
    failed["validation_receipts"] = [{"name": "run_status", "status": "passed"}]
    failed["bundle_sha256"] = _bundle_hash(failed)
    publish_run_evidence_bundle(project, failed)
    assert first_path.read_bytes() == original
    assert load_active_run_evidence_bundle(project)["bundle"]["bundle_sha256"] == first["bundle_sha256"]


def test_input_data_is_normalized_into_evidence_bundle(tmp_path) -> None:
    project = create_project(root=tmp_path, idea="bundle", field="generic").path
    (project / "data").mkdir(parents=True, exist_ok=True)
    (project / "data" / "source.csv").write_text("x\n1\n", encoding="utf-8")
    _run_manifest(project, input_data=[{"path": "data/source.csv", "role": "source_catalog"}])
    (project / "results" / "tables").mkdir(parents=True, exist_ok=True)
    (project / "results" / "tables" / "canonical.json").write_text("{}", encoding="utf-8")
    bundle = build_run_evidence_bundle(project, metric_identity=_metric_report(), count_identity=_count_report())
    assert bundle["input_artifacts"][0]["path"] == "data/source.csv"
    assert bundle["input_artifacts"][0]["status"] == "present"


def test_published_bundle_hash_covers_content_but_not_derived_storage_path(tmp_path) -> None:
    project = create_project(root=tmp_path, idea="bundle hash", field="generic").path
    _run_manifest(project)
    output = project / "results" / "tables" / "canonical.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("{}", encoding="utf-8")
    bundle = build_run_evidence_bundle(project, metric_identity=_metric_report(), count_identity=_count_report())

    published = publish_run_evidence_bundle(project, bundle)
    stored = json.loads((project / published["bundle_path"]).read_text(encoding="utf-8"))

    assert stored["bundle_sha256"] == _bundle_hash(stored)


def test_publish_rejects_a_stale_expected_active_pointer(tmp_path) -> None:
    project = create_project(root=tmp_path, idea="bundle concurrency", field="generic").path
    _run_manifest(project)
    output = project / "results" / "tables" / "canonical.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("{}", encoding="utf-8")
    first = publish_run_evidence_bundle(
        project,
        build_run_evidence_bundle(project, metric_identity=_metric_report(), count_identity=_count_report()),
    )
    output.write_text('{"changed": true}', encoding="utf-8")
    second = build_run_evidence_bundle(project, metric_identity=_metric_report(), count_identity=_count_report())

    import pytest

    with pytest.raises(ValueError, match="active bundle changed"):
        publish_run_evidence_bundle(
            project,
            second,
            expected_active_bundle_sha256="stale-baseline",
        )

    assert load_active_run_evidence_bundle(project)["bundle"]["bundle_sha256"] == first["bundle_sha256"]
