# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

from typing import Any

from .base import context_text, issue_payload


def discover(context: dict[str, Any], discipline_profile: dict[str, Any]) -> list[dict[str, Any]]:
    text = context_text(context)
    evidence = ["machine-learning discipline profile", "project archive context"]
    gaps: list[dict[str, Any]] = [
        issue_payload(
            code="machine_learning_data_leakage_audit",
            title="Audit data leakage before trusting model performance",
            severity="blocking",
            target_stage="methods",
            rationale="Machine-learning manuscripts are commonly rejected when preprocessing, feature construction, temporal order, spatial grouping, subject identity, or duplicate samples leak information across train and test splits.",
            actions=[
                "verify that preprocessing, scaling, feature selection, and imputation are fitted only on training data",
                "check duplicate, subject-level, spatial, temporal, or group leakage before generating final figures",
                "record the accepted split policy and rerun method verification after leakage checks",
            ],
            requires_user_confirmation=True,
            confirmation_question="Which leakage risks apply here: duplicate samples, subject identity, spatial groups, time order, preprocessing, or label-derived features?",
            evidence=evidence,
        ),
        issue_payload(
            code="machine_learning_baseline_ablation",
            title="Require baseline and ablation evidence",
            severity="major",
            target_stage="methods",
            rationale="Reviewers expect complex models to be compared with simpler baselines and ablations that show which data streams, features, or modules contribute evidence.",
            actions=[
                "add a transparent baseline such as majority class, linear/logistic model, random forest, or simple temporal model as appropriate",
                "run ablations for major feature groups, modalities, model modules, or preprocessing steps",
                "summarize whether the proposed method improves enough to justify its complexity",
            ],
            requires_user_confirmation=True,
            confirmation_question="Which baselines and ablations should be mandatory for this paper before Results are rewritten?",
            evidence=evidence,
        ),
        issue_payload(
            code="machine_learning_validation_split_robustness",
            title="Check validation split robustness and uncertainty",
            severity="major",
            target_stage="methods",
            rationale="A single random split can overstate performance, especially with small, clustered, imbalanced, temporal, or spatial data.",
            actions=[
                "use repeated cross-validation, grouped validation, temporal holdout, spatial holdout, or external validation when scientifically appropriate",
                "report confidence intervals, standard deviations, or bootstrap intervals for primary metrics",
                "separate exploratory model selection metrics from final held-out evaluation metrics",
            ],
            requires_user_confirmation=True,
            confirmation_question="Should the next analysis use repeated, grouped, temporal, spatial, or external validation?",
            evidence=evidence,
        ),
        issue_payload(
            code="machine_learning_uncertainty_calibration",
            title="Add uncertainty, calibration, and error-analysis review",
            severity="major",
            target_stage="results",
            rationale="For predictive claims, reviewers need more than one headline score; calibration, uncertainty, subgroup errors, and failure cases determine whether results are interpretable.",
            actions=[
                "add calibration or probability reliability checks when probabilistic predictions are used",
                "analyze error patterns by class, subgroup, region, time, or data-quality level",
                "connect figures to failure modes instead of only reporting aggregate performance",
            ],
            requires_user_confirmation=True,
            confirmation_question="Which subgroups, classes, or quality strata should be used for error analysis?",
            evidence=evidence,
        ),
    ]

    if any(term in text for term in ("imbalance", "imbalanced", "rare class", "macro", "f1", "auc", "classification", "classifier")):
        gaps.append(issue_payload(
            code="machine_learning_class_imbalance_metrics",
            title="Use class-imbalance-aware metrics",
            severity="major",
            target_stage="result_validity",
            rationale="Accuracy alone is not sufficient for imbalanced classification; macro-F1, balanced accuracy, AUROC/AUPRC, class-level recall, and confusion matrices are often required.",
            actions=[
                "report class counts and the primary metric chosen for imbalanced data",
                "prefer macro-averaged or class-specific metrics alongside aggregate scores",
                "rerun result validity with metric semantics matched to the prediction task",
            ],
            requires_user_confirmation=True,
            confirmation_question="Is the task imbalanced classification, and should macro-F1, balanced accuracy, AUPRC, or class-level recall be the primary metric?",
            evidence=evidence,
        ))

    return gaps
