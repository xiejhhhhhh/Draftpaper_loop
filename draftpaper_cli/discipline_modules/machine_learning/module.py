# Copyright (c) 2026 xiejhhhhhh
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

from ..base import DataConnectorSpec, DisciplineModule, DisciplineModuleSpec, MethodTemplateSpec


class MachineLearningModule(DisciplineModule):
    spec = DisciplineModuleSpec(
        module_id="machine_learning",
        display_name="Machine learning and model evaluation",
        keywords=["machine learning", "deep learning", "transformer", "cnn", "baseline", "ablation"],
        data_roles=["feature_matrix", "target_or_label", "train_validation_test_split", "sample_group", "quality_flag"],
        method_families=[
            "baseline_model",
            "supervised_learning",
            "deep_learning_architecture",
            "cross_validation",
            "ablation_study",
            "error_analysis",
        ],
        validation_checks=[
            "data_leakage_check",
            "train_validation_test_split_check",
            "baseline_comparison",
            "ablation_coverage",
            "uncertainty_or_resampling_check",
        ],
        figure_families=[
            "baseline_vs_model_performance",
            "ablation_summary",
            "confusion_or_error_analysis",
            "learning_curve_or_validation_curve",
            "feature_importance_or_attention_summary",
        ],
        minimum_main_figures=5,
        target_main_figures=6,
        required_figure_groups=[
            "data_overview",
            "class_or_target_distribution",
            "feature_space_structure",
            "baseline_vs_model_performance",
            "ablation_or_error_analysis",
        ],
        formula_families=["loss_function", "classification_metric", "cross_validation_estimator", "ablation_delta"],
        reviewer_risks=[
            "missing_baseline",
            "missing_ablation",
            "data_leakage",
            "overclaiming_without_external_validation",
        ],
        code_generation_constraints=[
            "Require a clear label or response column before supervised model code is generated.",
            "Prefer lightweight baselines before optional deep-learning training scaffolds.",
        ],
        data_connectors=[
            DataConnectorSpec(
                connector_id="local_files",
                display_name="Local ML dataset files",
                access_modes=["local_files"],
                packages=["pandas", "numpy", "scikit-learn"],
                package_modules=["pandas", "numpy", "sklearn"],
                download_or_access=["read local train/validation/test splits", "read image folders", "read feature tables"],
                data_formats=["CSV", "Parquet", "NPY/NPZ", "image folders", "JSONL"],
                requires_credentials=False,
                template_paths=["data/connectors/local_ml_dataset.py.template"],
            ),
            DataConnectorSpec(
                connector_id="kaggle_huggingface",
                display_name="Kaggle or Hugging Face datasets",
                access_modes=["api_access", "cloud_storage"],
                packages=["kaggle", "datasets", "huggingface_hub"],
                package_modules=["kaggle", "datasets", "huggingface_hub"],
                credential_env_vars=["KAGGLE_USERNAME", "KAGGLE_KEY"],
                download_or_access=["Kaggle dataset download", "Hugging Face dataset streaming/download", "cache dataset manifest"],
                data_formats=["CSV", "Parquet", "JSONL", "image folders", "Arrow dataset cache"],
                requires_credentials=True,
                template_paths=["data/connectors/kaggle_huggingface.py.template"],
            ),
        ],
        method_templates=[
            MethodTemplateSpec(
                template_id="baseline_model",
                display_name="Baseline model",
                discipline="machine_learning",
                method_family="baseline_model",
                input_roles=["feature_matrix", "target_or_label"],
                optional_roles=["sample_group", "quality_flag"],
                packages=["pandas", "numpy", "scikit-learn"],
                package_modules=["pandas", "numpy", "sklearn"],
                output_artifacts=["results/tables/baseline_metrics.csv", "results/figures/baseline_vs_model_performance.png"],
                figure_groups=["baseline_vs_model_performance"],
                formula_families=["classification_metric", "cross_validation_estimator"],
                validation_checks=["label_available", "minimum_class_count", "metric_written"],
                template_path="method_templates/baseline_model/template.py",
                aliases=["dummy baseline", "random forest baseline", "classical ml baseline"],
                variants=["dummy_classifier", "random_forest"],
                genericity_rules=["Expose target and feature columns as parameters.", "Do not hard-code dataset names or labels."],
            ),
            MethodTemplateSpec(
                template_id="ablation_study",
                display_name="Ablation study",
                discipline="machine_learning",
                method_family="ablation_study",
                input_roles=["feature_matrix", "target_or_label"],
                optional_roles=["feature_groups", "sample_group"],
                packages=["pandas", "numpy", "scikit-learn"],
                package_modules=["pandas", "numpy", "sklearn"],
                output_artifacts=["results/tables/ablation_metrics.csv", "results/figures/ablation_or_error_analysis.png"],
                figure_groups=["ablation_or_error_analysis"],
                formula_families=["ablation_delta", "classification_metric"],
                validation_checks=["feature_group_available", "baseline_comparison", "metric_written"],
                template_path="method_templates/ablation_study/template.py",
                aliases=["feature group ablation", "component ablation"],
                variants=["drop_one_group", "single_group_only"],
                genericity_rules=["Feature groups must be configuration values.", "Do not encode paper-specific feature names into the template."],
            ),
            MethodTemplateSpec(
                template_id="train_validation_test_split_check",
                display_name="Train/validation/test split check",
                discipline="machine_learning",
                method_family="data_split_validation",
                input_roles=["feature_matrix", "target_or_label", "train_validation_test_split"],
                optional_roles=["sample_group"],
                packages=["pandas", "numpy", "scikit-learn"],
                package_modules=["pandas", "numpy", "sklearn"],
                output_artifacts=["results/tables/split_integrity_report.csv", "results/figures/class_or_target_distribution.png"],
                figure_groups=["class_or_target_distribution"],
                formula_families=["split_ratio", "class_support_ratio"],
                validation_checks=["no_overlap_between_splits", "class_balance_by_split", "group_leakage_check"],
                template_path="method_templates/train_validation_test_split_check/template.py",
                aliases=["split integrity", "leakage check", "holdout split check"],
                variants=["explicit_split_column", "generated_stratified_split"],
                genericity_rules=["Split column names must be parameters.", "Never encode project-specific sample IDs."],
            ),
        ],
    )


MODULE = MachineLearningModule()
