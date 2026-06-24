# Copyright (c) 2026 xiejhhhhhh
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

from ..base import DisciplineModule, DisciplineModuleSpec


class DefaultModule(DisciplineModule):
    spec = DisciplineModuleSpec(
        module_id="default",
        display_name="Default cross-disciplinary workflow",
        keywords=["research design", "statistical analysis", "reproducibility"],
        data_roles=["analysis_ready_table", "target_or_response", "predictors", "quality_notes"],
        method_families=["descriptive_statistics", "baseline_model", "sensitivity_analysis"],
        validation_checks=["sample_size_check", "missingness_check", "basic_holdout_or_resampling"],
        figure_families=["data_overview", "feature_distribution", "feature_relationship", "metric_summary"],
        minimum_main_figures=5,
        target_main_figures=6,
        required_figure_groups=["data_overview", "feature_distribution", "feature_relationship", "validation_summary", "metric_summary"],
        formula_families=["descriptive_statistic", "linear_response", "primary_metric"],
        reviewer_risks=["unsupported_claim_strength", "insufficient_validation", "unclear_data_provenance"],
        code_generation_constraints=[
            "Generate analysis code only from declared local, processed, API, or remote-manifest data roles.",
            "Do not invent domain-specific preprocessing when the module does not declare it.",
        ],
        data_connectors=[
            {
                "connector_id": "local_files",
                "display_name": "Local files and processed artifacts",
                "access_modes": ["local_files"],
                "packages": [],
                "package_modules": [],
                "download_or_access": ["read local CSV/TSV/XLSX/JSON/Parquet files", "read supplied result tables and figures"],
                "data_formats": ["CSV", "TSV", "XLSX", "JSON", "Parquet", "PNG", "PDF"],
                "requires_credentials": False,
            }
        ],
    )


MODULE = DefaultModule()
