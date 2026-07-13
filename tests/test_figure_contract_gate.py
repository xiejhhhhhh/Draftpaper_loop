# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from draftpaper_cli.figure_contract_gate import assess_figure_contracts
from draftpaper_cli.figure_repair import repair_figure_data
from draftpaper_cli.discipline_modules.default import MODULE as DEFAULT_MODULE
from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.project_state import update_stage_status


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class FigureContractGateTests(unittest.TestCase):
    def test_promoted_review_rule_is_deferred_until_results_review(self) -> None:
        rule = {
            "rule_id": "external_validation_figure_gate_test",
            "rule_group_id": "external_validation_figure_gate_test",
            "rule_family": "model_validity",
            "evidence_binding": {
                "registry_record_types": ["figure", "method_output"],
                "required_fields": ["external_validation"],
                "forbidden_conflicts": [],
            },
            "minimum_evidence_required": ["external_validation"],
            "blocking_level": "block_claim",
            "failure_route": "supplement_data_and_method",
            "pipeline_hooks": {"figure_contract": "required"},
            "threshold_policy": {"mode": "contextual"},
            "threshold_source": {"type": "discipline_convention"},
            "maturity": "mature",
            "deployment_state": "promoted_review_rule",
        }
        DEFAULT_MODULE.spec.review_rule_groups.append(rule)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                project = create_project(root=tmp, idea="External validation figure", field="machine learning")
                contracts = [
                    {
                        "figure_id": f"fig_main_{index}",
                        "required_data": [],
                        "required_method": [],
                        "expected_finding": "A validated predictive result.",
                    }
                    for index in range(1, 6)
                ]
                _write_json(project.path / "results" / "figure_contracts.json", {"contracts": contracts, "main_figure_group_count": 5})
                _write_json(project.path / "results" / "figure_plan.json", {"figure_policy": {"minimum_main_figures": 5}, "main_figure_group_count": 5})
                _write_json(project.path / "results" / "storyboard_alignment_report.json", {"all_storyboard_figures_planned": True})
                _write_json(project.path / "methods" / "method_feasibility_report.json", {"decision": "pass"})
                _write_json(project.path / "data" / "data_role_coverage_report.json", {"available_roles": ["local_data"]})

                result = assess_figure_contracts(project.path)
                report = json.loads((project.path / "results" / "figure_contract_gate_report.json").read_text(encoding="utf-8"))

                self.assertEqual(result["decision"], "pass")
                self.assertNotIn("review_rule_gate_decision", report)
                self.assertEqual(report["review_rule_stage"], "post_results")
        finally:
            DEFAULT_MODULE.spec.review_rule_groups.remove(rule)

    def test_legacy_metadata_can_be_completed_by_auditable_semantic_annotation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Legacy scientific figure", field="ecology")
            _write_json(project.path / "results" / "figure_contracts.json", {"contracts": [{
                "figure_id": "fig_response",
                "path": "results/figures/response.png",
                "scientific_question": "How does the predictor relate to the response?",
                "required_variable_roles": ["features", "label_or_response"],
                "forbidden_variable_roles": ["identifier"],
                "required_method_outputs": ["r2"],
                "plot_grammar": "relationship",
                "metric_dimensions": ["dimensionless_score"],
            }]})
            _write_json(project.path / "results" / "figure_plan.json", {"figures": []})
            _write_json(project.path / "results" / "storyboard_alignment_report.json", {"decision": "pass", "all_storyboard_figures_planned": True})
            _write_json(project.path / "methods" / "method_feasibility_report.json", {"decision": "pass"})
            _write_json(project.path / "methods" / "run_manifest.yaml", {"status": "success", "output_files": []})
            _write_json(project.path / "data" / "data_role_coverage_report.json", {"available_roles": ["local_data"]})
            _write_json(project.path / "results" / "figure_metadata.json", {"figures": [{
                "figure_id": "fig_response",
                "path": "results/figures/response.png",
                "variables": {"x": "predictor", "y": "response"},
                "statistics": {"r2": 0.42},
            }]})
            _write_json(project.path / "results" / "figure_semantic_annotations.json", {"annotations": [{
                "figure_id": "fig_response",
                "x_role": "features",
                "y_role": "label_or_response",
                "variable_roles": ["features", "label_or_response"],
                "series": [{"role": "performance_metric", "unit_family": "dimensionless_score", "metric": "r2"}],
                "method_outputs": ["r2"],
                "plot_grammar": "relationship",
                "evidence_source_ids": ["run:verified", "table:response_metrics"],
            }]})

            result = assess_figure_contracts(project.path)

            self.assertEqual(result["decision"], "pass")

    def test_successful_run_cannot_pass_with_unvalidated_main_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Missing semantic metadata", field="engineering")
            contracts = [
                {
                    "storyboard_id": f"fig_main_{index}",
                    "figure_id": f"fig_main_{index}",
                    "path": f"results/figures/fig_main_{index}.png",
                    "required_data": [],
                    "required_method": [],
                    "scientific_question": "What evidence answers the research question?",
                    "plot_grammar": "relationship",
                    "required_variable_roles": ["features"],
                }
                for index in range(1, 6)
            ]
            _write_json(project.path / "results" / "figure_contracts.json", {"contracts": contracts, "main_figure_group_count": 5})
            _write_json(project.path / "results" / "figure_plan.json", {
                "figure_policy": {"minimum_main_figures": 5},
                "main_figure_group_count": 5,
                "figures": [],
            })
            _write_json(project.path / "results" / "storyboard_alignment_report.json", {"decision": "pass", "all_storyboard_figures_planned": True})
            _write_json(project.path / "methods" / "method_feasibility_report.json", {"decision": "pass"})
            _write_json(project.path / "methods" / "run_manifest.yaml", {
                "status": "success",
                "output_files": [f"results/figures/fig_main_{index}.png" for index in range(1, 6)],
            })
            _write_json(project.path / "data" / "data_role_coverage_report.json", {"available_roles": ["local_data"]})
            _write_json(project.path / "results" / "figure_metadata.json", {"figures": []})

            result = assess_figure_contracts(project.path)

            self.assertEqual(result["decision"], "blocked")
            report = json.loads((project.path / "results" / "figure_semantic_validation_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["validated_figure_count"], 0)
            self.assertEqual(report["required_main_figure_count"], 5)
            self.assertEqual(report["decision"], "blocked")

    def test_post_run_semantic_validation_does_not_reopen_verified_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Post-run semantic validation", field="machine learning")
            _write_json(project.path / "results" / "figure_contracts.json", {"contracts": [{
                "figure_id": "fig_main",
                "path": "results/figures/fig_main.png",
                "required_data": [],
                "required_method": [],
                "expected_finding": "Validated result",
                "required_variable_roles": ["model_variant", "performance_metric"],
                "required_method_outputs": ["f1"],
                "plot_grammar": "model_comparison",
                "metric_dimensions": ["dimensionless_score"],
            }]})
            _write_json(project.path / "results" / "figure_plan.json", {"figures": []})
            _write_json(project.path / "results" / "storyboard_alignment_report.json", {"all_storyboard_figures_planned": True})
            _write_json(project.path / "methods" / "method_feasibility_report.json", {"decision": "pass"})
            _write_json(project.path / "data" / "data_role_coverage_report.json", {"available_roles": ["local_data"]})
            _write_json(project.path / "methods" / "run_manifest.yaml", {
                "status": "success", "output_files": ["results/figures/fig_main.png"]
            })
            _write_json(project.path / "results" / "figure_metadata.json", {"figures": [{
                "figure_id": "fig_main",
                "path": "results/figures/fig_main.png",
                "variable_roles": ["model_variant", "performance_metric"],
                "series": [{"role": "performance_metric", "unit_family": "dimensionless_score"}],
                "method_outputs": ["f1"],
                "plot_grammar": "model_comparison",
            }]})
            update_stage_status(project.path, "code", "approved")
            update_stage_status(project.path, "methods", "approved")

            result = assess_figure_contracts(project.path)
            state = json.loads((project.path / "project.json").read_text(encoding="utf-8"))

            self.assertEqual(result["decision"], "pass")
            self.assertEqual(state["stages"]["code"]["status"], "approved")
            self.assertFalse(state["stages"]["code"]["stale"])
            self.assertEqual(state["stages"]["figure_contracts"]["status"], "approved")

    def test_semantically_invalid_rendered_figure_blocks_contract_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Scientific figure validation", field="astronomy")
            contracts = [
                {
                    "storyboard_id": f"fig_main_{index}",
                    "figure_id": f"fig_main_{index}",
                    "path": f"results/figures/fig_main_{index}.png",
                    "required_data": [],
                    "required_method": [],
                    "scientific_question": "Does temporal behavior distinguish source classes?",
                    "required_variable_roles": ["temporal_feature", "class_label"] if index == 1 else [],
                    "forbidden_variable_roles": ["identifier"] if index == 1 else [],
                    "plot_grammar": "grouped_distribution" if index == 1 else "",
                }
                for index in range(1, 6)
            ]
            _write_json(project.path / "results" / "figure_contracts.json", {"contracts": contracts, "main_figure_group_count": 5})
            _write_json(project.path / "results" / "figure_plan.json", {
                "figure_policy": {"minimum_main_figures": 5},
                "main_figure_group_count": 5,
                "figures": [],
            })
            _write_json(project.path / "results" / "storyboard_alignment_report.json", {"decision": "pass", "all_storyboard_figures_planned": True})
            _write_json(project.path / "methods" / "method_feasibility_report.json", {"decision": "pass"})
            _write_json(project.path / "methods" / "run_manifest.yaml", {
                "status": "success",
                "output_files": [f"results/figures/fig_main_{index}.png" for index in range(1, 6)],
            })
            _write_json(project.path / "data" / "data_role_coverage_report.json", {"available_roles": ["local_data"]})
            _write_json(project.path / "results" / "figure_metadata.json", {
                "figures": [
                    {
                        "figure_id": "fig_main_1",
                        "path": "results/figures/fig_main_1.png",
                        "x_role": "source_id",
                        "y_role": "obs_id",
                        "plot_grammar": "scatter",
                    }
                ]
            })

            result = assess_figure_contracts(project.path)
            report = json.loads((project.path / "results" / "figure_semantic_validation_report.json").read_text(encoding="utf-8"))

            self.assertEqual(result["decision"], "blocked")
            self.assertIn(
                "identifier_only_scientific_plot",
                {issue["kind"] for issue in report["figure_checks"][0]["issues"]},
            )

    def test_main_contract_requires_explicit_method_source_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Transformer classification", field="astronomy machine learning")
            contracts = [
                {
                    "storyboard_id": f"fig_main_{index}",
                    "figure_id": f"fig_main_{index}",
                    "required_data": [],
                    "required_method": ["time_aware_transformer"] if index == 1 else [],
                    "expected_finding": "main empirical finding",
                }
                for index in range(1, 6)
            ]
            _write_json(project.path / "results" / "figure_contracts.json", {"contracts": contracts, "main_figure_group_count": 5})
            _write_json(project.path / "results" / "figure_plan.json", {
                "figure_policy": {"minimum_main_figures": 5},
                "main_figure_group_count": 5,
                "figures": [],
            })
            _write_json(project.path / "results" / "storyboard_alignment_report.json", {"decision": "pass", "all_storyboard_figures_planned": True})
            _write_json(project.path / "methods" / "method_feasibility_report.json", {"decision": "pass"})
            _write_json(project.path / "data" / "data_role_coverage_report.json", {"available_roles": ["local_data"]})

            result = assess_figure_contracts(project.path)
            report = json.loads((project.path / "results" / "figure_contract_gate_report.json").read_text(encoding="utf-8"))

            self.assertEqual(result["decision"], "blocked")
            self.assertIn(
                "missing_method_source_evidence",
                {issue["kind"] for issue in report["contract_checks"][0]["issues"]},
            )

    def test_figure_contract_gate_routes_missing_data_to_repair(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Transformer classification", field="astronomy machine learning")
            _write_json(project.path / "results" / "figure_contracts.json", {"contracts": [{"storyboard_id": "fig_main", "required_data": ["flux", "class_label"], "required_method": ["time_aware_transformer"], "expected_finding": "classification performance"}]})
            _write_json(project.path / "results" / "figure_plan.json", {"figures": []})
            _write_json(project.path / "results" / "storyboard_alignment_report.json", {"decision": "pass", "all_storyboard_figures_planned": True})
            _write_json(project.path / "methods" / "method_feasibility_report.json", {"decision": "pass"})
            _write_json(project.path / "data" / "data_role_coverage_report.json", {"available_roles": ["spectral_or_remote_sensing_features"]})

            result = assess_figure_contracts(project.path)
            report = json.loads((project.path / "results" / "figure_contract_gate_report.json").read_text(encoding="utf-8"))

            self.assertEqual(result["decision"], "blocked")
            self.assertEqual(report["recommended_next_action"]["command"], "repair-figure-data")
            self.assertEqual(report["contract_checks"][0]["figure_id"], "fig_main")

    def test_generated_figure_count_can_exceed_main_group_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Six main figure groups with appendix diagnostics", field="astronomy machine learning")
            contracts = [
                {"storyboard_id": f"fig_main_{index}", "figure_id": f"fig_main_{index}", "required_data": [], "required_method": [], "expected_finding": "main empirical finding"}
                for index in range(1, 6)
            ]
            _write_json(project.path / "results" / "figure_contracts.json", {"contracts": contracts, "main_figure_group_count": 5})
            _write_json(project.path / "results" / "figure_plan.json", {
                "figure_policy": {"minimum_main_figures": 5, "target_main_figures": 6},
                "main_figure_group_count": 5,
                "generated_figure_count": 9,
                "supporting_figure_count": 4,
                "appendix_figure_count": 4,
                "figures": [],
            })
            _write_json(project.path / "results" / "storyboard_alignment_report.json", {"decision": "pass", "all_storyboard_figures_planned": True})
            _write_json(project.path / "methods" / "method_feasibility_report.json", {"decision": "pass"})
            _write_json(project.path / "data" / "data_role_coverage_report.json", {"available_roles": ["local_data"]})

            result = assess_figure_contracts(project.path)
            report = json.loads((project.path / "results" / "figure_contract_gate_report.json").read_text(encoding="utf-8"))

            self.assertEqual(result["decision"], "pass")
            self.assertEqual(report["main_figure_group_count"], 5)
            self.assertEqual(report["generated_figure_count"], 9)

    def test_appendix_contract_entries_do_not_block_main_figure_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Main figures plus appendix checks", field="astronomy machine learning")
            contracts = [
                {"storyboard_id": f"fig_main_{index}", "figure_id": f"fig_main_{index}", "required_data": [], "required_method": [], "expected_finding": "main finding"}
                for index in range(1, 6)
            ]
            contracts.append({
                "storyboard_id": "fig_appendix_diagnostic",
                "figure_id": "fig_appendix_diagnostic",
                "required_data": ["nonexistent_appendix_role"],
                "required_method": [],
                "manuscript_role": "appendix",
                "counts_toward_main_figures": False,
            })
            _write_json(project.path / "results" / "figure_contracts.json", {"contracts": contracts, "main_figure_group_count": 5})
            _write_json(project.path / "results" / "figure_plan.json", {"figure_policy": {"minimum_main_figures": 5}, "main_figure_group_count": 5, "figures": []})
            _write_json(project.path / "results" / "storyboard_alignment_report.json", {"decision": "pass", "all_storyboard_figures_planned": True})
            _write_json(project.path / "methods" / "method_feasibility_report.json", {"decision": "pass"})
            _write_json(project.path / "data" / "data_role_coverage_report.json", {"available_roles": ["local_data"]})

            result = assess_figure_contracts(project.path)

            self.assertEqual(result["decision"], "pass")

    def test_repair_figure_data_consumes_contract_gate_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Missing light curve contract", field="astronomy")
            _write_json(project.path / "results" / "figure_contracts.json", {"contracts": [{"storyboard_id": "fig_lc", "figure_id": "fig_lc", "title": "Light-curve evidence", "required_data": ["light_curve"], "expected_finding": "light-curve separation"}]})
            _write_json(project.path / "results" / "figure_plan.json", {"figures": []})
            _write_json(project.path / "results" / "storyboard_alignment_report.json", {"decision": "pass", "all_storyboard_figures_planned": True})
            _write_json(project.path / "methods" / "method_feasibility_report.json", {"decision": "pass"})
            _write_json(project.path / "data" / "data_role_coverage_report.json", {"available_roles": ["source_catalog"]})
            assess_figure_contracts(project.path)

            plan = repair_figure_data(project.path)

            self.assertTrue(plan["tasks"])
            self.assertEqual(plan["tasks"][0]["storyboard_id"], "fig_lc")
            self.assertIn("light_curve", plan["tasks"][0]["missing"])


if __name__ == "__main__":
    unittest.main()
