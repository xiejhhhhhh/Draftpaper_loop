# Copyright (c) 2026 xiejhhhhhh
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import unittest

from draftpaper_cli.plotting_requirements import plan_plotting_requirements, render_requirements_txt


class PlottingRequirementsTests(unittest.TestCase):
    def test_heatmap_figure_plan_adds_composable_heatmap_packages(self) -> None:
        plan = plan_plotting_requirements(
            figure_plan={
                "figures": [
                    {
                        "id": "predictor_matrix",
                        "title": "Predictor correlation structure",
                        "figure_type": "correlation_heatmap",
                        "statistical_transform": ["pearson_correlation_matrix"],
                    }
                ]
            },
            project_meta={"idea": "ecological predictor matrix analysis", "field": "ecology"},
            method_requirements={"user_method": "Use correlation heatmap and multi-panel summary."},
        )

        text = render_requirements_txt(plan)

        self.assertIn("composable_heatmap", plan["matched_rules"])
        self.assertIn("marsilea", text)
        self.assertIn("legendkit", text)

    def test_domain_context_adds_only_relevant_specialized_packages(self) -> None:
        plan = plan_plotting_requirements(
            figure_plan={"figures": [{"figure_type": "scatter_regression", "x": "ndvi", "y": "yield"}]},
            project_meta={"idea": "NDVI climate suitability zoning", "field": "remote sensing agriculture GIS"},
            method_requirements={"user_method": "Use NDVI raster summaries for climate zoning."},
        )

        packages = "\n".join(plan["packages"])

        self.assertIn("geopandas", packages)
        self.assertIn("rasterio", packages)
        self.assertIn("cartopy", packages)
        self.assertNotIn("astropy", packages)


if __name__ == "__main__":
    unittest.main()
