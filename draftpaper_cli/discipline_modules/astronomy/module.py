# Copyright (c) 2026 xiejhhhhhh
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

from ..base import DisciplineModule, DisciplineModuleSpec


class AstronomyModule(DisciplineModule):
    spec = DisciplineModuleSpec(
        module_id="astronomy",
        display_name="Astronomy and astrophysics",
        keywords=["astronomy", "astrophysics", "light curve", "x-ray", "catalog", "transient", "multiwavelength"],
        data_roles=[
            "source_catalog",
            "light_curve_or_time_series",
            "spectral_or_hardness_features",
            "multiwavelength_crossmatch",
            "class_label",
            "observation_quality_flag",
        ],
        method_families=[
            "catalog_crossmatch",
            "time_series_feature_extraction",
            "source_classification",
            "multimodal_fusion",
            "rare_class_validation",
        ],
        validation_checks=[
            "label_leakage_check",
            "class_imbalance_check",
            "survey_or_field_holdout",
            "cadence_and_missingness_check",
        ],
        figure_families=[
            "catalog_coverage_summary",
            "light_curve_feature_distribution",
            "classification_performance_summary",
            "confusion_or_error_analysis",
            "multimodal_feature_contribution",
        ],
        minimum_main_figures=5,
        target_main_figures=6,
        required_figure_groups=[
            "data_overview",
            "catalog_or_sample_coverage",
            "time_series_or_feature_distribution",
            "classification_or_metric_summary",
            "multimodal_or_error_analysis",
        ],
        formula_families=["classification_metric", "time_series_feature", "crossmatch_radius", "class_support_ratio"],
        reviewer_risks=[
            "unverified_catalog_crossmatch",
            "class_imbalance_underreported",
            "cadence_bias_or_selection_effect",
            "missing_external_survey_validation",
        ],
        code_generation_constraints=[
            "Treat remote mission APIs and server manifests as data connectors, not mandatory package dependencies.",
            "Require explicit class labels before supervised source-classification claims.",
        ],
        data_connectors=[
            {
                "connector_id": "mission_archive_api",
                "display_name": "Mission/archive API access",
                "access_modes": ["api_access", "instrument_archive"],
                "packages": ["astroquery", "astropy", "requests"],
                "package_modules": ["astroquery", "astropy", "requests"],
                "download_or_access": ["query mission catalogs", "download table products", "retrieve light-curve or event-list metadata"],
                "data_formats": ["FITS", "VOTable", "CSV", "ECSV", "JSON catalog metadata"],
                "requires_credentials": False,
            },
            {
                "connector_id": "remote_server_ssh",
                "display_name": "Remote server or instrument archive workspace",
                "access_modes": ["remote_server_ssh"],
                "packages": ["paramiko", "scp"],
                "package_modules": ["paramiko", "scp"],
                "credential_env_vars": ["DRAFTPAPER_SSH_HOST", "DRAFTPAPER_SSH_USER"],
                "download_or_access": ["create remote file manifest", "run server-side preprocessing", "download processed tables and figures"],
                "data_formats": ["remote manifest CSV", "FITS", "CSV", "Parquet", "PNG"],
                "requires_credentials": True,
            },
        ],
    )


MODULE = AstronomyModule()
