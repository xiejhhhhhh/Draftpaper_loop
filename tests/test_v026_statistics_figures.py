from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from draftpaper_cli.project_scaffold import create_project
from tests.test_v026_workspace_blueprint import _write_json, prepare_formal_blueprint


class StatisticsAndFiguresV026Tests(unittest.TestCase):
    def test_astronomy_sky_partition_rule_is_preferred_for_spatial_validation(self) -> None:
        from draftpaper_cli.statistical_validation import _FAMILY_DEFINITIONS

        self.assertIn(
            "sky_partition_overlap_validation",
            _FAMILY_DEFINITIONS["spatial_validation"]["preferred_rules"],
        )

    def test_unsupervised_multiview_plan_uses_partition_statistics_not_supervised_calibration(self) -> None:
        from draftpaper_cli.statistical_validation import _task_families

        families = _task_families(
            "unsupervised consensus clustering cross-view concordance ARI NMI optimal label alignment permutation null stratified concordance",
            {"primary_discipline": "astronomy", "secondary_disciplines": ["machine_learning"]},
        )

        self.assertIn("unsupervised_partition_validation", families)
        self.assertIn("partition_concordance", families)
        self.assertIn("label_alignment_and_null", families)
        self.assertIn("stratified_concordance_support", families)
        self.assertNotIn("classification_validation", families)
        self.assertNotIn("calibration", families)
        self.assertNotIn("regression_fit_diagnostics", families)

    def test_model_variants_and_literature_agreement_do_not_imply_partition_concordance(self) -> None:
        from draftpaper_cli.statistical_validation import _task_families

        families = _task_families(
            "supervised classifier variants compare physical intervals with observational literature agreement",
            {"primary_discipline": "astronomy", "secondary_disciplines": ["machine_learning"]},
        )

        self.assertIn("classification_validation", families)
        self.assertNotIn("partition_concordance", families)

    def test_task_aware_statistical_contracts_cover_cross_discipline_cases(self) -> None:
        from draftpaper_cli.statistical_validation import build_statistical_validation_contract

        cases = [
            ("Astronomical image representation classification with anomaly candidates", "astronomy machine learning", {"classification_validation", "representation_confounding", "anomaly_stability"}),
            ("Spatial NDVI regression with grouped validation", "geography machine learning", {"spatial_validation", "regression_fit_diagnostics"}),
            ("Censored clinical survival model", "bioinformatics medicine", {"survival_validation"}),
            ("Quantum simulation convergence under boundary conditions", "physics quantum science", {"simulation_convergence"}),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            for index, (idea, field, expected) in enumerate(cases):
                project = create_project(root=Path(tmp) / str(index), idea=idea, field=field)
                blueprint = {"status": "written", "research_claims": [], "figure_storyboard": {"figures": []}, "method_plan": {"method_tasks": []}}
                _write_json(project.path / "research_plan" / "research_blueprint.json", blueprint)
                build_statistical_validation_contract(project.path, blueprint=blueprint)
                contract = json.loads((project.path / "research_plan" / "statistical_validation_contract.json").read_text(encoding="utf-8"))
                self.assertTrue(expected.issubset(set(contract["task_families"])), (idea, contract["task_families"]))
                self.assertTrue(all(item["threshold_policy"]["universal_fixed_threshold_forbidden"] for item in contract["validations"]))

    def test_review_rule_gaps_are_explicit_not_silent_passes(self) -> None:
        from draftpaper_cli.statistical_validation import assess_review_rule_coverage

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Anomaly ranking stability", field="machine learning")
            blueprint = {"status": "written", "research_claims": [], "figure_storyboard": {"figures": []}, "method_plan": {"method_tasks": []}}
            _write_json(project.path / "research_plan" / "research_blueprint.json", blueprint)
            from draftpaper_cli.statistical_validation import build_statistical_validation_contract
            build_statistical_validation_contract(project.path, blueprint=blueprint)
            result = assess_review_rule_coverage(project.path)
            report = json.loads((project.path / result["report"]).read_text(encoding="utf-8"))
            if report["missing_rule_families"]:
                self.assertEqual(report["decision"], "advisory_and_rescue_required")

    def test_confirmed_plan_attaches_hash_panels_and_caption_without_filler(self) -> None:
        from draftpaper_cli.figure_contracts_v026 import (
            ConfirmedFigureContractError,
            attach_confirmed_contract_to_plan,
            validate_confirmed_figure_alignment,
            validate_figure_captions,
        )
        from draftpaper_cli.research_plan_confirmation import confirm_research_plan, review_research_plan

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Strict figure", field="machine learning")
            prepare_formal_blueprint(project.path)
            review = review_research_plan(project.path)
            confirm_research_plan(project.path, plan_hash=review["plan_hash"], accept_limitations=True)
            storyboard = json.loads((project.path / "research_plan" / "figure_storyboard.json").read_text(encoding="utf-8"))["figures"][0]
            figure = {
                "id": "fig_primary",
                "storyboard_id": "fig_primary",
                "figure_role": "main_result",
                "required_data": storyboard["required_data"],
                "required_method": storyboard["required_method"],
            }
            attached, plan_hash = attach_confirmed_contract_to_plan(project.path, [figure])
            self.assertEqual(attached[0]["confirmed_plan_hash"], plan_hash)
            self.assertEqual(attached[0]["panel_contract"][0]["panel_id"], "fig_primary_panel_1")
            _write_json(project.path / "results" / "figure_plan.json", {"figures": attached})
            self.assertEqual(validate_confirmed_figure_alignment(project.path)["decision"], "pass")
            self.assertEqual(validate_figure_captions(project.path)["decision"], "pass")
            self.assertEqual(len(attached), 1)

            attached[0]["panel_contract"][0]["required_method"] = "silent_substitute_method"
            _write_json(project.path / "results" / "figure_plan.json", {"figures": attached})
            with self.assertRaisesRegex(ConfirmedFigureContractError, "diverges"):
                validate_confirmed_figure_alignment(project.path)

    def test_pre_execution_support_exposes_rescue_and_scope_routes(self) -> None:
        from draftpaper_cli.pre_execution_support import assess_pre_execution_support, prepare_pre_execution_rescue

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Uncommon grouped classifier", field="machine learning")
            prepare_formal_blueprint(project.path)
            result = assess_pre_execution_support(project.path)
            report = json.loads((project.path / result["report"]).read_text(encoding="utf-8"))
            self.assertEqual({item["route"] for item in report["route_options"]}, {"supplement_data_or_methods", "downgrade_research_scope"})
            rescue = prepare_pre_execution_rescue(project.path)
            self.assertEqual(rescue["status"], "prepared")
            tasks = json.loads((project.path / rescue["tasks"]).read_text(encoding="utf-8"))
            self.assertTrue(all(item["scientific_contract_change_forbidden"] for item in tasks["tasks"]))


if __name__ == "__main__":
    unittest.main()
