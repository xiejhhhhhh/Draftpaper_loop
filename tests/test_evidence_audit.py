from __future__ import annotations

import json

from draftpaper_cli.evidence_audit import audit_evidence_identity
from draftpaper_cli.evidence_registry import build_scientific_evidence_registry
from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.run_evidence_bundle import build_run_evidence_bundle, publish_run_evidence_bundle


def _write(path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _strict_reports(project):
    _write(
        project / "results" / "metric_identity_report.json",
        {
            "schema_version": "dpl.metric_identity_report.v1",
            "status": "passed",
            "records": [
                {
                    "metric_record_id": "metric-1",
                    "identity_complete": True,
                    "legacy_source": False,
                    "evidence_role": "primary",
                }
            ],
        },
    )
    _write(
        project / "results" / "count_identity_report.json",
        {
            "schema_version": "dpl.count_identity_report.v1",
            "status": "passed",
            "records": [
                {
                    "count_record_id": "count-1",
                    "identity_complete": True,
                    "legacy_source": False,
                    "evidence_role": "sample_flow",
                }
            ],
        },
    )


def test_identity_audit_is_read_only_and_reports_unqualified_project(tmp_path) -> None:
    project = create_project(root=tmp_path, idea="audit fixture", field="generic").path
    before = sorted(path.relative_to(project).as_posix() for path in project.rglob("*"))

    report = audit_evidence_identity(project)

    after = sorted(path.relative_to(project).as_posix() for path in project.rglob("*"))
    assert report["schema_version"] == "dpl.evidence_identity_audit.v1"
    assert report["read_only"] is True
    assert report["writes_performed"] == []
    assert report["status"] == "needs_review"
    assert before == after


def test_identity_audit_accepts_strict_active_bundle_without_writing(tmp_path) -> None:
    project = create_project(root=tmp_path, idea="strict audit fixture", field="generic").path
    _write(
        project / "methods" / "run_manifest.yaml",
        {
            "status": "success",
            "run_id": "run-audit",
            "run_transaction_id": "txn-audit",
            "output_files": ["results/tables/canonical.json"],
        },
    )
    (project / "results" / "tables").mkdir(parents=True, exist_ok=True)
    (project / "results" / "tables" / "canonical.json").write_text("{}", encoding="utf-8")
    _strict_reports(project)
    bundle = build_run_evidence_bundle(
        project,
        metric_identity={"status": "passed", "records": [{"metric_record_id": "metric-1"}]},
        count_identity={"status": "passed", "records": [{"count_record_id": "count-1"}]},
    )
    publish_run_evidence_bundle(project, bundle)
    before = sorted(path.relative_to(project).as_posix() for path in project.rglob("*"))

    report = audit_evidence_identity(project)

    after = sorted(path.relative_to(project).as_posix() for path in project.rglob("*"))
    assert report["status"] == "passed"
    assert report["checks"][0]["status"] == "passed"
    assert report["checks"][1]["status"] == "passed"
    assert report["checks"][2]["status"] == "active"
    assert report["writes_performed"] == []
    assert before == after


def test_registry_exposes_typed_identity_bridge(tmp_path) -> None:
    project = create_project(root=tmp_path, idea="registry fixture", field="generic").path
    _strict_reports(project)

    registry = build_scientific_evidence_registry(project)

    typed = registry["typed_evidence"]
    assert typed["metric_status"] == "passed"
    assert typed["count_status"] == "passed"
    assert typed["metric_record_count"] == 1
    assert typed["count_record_count"] == 1
    assert registry["typed_blocking_statuses"] == []
