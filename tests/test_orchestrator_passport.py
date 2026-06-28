# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from draftpaper_cli.project_scaffold import create_project


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class OrchestratorPassportTests(unittest.TestCase):
    def test_create_project_initializes_passport_and_ledgers(self) -> None:
        from draftpaper_cli.passport import PASSPORT_FILES, load_project_passport

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Passport test", field="workflow engineering")

            for relative in PASSPORT_FILES.values():
                self.assertTrue((project.path / relative).exists(), relative)

            passport = load_project_passport(project.path)
            self.assertEqual(passport["project_id"], project.project_id)
            self.assertEqual(passport["schema_version"], 1)
            self.assertEqual(passport["dpl"]["schema_family"], "dpl")
            self.assertEqual(passport["dpl"]["project_passport_schema"], "dpl.project_passport.v1")
            self.assertEqual(passport["generated_by"]["name"], "Draftpaper-loop")
            self.assertGreaterEqual(passport["artifact_count"], 3)
            self.assertIn("project.json", {item["path"] for item in passport["artifacts"]})

            artifact_events = read_jsonl(project.path / "artifact_ledger.jsonl")
            self.assertTrue(any(event["path"] == "project.json" for event in artifact_events))

    def test_checkpoint_and_resume_are_append_only_and_drive_status(self) -> None:
        from draftpaper_cli.orchestrator import checkpoint_project, resume_project, status_project

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Checkpoint test", field="workflow engineering")

            checkpoint = checkpoint_project(project.path, stage="idea", note="User approved the idea.")
            self.assertEqual(checkpoint["status"], "checkpoint_created")
            self.assertRegex(checkpoint["checkpoint_hash"], r"^[a-f0-9]{12}$")

            waiting = status_project(project.path)
            self.assertEqual(waiting["pipeline_state"], "awaiting_confirmation")
            self.assertEqual(waiting["awaiting_checkpoint"]["hash"], checkpoint["checkpoint_hash"])
            self.assertEqual(waiting["next_action"]["command"], "resume")

            resumed = resume_project(project.path, checkpoint_hash=checkpoint["checkpoint_hash"], note="Continue.")
            self.assertEqual(resumed["status"], "resumed")
            self.assertEqual(resumed["consumed_checkpoint_hash"], checkpoint["checkpoint_hash"])

            status = status_project(project.path)
            self.assertEqual(status["pipeline_state"], "ready")
            self.assertEqual(status["next_action"]["stage"], "references")
            self.assertEqual(status["next_action"]["command"], "search-literature")

            checkpoint_events = read_jsonl(project.path / "checkpoint_ledger.jsonl")
            self.assertEqual([event["kind"] for event in checkpoint_events], ["checkpoint", "resume"])

    def test_cli_status_checkpoint_resume_and_run_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="CLI orchestrator", field="workflow engineering")

            status_completed = subprocess.run(
                [sys.executable, "-m", "draftpaper_cli.cli", "status", "--project", str(project.path)],
                check=True,
                capture_output=True,
                text=True,
            )
            status_payload = json.loads(status_completed.stdout)
            self.assertEqual(status_payload["status"], "reported")
            self.assertEqual(status_payload["next_action"]["command"], "search-literature")

            checkpoint_completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "checkpoint",
                    "--project",
                    str(project.path),
                    "--stage",
                    "idea",
                    "--note",
                    "Approved.",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            checkpoint_hash = json.loads(checkpoint_completed.stdout)["checkpoint_hash"]

            resume_completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "resume",
                    "--project",
                    str(project.path),
                    "--checkpoint-hash",
                    checkpoint_hash,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(json.loads(resume_completed.stdout)["status"], "resumed")

            run_completed = subprocess.run(
                [sys.executable, "-m", "draftpaper_cli.cli", "run-pipeline", "--project", str(project.path)],
                check=True,
                capture_output=True,
                text=True,
            )
            run_payload = json.loads(run_completed.stdout)
            self.assertEqual(run_payload["status"], "planned")
            self.assertIn("search-literature", run_payload["next_action"]["cli"])

    def test_status_recommends_integrity_gate_before_final_quality_check(self) -> None:
        from draftpaper_cli.orchestrator import status_project
        from draftpaper_cli.passport import refresh_project_passport
        from draftpaper_cli.project_scaffold import _write_json
        from draftpaper_cli.project_state import update_stage_status

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Integrity before quality", field="workflow engineering")
            for stage in [
                "references",
                "journal_profile",
                "research_plan",
                "introduction",
                "data",
                "method_plan",
                "figure_plan",
                "code",
                "methods",
                "result_validity",
                "results",
                "discussion",
                "latex",
            ]:
                update_stage_status(project.path, stage, "completed")
            _write_json(project.path / "data" / "data_writing_context.json", {"narrative_summary": "ready"})
            (project.path / "data" / "data.tex").write_text("\\section{Data}\nReady.\n", encoding="utf-8")
            (project.path / "data" / "data_inventory.json").write_text("{}", encoding="utf-8")
            (project.path / "data" / "data_quality_report.json").write_text("{}", encoding="utf-8")
            (project.path / "data" / "data_feasibility_report.json").write_text('{"decision":"pass"}', encoding="utf-8")
            _write_json(project.path / "methods" / "method_writing_context.json", {"narrative_summary": "ready"})
            (project.path / "methods" / "methods.tex").write_text("\\section{Methods}\nReady.\n", encoding="utf-8")
            (project.path / "methods" / "run_manifest.yaml").write_text('{"status":"success"}', encoding="utf-8")
            refresh_project_passport(project.path, event="test_status_ready")

            status = status_project(project.path)

            self.assertEqual(status["next_action"]["stage"], "quality_checks")
            self.assertEqual(status["next_action"]["command"], "run-integrity-gate")

            _write_json(project.path / "integrity" / "integrity_report.json", {"status": "passed"})
            status_after_integrity = status_project(project.path)

            self.assertEqual(status_after_integrity["next_action"]["stage"], "quality_checks")
            self.assertEqual(status_after_integrity["next_action"]["command"], "audit-citations")

            (project.path / "citation_audit").mkdir(parents=True, exist_ok=True)
            _write_json(project.path / "citation_audit" / "final_citation_audit_report.json", {"status": "passed"})
            status_after_citation_audit = status_project(project.path)

            self.assertEqual(status_after_citation_audit["next_action"]["stage"], "quality_checks")
            self.assertEqual(status_after_citation_audit["next_action"]["command"], "quality-check")

    def test_status_recommends_citation_repair_loop_before_quality_check(self) -> None:
        from draftpaper_cli.orchestrator import run_pipeline
        from draftpaper_cli.passport import refresh_project_passport
        from draftpaper_cli.project_scaffold import _write_json
        from draftpaper_cli.project_state import update_stage_status

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Citation repair route", field="workflow engineering")
            for stage in [
                "references",
                "journal_profile",
                "research_plan",
                "introduction",
                "data",
                "method_plan",
                "figure_plan",
                "code",
                "methods",
                "result_validity",
                "results",
                "discussion",
                "latex",
            ]:
                update_stage_status(project.path, stage, "completed")
            _write_json(project.path / "data" / "data_writing_context.json", {"narrative_summary": "ready"})
            (project.path / "data" / "data.tex").write_text("\\section{Data}\nReady.\n", encoding="utf-8")
            (project.path / "data" / "data_inventory.json").write_text("{}", encoding="utf-8")
            (project.path / "data" / "data_quality_report.json").write_text("{}", encoding="utf-8")
            (project.path / "data" / "data_feasibility_report.json").write_text('{"decision":"pass"}', encoding="utf-8")
            _write_json(project.path / "methods" / "method_writing_context.json", {"narrative_summary": "ready"})
            (project.path / "methods" / "methods.tex").write_text("\\section{Methods}\nReady.\n", encoding="utf-8")
            (project.path / "methods" / "run_manifest.yaml").write_text('{"status":"success"}', encoding="utf-8")
            _write_json(project.path / "integrity" / "integrity_report.json", {"status": "passed"})
            refresh_project_passport(project.path, event="test_integrity_passed_no_citation_audit")

            self.assertEqual(run_pipeline(project.path)["next_action"]["command"], "audit-citations")

            (project.path / "citation_audit").mkdir(parents=True, exist_ok=True)
            _write_json(project.path / "citation_audit" / "citation_audit_report.json", {
                "status": "failed",
                "summary": {"unsupported": 1, "unverifiable": 0},
            })
            refresh_project_passport(project.path, event="test_citation_audit_failed")
            self.assertEqual(run_pipeline(project.path)["next_action"]["command"], "generate-citation-repair-plan")

            _write_json(project.path / "citation_audit" / "citation_repair_plan.json", {"status": "repair_plan_written", "issues": []})
            refresh_project_passport(project.path, event="test_citation_repair_plan")
            self.assertEqual(run_pipeline(project.path)["next_action"]["command"], "apply-citation-repair")

            _write_json(project.path / "citation_audit" / "citation_repair_ledger.json", {"status": "applied", "applied_action_count": 1})
            refresh_project_passport(project.path, event="test_citation_repair_applied")
            self.assertEqual(run_pipeline(project.path)["next_action"]["command"], "re-audit-citations")

            _write_json(project.path / "citation_audit" / "final_citation_audit_report.json", {"status": "passed"})
            refresh_project_passport(project.path, event="test_citation_final_passed")
            self.assertEqual(run_pipeline(project.path)["next_action"]["command"], "quality-check")

    def test_status_recommends_gate_failure_diagnosis_after_integrity_failure(self) -> None:
        from draftpaper_cli.orchestrator import status_project
        from draftpaper_cli.passport import refresh_project_passport
        from draftpaper_cli.project_scaffold import _write_json
        from draftpaper_cli.project_state import update_stage_status

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Diagnose integrity failure", field="workflow engineering")
            for stage in [
                "references",
                "journal_profile",
                "research_plan",
                "introduction",
                "data",
                "method_plan",
                "figure_plan",
                "code",
                "methods",
                "result_validity",
                "results",
                "discussion",
                "latex",
            ]:
                update_stage_status(project.path, stage, "completed")
            _write_json(project.path / "integrity" / "integrity_report.json", {
                "status": "failed",
                "issues": [{"severity": "error", "code": "missing_citation_evidence", "message": "Missing evidence."}],
            })
            refresh_project_passport(project.path, event="test_integrity_failed")

            status = status_project(project.path)

            self.assertEqual(status["next_action"]["stage"], "review")
            self.assertEqual(status["next_action"]["command"], "diagnose-gate-failures")
            self.assertIn("diagnose-gate-failures", status["next_action"]["cli"])

    def test_run_pipeline_recommends_review_sequence_after_quality_failure(self) -> None:
        from draftpaper_cli.orchestrator import run_pipeline
        from draftpaper_cli.passport import refresh_project_passport
        from draftpaper_cli.project_scaffold import _write_json
        from draftpaper_cli.project_state import update_stage_status

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Diagnose quality failure", field="workflow engineering")
            for stage in [
                "references",
                "journal_profile",
                "research_plan",
                "introduction",
                "data",
                "method_plan",
                "figure_plan",
                "code",
                "methods",
                "result_validity",
                "results",
                "discussion",
                "latex",
            ]:
                update_stage_status(project.path, stage, "completed")
            update_stage_status(project.path, "quality_checks", "failed")
            _write_json(project.path / "integrity" / "integrity_report.json", {"status": "passed"})
            _write_json(project.path / "quality_checks" / "quality_report.json", {
                "status": "failed",
                "issues": [{"severity": "error", "code": "required_artifact_missing", "message": "Missing artifact."}],
            })
            refresh_project_passport(project.path, event="test_quality_failed")

            plan = run_pipeline(project.path)

            self.assertEqual(plan["next_action"]["stage"], "review")
            self.assertEqual(plan["next_action"]["command"], "diagnose-gate-failures")

            _write_json(project.path / "review" / "gate_failure_diagnosis.json", {"status": "issues_found"})
            refresh_project_passport(project.path, event="test_review_diagnosis_written")
            self.assertEqual(run_pipeline(project.path)["next_action"]["command"], "review-draft")

            _write_json(project.path / "review" / "reviewer_issues.json", {"status": "reviewed"})
            refresh_project_passport(project.path, event="test_reviewer_issues_written")
            self.assertEqual(run_pipeline(project.path)["next_action"]["command"], "assess-publication-readiness")

            _write_json(project.path / "review" / "publication_readiness_report.json", {"status": "reviewed"})
            refresh_project_passport(project.path, event="test_readiness_written")
            self.assertEqual(run_pipeline(project.path)["next_action"]["command"], "discover-review-workflow-gaps")

            _write_json(project.path / "review" / "review_workflow_gap_report.json", {"status": "review_workflow_gaps_found"})
            refresh_project_passport(project.path, event="test_review_gaps_written")
            self.assertEqual(run_pipeline(project.path)["next_action"]["command"], "propose-review-engineering-plan")

            _write_json(project.path / "review" / "review_engineering_plan.json", {"status": "review_engineering_plan_written"})
            refresh_project_passport(project.path, event="test_review_engineering_written")
            self.assertEqual(run_pipeline(project.path)["next_action"]["command"], "recommend-statistical-revision")

            _write_json(project.path / "review" / "statistical_rescue_plan.json", {"status": "rescue_recommended"})
            refresh_project_passport(project.path, event="test_rescue_written")
            self.assertEqual(run_pipeline(project.path)["next_action"]["command"], "prepare-analysis-revision")

            _write_json(project.path / "review" / "actionable_analysis_tasks.json", {"status": "analysis_revision_prepared"})
            refresh_project_passport(project.path, event="test_analysis_revision_written")
            plan_after_tasks = run_pipeline(project.path)
            self.assertEqual(plan_after_tasks["next_action"]["command"], "prepare-data-acquisition")

            _write_json(project.path / "data" / "data_acquisition_tasks.json", {"status": "tasks_written", "task_count": 1, "tasks": []})
            refresh_project_passport(project.path, event="test_data_acquisition_tasks_written")
            plan_after_data_tasks = run_pipeline(project.path)
            self.assertEqual(plan_after_data_tasks["next_action"]["command"], "plan-figures")
            self.assertIn("--use-review-tasks", plan_after_data_tasks["next_action"]["cli"])

            _write_json(project.path / "results" / "figure_plan.json", {"status": "written", "used_review_tasks": True, "figures": []})
            refresh_project_passport(project.path, event="test_review_figure_plan_written")
            code_after_figures = run_pipeline(project.path)
            self.assertEqual(code_after_figures["next_action"]["command"], "generate-analysis-code")
            self.assertIn("--use-review-tasks", code_after_figures["next_action"]["cli"])

            _write_json(project.path / "methods" / "analysis_code_manifest.json", {
                "status": "written",
                "declared_outputs": ["results/tables/metrics.csv", "results/tables/review_task_coverage.csv"],
                "review_task_coverage": {"enabled": True},
            })
            refresh_project_passport(project.path, event="test_review_codegen_written")
            verify_after_codegen = run_pipeline(project.path)
            self.assertEqual(verify_after_codegen["next_action"]["command"], "verify-methods")
            self.assertIn("review_task_coverage.csv", verify_after_codegen["next_action"]["cli"])

            _write_json(project.path / "methods" / "run_manifest.yaml", {
                "status": "success",
                "review_task_coverage_issues": [],
                "output_files": ["results/tables/metrics.csv", "results/tables/review_task_coverage.csv"],
            })
            refresh_project_passport(project.path, event="test_review_methods_verified")
            self.assertEqual(run_pipeline(project.path)["next_action"]["command"], "assess-result-validity")

            _write_json(project.path / "results" / "result_validity_report.json", {"decision": "conditional_pass", "review_task_coverage_issues": []})
            refresh_project_passport(project.path, event="test_review_result_validity_written")
            self.assertEqual(run_pipeline(project.path)["next_action"]["command"], "generate-revision-plan")


if __name__ == "__main__":
    unittest.main()
