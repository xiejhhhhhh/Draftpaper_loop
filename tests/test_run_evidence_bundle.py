from __future__ import annotations

import json

from draftpaper_cli.run_evidence_bundle import (
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
