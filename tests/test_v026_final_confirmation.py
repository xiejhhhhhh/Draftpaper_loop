from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from draftpaper_cli.evidence_snapshot import manuscript_snapshot
from draftpaper_cli.independent_review import SCORE_DIMENSIONS, derive_independent_review_decision
from draftpaper_cli.project_scaffold import create_project


def _artifact_record(project: Path, relative: str) -> dict[str, object]:
    path = project / relative
    return {
        "path": relative,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "size_bytes": path.stat().st_size,
    }


def _write_structured_reviews(project: Path) -> None:
    core = {
        "schema_version": "dpl.independent_review_bundle.v1",
        "project_id_hash": "project-id-hash",
        "submission_anonymized": True,
        "full_manuscript_reviewed": True,
        "real_figures_reviewed": True,
        "baseline_material_prohibited": True,
        "frozen_artifacts": {
            "manuscript": [_artifact_record(project, "latex/main.pdf")],
            "figures": [],
            "tables": [],
            "references": [_artifact_record(project, "references/library.bib")],
            "evidence": [_artifact_record(project, "results/promoted_evidence_snapshot.json")],
            "reproducibility": [],
        },
        "reviewer_contract": {
            "same_bundle_for_all_reviewers": True,
            "reviewers_cannot_see_other_reports": True,
            "automatic_scores_withheld": True,
            "prior_audits_withheld": True,
        },
        "excluded_reproducibility_files": [],
        "reproducibility_smoke_test": {"decision": "pass"},
        "selected_run_asset_filtering": True,
    }
    bundle_hash = hashlib.sha256(json.dumps(core, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    review_root = project / "quality_checks" / "blind_reviews"
    manifest = {
        **core,
        "created_at": "2026-07-18T10:00:00+00:00",
        "bundle_hash": bundle_hash,
        "bundle_hash_semantics": "SHA-256 of the canonical frozen-artifact manifest core; not the ZIP container byte hash.",
        "bundle_zip": "quality_checks/blind_reviews/anonymous_submission_bundle.zip",
    }
    (review_root / "submission_bundle_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    bundle_path = project / manifest["bundle_zip"]
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("bundle_manifest.json", json.dumps(manifest))
        for group in manifest["frozen_artifacts"].values():
            for record in group:
                archive.writestr(record["path"], (project / record["path"]).read_bytes())

    report_paths = []
    report_sha256 = {}
    reports = []
    for index, recorded_at in ((1, "2026-07-18T11:00:00+00:00"), (2, "2026-07-18T11:05:00+00:00")):
        reviewer = f"reviewer_{index:02d}"
        relative = f"quality_checks/blind_reviews/{reviewer}/report.json"
        report_paths.append(relative)
        report = {
            "schema_version": "dpl.independent_manuscript_review.v1",
            "reviewer_anonymous_id": reviewer,
            "independent_session_provider_id_hash": f"session-{index}",
            "frozen_submission_bundle_hash": bundle_hash,
            "overall_recommendation": "accept_for_revision",
            "scores": {dimension: 0.95 for dimension in SCORE_DIMENSIONS},
            "findings": [
                {
                    "finding_id": f"{reviewer}:001",
                    "severity": "advisory",
                    "locator": "page 1, Results",
                    "detail": "The result summary is grounded in the frozen manuscript.",
                    "required_action": "Retain the current evidence boundary.",
                }
            ],
            "checked_real_figures": True,
            "full_manuscript_reviewed": True,
            "recorded_at": recorded_at,
        }
        reports.append(report)
        report_path = project / relative
        report_path.write_text(json.dumps(report), encoding="utf-8")
        report_sha256[relative] = hashlib.sha256(report_path.read_bytes()).hexdigest()

    aggregate = {
        "schema_version": "dpl.independent_review_aggregate.v1",
        "status": "passed",
        "generated_at": "2026-07-18T11:30:00+00:00",
        "frozen_submission_bundle_hash": bundle_hash,
        "reviewer_count": 2,
        "reviewer_reports": report_paths,
        "reviewer_report_sha256": report_sha256,
        **derive_independent_review_decision(reports),
    }
    (review_root / "aggregate.json").write_text(json.dumps(aggregate), encoding="utf-8")


class FinalConfirmationV026Tests(unittest.TestCase):
    def test_final_release_binds_pdf_citations_two_reviews_and_quality(self) -> None:
        from draftpaper_cli.final_manuscript_confirmation import (
            confirm_final_manuscript,
            final_confirmation_state,
            review_final_manuscript,
        )

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Final paper", field="astronomy")
            artifacts = {
                "latex/main.pdf": b"%PDF-1.4\n",
                "writing/manuscript_completion/active_completion_manifest.json": json.dumps({"status": "applied", "packet_id": "packet:test", "packet_hash": "a" * 64, "applied_at": "2026-07-18T08:00:00+00:00"}).encode(),
                "writing/manuscript_metadata.yaml": b"title: Final paper\n",
                "introduction/introduction.tex": b"\\section{Introduction}\nFinal.\n",
                "data/data.tex": b"\\section{Data}\nFinal.\n",
                "methods/methods.tex": b"\\section{Methods}\nFinal.\n",
                "results/results.tex": b"\\section{Results}\nFinal.\n",
                "discussion/discussion.tex": b"\\section{Discussion}\nFinal.\n",
                "references/library.bib": b"@article{Test2026,title={Test},year={2026}}\n",
                "latex/library.bib": b"@article{Test2026,title={Test},year={2026}}\n",
                "references/reference_registry.json": json.dumps({"status": "passed"}).encode(),
                "results/promoted_evidence_snapshot.json": json.dumps({"snapshot_id": "evidence:test", "artifacts": {}}).encode(),
                "results/result_manifest.yaml": b"schema_version: dpl.result_manifest.v2\nstatus: passed\n",
                "results/figure_metadata.json": json.dumps({"status": "passed"}).encode(),
                "core_evidence/core_evidence_report.json": json.dumps({"decision": "pass"}).encode(),
                "integrity/integrity_report.json": json.dumps({"status": "passed"}).encode(),
                "quality_checks/blind_reviews/reviewer_01/report.md": b"# Reviewer 1\n",
                "quality_checks/blind_reviews/reviewer_02/report.md": b"# Reviewer 2\n",
                "quality_checks/quality_report.json": json.dumps({"status": "passed"}).encode(),
            }
            for relative, content in artifacts.items():
                path = project.path / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            citation_snapshot = manuscript_snapshot(project.path)
            citation = project.path / "citation_audit" / "final_citation_audit_report.json"
            citation.parent.mkdir(parents=True, exist_ok=True)
            citation.write_text(
                json.dumps(
                    {
                        "schema_version": "dpl.citation_audit.v2",
                        "status": "passed",
                        "generated_at": "2026-07-18T09:00:00+00:00",
                        "manuscript_snapshot": citation_snapshot,
                    }
                ),
                encoding="utf-8",
            )
            _write_structured_reviews(project.path)
            review = review_final_manuscript(project.path)
            confirmed = confirm_final_manuscript(project.path, release_hash=review["release_hash"])
            self.assertEqual(confirmed["status"], "approved")
            self.assertTrue(final_confirmation_state(project.path)["current"])
            (project.path / "latex" / "main.pdf").write_bytes(b"%PDF-1.5\nchanged")
            self.assertEqual(final_confirmation_state(project.path)["status"], "incomplete")


if __name__ == "__main__":
    unittest.main()
