# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import unittest

from draftpaper_cli.figure_semantics import rendered_semantic_metadata, validate_figure_semantics


class FigureSemanticValidationTests(unittest.TestCase):
    def test_rendered_metric_metadata_exposes_mixed_units(self) -> None:
        metadata = rendered_semantic_metadata(
            {"title": "Model performance", "figure_type": "metric_summary"},
            {
                "variables": {"metrics": ["row_count", "f1_macro"]},
                "statistics": {"row_count": 60, "f1_macro": 0.8667},
            },
        )

        self.assertEqual(metadata["plot_grammar"], "model_comparison")
        self.assertEqual(
            {item["unit_family"] for item in metadata["series"]},
            {"count", "dimensionless_score"},
        )

    def test_rejects_identifier_against_identifier_as_scientific_result(self) -> None:
        result = validate_figure_semantics(
            {
                "figure_id": "fig_science",
                "scientific_question": "Does temporal behavior separate source classes?",
                "required_variable_roles": ["temporal_feature", "class_label"],
                "forbidden_variable_roles": ["identifier"],
                "plot_grammar": "grouped_distribution",
            },
            {
                "x_role": "source_id",
                "y_role": "obs_id",
                "plot_grammar": "scatter",
                "method_outputs": [],
            },
        )

        self.assertEqual(result["decision"], "blocked")
        self.assertIn("identifier_only_scientific_plot", {item["kind"] for item in result["issues"]})

    def test_rejects_mixed_count_and_performance_on_one_metric_axis(self) -> None:
        result = validate_figure_semantics(
            {
                "figure_id": "fig_metrics",
                "scientific_question": "Which model performs best?",
                "required_variable_roles": ["model_variant", "performance_metric"],
                "metric_dimensions": ["dimensionless_score"],
                "plot_grammar": "model_comparison",
            },
            {
                "x_role": "model_variant",
                "series": [
                    {"role": "performance_metric", "unit_family": "dimensionless_score", "metric": "f1_macro"},
                    {"role": "sample_count", "unit_family": "count", "metric": "n_sources"},
                ],
                "plot_grammar": "model_comparison",
            },
        )

        self.assertEqual(result["decision"], "blocked")
        self.assertIn("mixed_unit_families", {item["kind"] for item in result["issues"]})

    def test_rejects_ablation_without_required_variants(self) -> None:
        result = validate_figure_semantics(
            {
                "figure_id": "fig_ablation",
                "scientific_question": "Which modality contributes to classification?",
                "plot_grammar": "ablation",
                "required_panels": ["full", "no_history", "no_spectrum"],
            },
            {
                "plot_grammar": "ablation",
                "panels": ["full"],
                "series": [{"role": "performance_metric", "unit_family": "dimensionless_score"}],
            },
        )

        self.assertEqual(result["decision"], "blocked")
        self.assertIn("missing_required_panel", {item["kind"] for item in result["issues"]})

    def test_accepts_semantically_complete_model_comparison(self) -> None:
        result = validate_figure_semantics(
            {
                "figure_id": "fig_models",
                "scientific_question": "How do verified models compare?",
                "required_variable_roles": ["model_variant", "performance_metric"],
                "required_method_outputs": ["source_held_out_metrics"],
                "metric_dimensions": ["dimensionless_score"],
                "plot_grammar": "model_comparison",
            },
            {
                "x_role": "model_variant",
                "series": [
                    {"role": "performance_metric", "unit_family": "dimensionless_score", "metric": "f1_macro"}
                ],
                "method_outputs": ["source_held_out_metrics"],
                "plot_grammar": "model_comparison",
            },
        )

        self.assertEqual(result["decision"], "pass")


if __name__ == "__main__":
    unittest.main()
