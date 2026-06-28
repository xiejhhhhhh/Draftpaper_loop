# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from draftpaper_cli.project_scaffold import create_project


def write_failed_gate_reports(project_path: Path) -> None:
    (project_path / "data" / "data_feasibility_report.json").write_text(
        json.dumps({
            "decision": "blocked",
            "blocking_issues": ["Total tabular row count 5 is below the minimum threshold 30."],
            "recommended_actions": ["Add more observations or reduce the scope."],
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (project_path / "methods" / "run_manifest.yaml").write_text(
        json.dumps({
            "status": "failed",
            "command": "python code/scripts/run_analysis.py",
            "returncode": 1,
            "missing_outputs": ["results/tables/metrics.csv"],
            "output_files": ["results/tables/metrics.csv"],
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (project_path / "results" / "result_validity_report.json").write_text(
        json.dumps({
            "decision": "revise_required",
            "primary_metric": "f1",
            "observed_value": 0.42,
            "minimum_value": 0.75,
            "failure_causes": ["method"],
            "recommended_actions": ["Inspect model design and validation split."],
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (project_path / "integrity").mkdir(exist_ok=True)
    (project_path / "integrity" / "integrity_report.json").write_text(
        json.dumps({
            "status": "failed",
            "issues": [
                {
                    "severity": "error",
                    "code": "missing_citation_evidence",
                    "message": "Citation key is absent from citation_evidence.csv: Unknown2026",
                    "file": "references/citation_evidence.csv",
                    "section": "introduction",
                },
                {
                    "severity": "error",
                    "code": "result_artifact_missing",
                    "message": "Result artifact does not exist: results/figures/missing.svg",
                    "file": "results/figures/missing.svg",
                    "section": "results",
                },
            ],
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (project_path / "quality_checks" / "quality_report.json").write_text(
        json.dumps({
            "status": "failed",
            "issues": [
                {
                    "severity": "error",
                    "code": "stale_stage_in_final_latex",
                    "message": "Final LaTeX depends on stale stage: results.",
                    "file": "results/stage_manifest.json",
                }
            ],
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (project_path / "latex" / "main.tex").write_text("\\section{Draft}\n", encoding="utf-8")
    (project_path / "results" / "results.tex").write_text("\\section{Results}\nWeak result text.\n", encoding="utf-8")


class ReviewRevisionTests(unittest.TestCase):
    def test_diagnose_gate_failures_writes_unified_revision_issues(self) -> None:
        from draftpaper_cli.review_revision import diagnose_gate_failures

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Revision router", field="workflow engineering")
            write_failed_gate_reports(project.path)

            report = diagnose_gate_failures(project.path)

            self.assertEqual(report["status"], "issues_found")
            self.assertTrue((project.path / "review" / "gate_failure_diagnosis.json").exists())
            self.assertTrue((project.path / "review" / "gate_failure_diagnosis.md").exists())
            sources = {issue["source"] for issue in report["issues"]}
            self.assertIn("data_feasibility", sources)
            self.assertIn("methods", sources)
            self.assertIn("result_validity", sources)
            self.assertIn("integrity", sources)
            self.assertTrue(all("recommended_commands" in issue for issue in report["issues"]))
            self.assertTrue(any(issue["target_stage"] == "references" for issue in report["issues"]))
            self.assertTrue(any(issue["target_stage"] == "results" for issue in report["issues"]))

    def test_review_and_revision_plan_create_commitment_ledger(self) -> None:
        from draftpaper_cli.review_revision import generate_revision_plan, review_draft

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Reviewer loop", field="workflow engineering")
            write_failed_gate_reports(project.path)

            review = review_draft(project.path)
            plan = generate_revision_plan(project.path)

            self.assertEqual(review["status"], "reviewed")
            self.assertTrue((project.path / "review" / "review_report.md").exists())
            self.assertTrue((project.path / "review" / "reviewer_issues.json").exists())
            self.assertEqual(plan["status"], "revision_required")
            self.assertTrue((project.path / "review" / "revision_plan.json").exists())
            self.assertTrue((project.path / "review" / "revision_plan.md").exists())
            ledger_path = project.path / "review" / "commitment_ledger.csv"
            self.assertTrue(ledger_path.exists())
            with ledger_path.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertGreaterEqual(len(rows), 1)
            self.assertIn("issue_id", rows[0])
            self.assertIn("target_stage", rows[0])
            sources = {issue["source"] for issue in plan["issues"]}
            self.assertIn("publication_readiness", sources)
            self.assertIn("statistical_rescue", sources)

    def test_publication_readiness_and_statistical_rescue_write_review_artifacts(self) -> None:
        from draftpaper_cli.review_revision import assess_publication_readiness, recommend_statistical_revision

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Weak data rescue", field="environmental statistics")
            write_failed_gate_reports(project.path)

            readiness = assess_publication_readiness(project.path)
            rescue = recommend_statistical_revision(project.path)

            self.assertLess(readiness["readiness_score"], 65)
            self.assertIn(readiness["readiness_band"], {"major_revision_needed", "not_ready_for_submission"})
            self.assertEqual(rescue["status"], "rescue_recommended")
            self.assertGreaterEqual(rescue["issue_count"], 1)
            self.assertTrue((project.path / "review" / "publication_readiness_report.json").exists())
            self.assertTrue((project.path / "review" / "publication_readiness_report.html").exists())
            self.assertTrue((project.path / "review" / "codex_archive_review_context.json").exists())
            self.assertTrue((project.path / "review" / "codex_archive_review_context.html").exists())
            self.assertTrue((project.path / "review" / "statistical_rescue_plan.json").exists())
            self.assertTrue((project.path / "review" / "statistical_rescue_plan.html").exists())
            self.assertTrue((project.path / "review" / "claim_evidence_matrix.csv").exists())
            self.assertIn("reviewer_narrative", readiness)
            self.assertIn("reviewer perspective", readiness["reviewer_narrative"])

    def test_statistical_rescue_flags_weak_effect_statistics_as_data_qc(self) -> None:
        from draftpaper_cli.review_revision import assess_publication_readiness, recommend_statistical_revision

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(
                root=tmp,
                idea="Assess wheat yield response using NDVI and environmental drivers.",
                field="remote sensing agronomy wheat yield NDVI",
            )
            (project.path / "data" / "data_quality_report.json").write_text(
                json.dumps({
                    "overall_status": "pass",
                    "overall_missing_cell_ratio": 0.0,
                    "total_rows": 842,
                    "required_columns": ["ndvi", "yield", "air_temperature_proxy"],
                    "missing_required_columns": [],
                }, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (project.path / "data" / "data_feasibility_report.json").write_text(
                json.dumps({"decision": "pass", "observed_rows": 842, "min_rows": 30}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (project.path / "methods" / "method_requirements.json").write_text(
                json.dumps({"primary_metric": "r2", "minimum_primary_metric": 0.05}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps({"status": "success", "metrics": {"r2": 0.085081}}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (project.path / "results" / "result_validity_report.json").write_text(
                json.dumps({
                    "decision": "pass",
                    "primary_metric": "r2",
                    "observed_value": 0.085081,
                    "minimum_value": 0.05,
                    "issues": [],
                    "failure_causes": [],
                }, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (project.path / "results" / "figure_metadata.json").write_text(
                json.dumps({
                    "figures": [
                        {
                            "figure_id": "environmental_driver_response",
                            "title": "Environmental driver response",
                            "figure_type": "scatter_regression",
                            "variables": {"x": "air_temperature_proxy", "y": "yield"},
                            "statistics": {"pearson_r": -0.2304975730964553, "r2": 0.05312913120335572},
                            "interpretation_summary": "air_temperature_proxy and yield show a weak negative association.",
                        }
                    ]
                }, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            readiness = assess_publication_readiness(project.path)
            rescue = recommend_statistical_revision(project.path)

            route_ids = {route["route_id"] for route in rescue["recommended_routes"]}
            self.assertTrue(any("weak explanatory effects" in signal for signal in readiness["evidence_signals"]))
            self.assertIn("weak explanatory effects", readiness["reviewer_narrative"])
            self.assertEqual(rescue["status"], "rescue_recommended")
            self.assertIn("weak_effect_data_quality_audit", route_ids)
            self.assertIn("agricultural_remote_sensing_qc_rebuild", route_ids)
            self.assertIn("weak_effect_statistics", rescue["likely_failure_sources"])
            weak_route = next(route for route in rescue["recommended_routes"] if route["route_id"] == "weak_effect_data_quality_audit")
            self.assertEqual(weak_route["target_stage"], "data")
            self.assertTrue(any("outlier" in action.lower() for action in weak_route["actions"]))

    def test_apply_revision_marks_target_and_downstream_stages_stale(self) -> None:
        from draftpaper_cli.project_state import update_stage_status
        from draftpaper_cli.review_revision import apply_revision, generate_revision_plan

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Apply revision", field="workflow engineering")
            write_failed_gate_reports(project.path)
            for stage in ["methods", "result_validity", "results", "discussion", "latex", "quality_checks"]:
                update_stage_status(project.path, stage, "completed")
            generate_revision_plan(project.path)

            result = apply_revision(project.path)

            self.assertEqual(result["status"], "applied")
            project_json = json.loads((project.path / "project.json").read_text(encoding="utf-8"))
            self.assertEqual(project_json["stages"]["methods"]["status"], "stale")
            self.assertEqual(project_json["stages"]["results"]["status"], "stale")
            self.assertTrue((project.path / "review" / "apply_revision_report.json").exists())

    def test_cli_review_revision_loop_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="CLI review loop", field="workflow engineering")
            write_failed_gate_reports(project.path)
            for command in [
                "diagnose-gate-failures",
                "review-draft",
                "assess-publication-readiness",
                "recommend-statistical-revision",
                "generate-revision-plan",
                "apply-revision",
                "re-review",
            ]:
                completed = subprocess.run(
                    [sys.executable, "-m", "draftpaper_cli.cli", command, "--project", str(project.path)],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                self.assertIn("status", json.loads(completed.stdout))
            self.assertTrue((project.path / "review" / "re_review_report.md").exists())


if __name__ == "__main__":
    unittest.main()
