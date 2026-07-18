# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import ast
import csv
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
from ..data_feasibility import DataGateError, validate_data_feasibility_for_methods
from ..execution_policy import redact_sensitive, sanitized_environment
from ..html_utils import write_html_report
from ..io_utils import read_json, read_text
from ..latex_utils import safe_latex_text
from ..method_plan import MethodPlanError, validate_method_plan_for_methods
from ..manuscript_composer import SectionCompositionError, select_validated_section_draft
from ..observations import load_observations
from ..project_scaffold import _write_json, utc_now
from ..project_state import load_project, mark_stage_stale, update_stage_status
from ..reference_usage import ensure_reference_usage_plan, missing_entries_for_section
from ..evidence_registry import EVIDENCE_REGISTRY_JSON, build_scientific_evidence_registry, ensure_registry_consistent
from ..result_evidence import ResultEvidenceError, resolve_result_evidence
from ..writing_brief import METHOD_WRITING_BRIEF_HTML, METHOD_WRITING_BRIEF_JSON, build_method_writing_brief
from ..write_set_guard import BoundaryViolation, resolve_confined_path

from .common import (
    _drop_internal_method_sentences,
    _read_json,
)

def _entry(entry_id: str, name: str, latex: str, source: str, explanation: str, *, method_step: str = "", used_by_figures: list[str] | None = None) -> dict[str, Any]:
    return {
        "id": entry_id,
        "name": name,
        "latex": latex,
        "source": source,
        "variable_explanations": explanation,
        "method_step": method_step,
        "used_by_figures": used_by_figures or [],
    }


def _formula_context_text(manifest: dict[str, Any], figure_metadata: dict[str, Any], method_context: dict[str, Any]) -> str:
    parts: list[str] = [json.dumps(manifest, ensure_ascii=False, default=str), json.dumps(figure_metadata, ensure_ascii=False, default=str)]
    for relative in [
        "project.json",
        "project.yaml",
        "methods/method_code_manifest.json",
        "methods/analysis_code_manifest.json",
        "methods/method_blueprint.json",
        "methods/method_requirements.json",
        "research_plan/method_plan.json",
        "research_plan/figure_storyboard.json",
        "results/figure_plan.json",
    ]:
        project_path = method_context.get("project_path")
        if not project_path:
            continue
        payload = _read_json(Path(str(project_path)) / relative, {})
        if payload:
            if relative == "methods/method_blueprint.json":
                payload = {
                    "method_requirements": payload.get("method_requirements") or {},
                    "method_code_plan": {
                        key: (payload.get("method_code_plan") or {}).get(key)
                        for key in ("method_families", "validation_checks", "storyboard_method_tasks")
                    },
                    "method_formula_plan": payload.get("method_formula_plan") or {},
                }
            parts.append(json.dumps(payload, ensure_ascii=False, default=str))
    return " ".join(parts).lower()


def _planned_formula_entries(
    formula_families: list[str],
    figure_metadata: dict[str, Any],
) -> list[dict[str, Any]]:
    catalog: dict[str, dict[str, Any]] = {
        "coverage_rate": {
            "name": "Cohort coverage rate",
            "latex": r"\begin{equation}r_{\mathrm{valid}}=\frac{N_{\mathrm{valid}}}{N_{\mathrm{source}}}.\end{equation}",
            "explanation": r"Here $N_{\mathrm{source}}$ is the number of objects in the source cohort, $N_{\mathrm{valid}}$ is the number retained after the stated availability or validity check, and $r_{\mathrm{valid}}$ is the corresponding coverage fraction.",
            "step": "cohort construction and missingness",
            "tokens": ("cohort_coverage", "coverage_summary"),
        },
        "principal_component_projection": {
            "name": "Principal-component projection",
            "latex": r"\begin{equation}\mathbf{z}_i=\mathbf{W}_q^{\mathsf T}(\mathbf{x}_i-\boldsymbol{\mu}),\qquad \mathbf{W}_q^{\mathsf T}\mathbf{W}_q=\mathbf{I}_q.\end{equation}",
            "explanation": r"The vector $\mathbf{x}_i$ is the image representation for object $i$, $\boldsymbol{\mu}$ is the sample mean, $\mathbf{W}_q$ contains the first $q$ orthonormal principal directions, and $\mathbf{z}_i$ is the resulting exploratory projection.",
            "step": "representation projection",
            "tokens": ("target_and_confounder_association", "embedding_diagnostic"),
        },
        "multinomial_logistic_regression": {
            "name": "Multinomial logistic probe",
            "latex": r"\begin{equation}P(y_i=c\mid\mathbf{x}_i)=\frac{\exp(\beta_{c0}+\boldsymbol{\beta}_c^{\mathsf T}\mathbf{x}_i)}{\sum_{k=1}^{C}\exp(\beta_{k0}+\boldsymbol{\beta}_k^{\mathsf T}\mathbf{x}_i)}.\end{equation}",
            "explanation": r"The label $y_i$ is the catalogue morphology class for object $i$, $\mathbf{x}_i$ is the selected catalogue, embedding, or combined feature vector, $C$ is the number of retained classes, and $(\beta_{c0},\boldsymbol{\beta}_c)$ are the class-specific intercept and coefficients.",
            "step": "transparent baseline and representation probes",
            "tokens": ("group_held_out_metric", "model_comparison"),
        },
        "balanced_accuracy": {
            "name": "Multiclass balanced accuracy",
            "latex": r"\begin{equation}\mathrm{BA}=\frac{1}{C}\sum_{c=1}^{C}\frac{\mathrm{TP}_c}{\mathrm{TP}_c+\mathrm{FN}_c}.\end{equation}",
            "explanation": r"The number of retained classes is $C$, while $\mathrm{TP}_c$ and $\mathrm{FN}_c$ are the true-positive and false-negative counts for class $c$. Equal averaging across classes reduces domination by the most frequent morphology category.",
            "step": "group-held-out evaluation",
            "tokens": ("group_held_out_metric", "classwise_uncertainty", "confusion_matrix"),
        },
        "macro_f1": {
            "name": "Macro-averaged F1 score",
            "latex": r"\begin{equation}F_{1,c}=\frac{2P_cR_c}{P_c+R_c},\qquad F_{1,\mathrm{macro}}=\frac{1}{C}\sum_{c=1}^{C}F_{1,c}.\end{equation}",
            "explanation": r"For class $c$, $P_c$ and $R_c$ denote precision and recall, respectively; $F_{1,c}$ is their harmonic mean, and $F_{1,\mathrm{macro}}$ averages the class-wise scores over the $C$ retained classes.",
            "step": "class-balanced predictive evaluation",
            "tokens": ("group_held_out_metric", "classwise_uncertainty", "confusion_matrix"),
        },
        "fold_dispersion_or_confidence_interval": {
            "name": "Across-fold dispersion",
            "latex": r"\begin{equation}\bar{s}=\frac{1}{K}\sum_{k=1}^{K}s_k,\qquad \sigma_s=\sqrt{\frac{1}{K-1}\sum_{k=1}^{K}(s_k-\bar{s})^2}.\end{equation}",
            "explanation": r"The score $s_k$ is the evaluation metric on held-out fold $k$, $K$ is the number of group-aware folds, $\bar{s}$ is the fold mean, and $\sigma_s$ summarizes between-fold dispersion.",
            "step": "group-aware uncertainty estimation",
            "tokens": ("group_held_out_metric", "classwise_uncertainty"),
        },
        "incremental_metric_delta": {
            "name": "Incremental metric difference",
            "latex": r"\begin{equation}\Delta s=s_{\mathrm{combined}}-s_{\mathrm{catalog}}.\end{equation}",
            "explanation": r"The score $s_{\mathrm{combined}}$ is obtained from catalogue variables plus the image representation, $s_{\mathrm{catalog}}$ is obtained from the catalogue-only baseline under the same folds, and $\Delta s$ measures incremental predictive association rather than a causal effect.",
            "step": "feature-group ablation",
            "tokens": ("incremental_metric_delta", "ablation"),
        },
        "anomaly_score": {
            "name": "Anomaly ranking score",
            "latex": r"\begin{equation}a_i=-f(\mathbf{x}_i),\end{equation}",
            "explanation": r"The fitted unsupervised detector assigns decision score $f(\mathbf{x}_i)$ to representation $\mathbf{x}_i$; the sign is reversed so that larger $a_i$ denotes a more unusual candidate. The score defines a ranking, not a physical anomaly probability.",
            "step": "candidate anomaly ranking",
            "tokens": ("candidate_stability", "image_gallery"),
        },
        "set_stability_jaccard": {
            "name": "Candidate-set stability",
            "latex": r"\begin{equation}J(A,B)=\frac{|A\cap B|}{|A\cup B|}.\end{equation}",
            "explanation": r"The sets $A$ and $B$ contain the top-ranked anomaly candidates from two resampled fits, and $J(A,B)$ is their Jaccard overlap. Values near one indicate a stable candidate set under the tested perturbation.",
            "step": "anomaly stability analysis",
            "tokens": ("candidate_stability", "image_gallery"),
        },
    }
    figures = [item for item in figure_metadata.get("figures") or [] if isinstance(item, dict)]
    entries: list[dict[str, Any]] = []
    for family in formula_families:
        spec = catalog.get(str(family))
        if not spec:
            continue
        used_by = []
        for figure in figures:
            blob = " ".join([
                str(figure.get("plot_grammar") or ""),
                " ".join(str(item) for item in figure.get("method_outputs") or []),
                " ".join(str(key) for key in (figure.get("statistics") or {}).keys()),
            ]).lower()
            if any(token in blob for token in spec["tokens"]):
                used_by.append(str(figure.get("figure_id") or figure.get("storyboard_id") or figure.get("path") or ""))
        entries.append(_entry(
            str(family),
            str(spec["name"]),
            str(spec["latex"]),
            "current method formula plan and verified project-local method contract",
            str(spec["explanation"]),
            method_step=str(spec["step"]),
            used_by_figures=[item for item in used_by if item],
        ))
    return entries


def _formula_entries(manifest: dict[str, Any], figure_metadata: dict[str, Any], method_context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    method_context = method_context or {}
    project_path = Path(str(method_context.get("project_path") or ""))
    blueprint = _read_json(project_path / "methods" / "method_blueprint.json", {}) if str(project_path) else {}
    formula_plan = blueprint.get("method_formula_plan") if isinstance(blueprint.get("method_formula_plan"), dict) else {}
    planned_families = [str(item) for item in formula_plan.get("formula_families") or [] if str(item)]
    if planned_families:
        return _planned_formula_entries(planned_families, figure_metadata)
    entries: list[dict[str, Any]] = []
    metrics = {str(key).lower(): value for key, value in (manifest.get("metrics") or {}).items()}
    context_text = _formula_context_text(manifest, figure_metadata, method_context)
    has_transformer = any(token in context_text for token in ["transformer", "attention", "time-aware", "time aware", "time2vec", "sequence encoder", "light curve", "light-curve"])
    has_classification = any(token in context_text for token in ["classification", "classifier", "softmax", "cross_entropy", "cross entropy", "class label", "confusion"])
    has_ablation = "ablation" in context_text
    has_auc = any(token in context_text for token in ["auc", "roc", "receiver operating"])
    figure_ids = [str(item.get("figure_id") or item.get("id") or item.get("path") or "") for item in figure_metadata.get("figures") or [] if isinstance(item, dict)]
    if has_transformer:
        entries.append(_entry(
            "time2vec_embedding",
            "Time-aware embedding",
            r"\begin{equation}\mathrm{Time2Vec}(t)=\left[\omega_0 t+\phi_0,\ \sin(\omega_1 t+\phi_1),\ldots,\sin(\omega_k t+\phi_k)\right].\end{equation}",
            "method blueprint and code context",
            r"Here $t$ denotes the observation time or relative time interval, $\omega_j$ and $\phi_j$ are learned frequency and phase parameters, and $k$ is the number of periodic time components used to encode irregular temporal structure.",
            method_step="temporal feature encoding",
            used_by_figures=figure_ids,
        ))
        entries.append(_entry(
            "sinusoidal_position_encoding",
            "Sinusoidal sequence position encoding",
            r"\begin{equation}p_{i,2j}=\sin\left(i/10000^{2j/d}\right),\qquad p_{i,2j+1}=\cos\left(i/10000^{2j/d}\right).\end{equation}",
            "method blueprint and code context",
            r"The index $i$ is the sequence position, $j$ indexes paired encoding dimensions, and $d$ is the embedding dimension. The encoding lets the sequence model distinguish event order even when the input tokens are padded or irregularly sampled.",
            method_step="sequence representation",
            used_by_figures=figure_ids,
        ))
        entries.append(_entry(
            "masked_sequence_pooling",
            "Masked sequence pooling",
            r"\begin{equation}\bar{\mathbf{h}}=\frac{\sum_{i=1}^{T}m_i\mathbf{h}_i}{\sum_{i=1}^{T}m_i+\epsilon}.\end{equation}",
            "method blueprint and code context",
            r"The hidden state $\mathbf{h}_i$ represents the encoded token at position $i$, $m_i\in\{0,1\}$ indicates whether that token is observed rather than padded, $T$ is the maximum sequence length, and $\epsilon$ prevents division by zero.",
            method_step="sequence aggregation",
            used_by_figures=figure_ids,
        ))
    if has_transformer or has_classification:
        entries.append(_entry(
            "multimodal_classifier",
            "Multimodal classifier logits",
            r"\begin{equation}\mathbf{z}=\mathbf{W}\,[\bar{\mathbf{h}};\mathbf{x}_{\mathrm{obs}};\mathbf{x}_{\mathrm{spec}}]+\mathbf{b},\qquad \hat{\mathbf{p}}=\mathrm{softmax}(\mathbf{z}).\end{equation}",
            "method blueprint and code context",
            r"The vector $\bar{\mathbf{h}}$ summarizes the long-term sequence, $\mathbf{x}_{\mathrm{obs}}$ stores current-observation descriptors, $\mathbf{x}_{\mathrm{spec}}$ stores spectral or hardness-ratio features when available, $\mathbf{W}$ and $\mathbf{b}$ are classifier parameters, and $\hat{\mathbf{p}}$ is the predicted class-probability vector.",
            method_step="feature fusion and prediction",
            used_by_figures=figure_ids,
        ))
        entries.append(_entry(
            "cross_entropy_loss",
            "Cross-entropy objective",
            r"\begin{equation}\mathcal{L}_{\mathrm{CE}}=-\frac{1}{N}\sum_{i=1}^{N}\sum_{c=1}^{C}y_{ic}\log(\hat{p}_{ic}).\end{equation}",
            "method blueprint and code context",
            r"The sample index is $i$, $N$ is the number of labelled samples, $C$ is the number of classes, $y_{ic}$ is the one-hot class indicator, and $\hat{p}_{ic}$ is the model probability assigned to class $c$.",
            method_step="model optimization",
            used_by_figures=figure_ids,
        ))
    if "f1" in metrics or "f1_score" in metrics or "f1_macro" in metrics or has_classification:
        entries.append(_entry(
            "f1_score",
            "F1 score",
            r"\begin{equation}F_1 = 2\cdot \frac{\mathrm{precision}\cdot \mathrm{recall}}{\mathrm{precision}+\mathrm{recall}},\qquad F_{1,\mathrm{macro}}=\frac{1}{C}\sum_{c=1}^{C}F_{1,c}.\end{equation}",
            "verified metric output",
            r"Precision is the fraction of predicted positives that are correct, recall is the fraction of true positives recovered, $F_{1,c}$ is the class-wise F1 score, and $C$ is the number of classes. Macro averaging treats classes equally and is therefore useful when source classes have different support.",
            method_step="classification evaluation",
            used_by_figures=figure_ids,
        ))
    if "baseline_accuracy" in metrics:
        entries.append(_entry(
            "majority_baseline",
            "Majority-class baseline",
            r"\begin{equation}\mathrm{Acc}_{\mathrm{baseline}} = \max_k \frac{n_k}{N}.\end{equation}",
            "verified metric output",
            r"The term $n_k$ is the number of samples in class $k$, and $N$ is the total number of samples. This baseline reports the accuracy obtained by always predicting the most frequent class.",
            method_step="baseline comparison",
            used_by_figures=figure_ids,
        ))
    if has_auc or "roc_auc" in metrics or "auc" in metrics:
        entries.append(_entry(
            "roc_auc",
            "Area under the ROC curve",
            r"\begin{equation}\mathrm{AUC}=\int_{0}^{1}\mathrm{TPR}(u)\,d\mathrm{FPR}(u).\end{equation}",
            "verified metric output",
            r"The true-positive rate $\mathrm{TPR}$ and false-positive rate $\mathrm{FPR}$ are evaluated across score thresholds $u$. For multiclass tasks, the reported AUC must specify whether one-vs-rest or macro-averaged aggregation is used.",
            method_step="threshold-independent evaluation",
            used_by_figures=figure_ids,
        ))
    if has_classification:
        entries.append(_entry(
            "confusion_matrix",
            "Confusion matrix",
            r"\begin{equation}M_{ab}=\sum_{i=1}^{N}\mathbb{I}(y_i=a,\hat{y}_i=b).\end{equation}",
            "classification diagnostics",
            r"The element $M_{ab}$ counts samples whose true class is $a$ and predicted class is $b$, $y_i$ is the true label, $\hat{y}_i$ is the predicted label, and $\mathbb{I}(\cdot)$ is the indicator function.",
            method_step="error structure analysis",
            used_by_figures=figure_ids,
        ))
    if has_ablation:
        entries.append(_entry(
            "ablation_delta",
            "Ablation effect size",
            r"\begin{equation}\Delta s_j=s_{\mathrm{full}}-s_{\setminus j}.\end{equation}",
            "ablation diagnostics",
            r"The score $s_{\mathrm{full}}$ is the metric from the complete model, $s_{\setminus j}$ is the metric after removing feature group or module $j$, and $\Delta s_j$ estimates that component's contribution under the same validation protocol.",
            method_step="component contribution analysis",
            used_by_figures=figure_ids,
        ))
    for item in figure_metadata.get("figures") or []:
        statistics = item.get("statistics") or {}
        figure_id = str(item.get("figure_id") or item.get("path") or "figure")
        if "pearson_r" in statistics:
            entries.append(_entry(f"{figure_id}_pearson_r", "Pearson correlation", r"\begin{equation}r = \frac{\sum_i (x_i-\bar{x})(y_i-\bar{y})}{\sqrt{\sum_i (x_i-\bar{x})^2}\sqrt{\sum_i (y_i-\bar{y})^2}}.\end{equation}", figure_id, r"The variables $x_i$ and $y_i$ are paired observations for sample $i$, and $\bar{x}$ and $\bar{y}$ are their sample means. The statistic $r$ describes linear association rather than statistical confidence.", method_step="association analysis", used_by_figures=[figure_id]))
        if "r2" in statistics:
            entries.append(_entry(f"{figure_id}_linear_r2", "Linear response and coefficient of determination", r"\begin{equation}y_i = \beta_0+\beta_1x_i+\epsilon_i,\qquad R^2 = 1-\frac{\sum_i (y_i-\hat{y}_i)^2}{\sum_i (y_i-\bar{y})^2}.\end{equation}", figure_id, r"The coefficient $\beta_0$ is the intercept, $\beta_1$ is the fitted slope, $\epsilon_i$ is the residual, $\hat{y}_i$ is the fitted value, and $R^2$ measures explained variance rather than a significance threshold.", method_step="linear response modelling", used_by_figures=[figure_id]))
        if "correlation_matrix" in statistics:
            entries.append(_entry(f"{figure_id}_correlation_matrix", "Pairwise correlation matrix", r"\begin{equation}\mathbf{R}_{jk} = \mathrm{corr}(X_j, X_k).\end{equation}", figure_id, r"The matrix element $\mathbf{R}_{jk}$ is the correlation between variables $X_j$ and $X_k$ and is used to diagnose association or redundancy among measured features.", method_step="feature association analysis", used_by_figures=[figure_id]))
        if "counts" in statistics:
            entries.append(_entry(f"{figure_id}_class_support", "Class-support ratio", r"\begin{equation}\rho_{\mathrm{imbalance}} = \frac{\max_k n_k}{\min_k n_k}.\end{equation}", figure_id, r"The value $n_k$ is the number of samples in class $k$. The ratio $\rho_{\mathrm{imbalance}}$ summarizes imbalance across classes and helps interpret classification metrics.", method_step="sample composition analysis", used_by_figures=[figure_id]))
    seen: set[str] = set()
    unique = []
    for entry in entries:
        if entry["id"] in seen:
            continue
        seen.add(entry["id"])
        unique.append(entry)
    return unique


def _write_method_formulas(project_path: Path, manifest: dict[str, Any]) -> None:
    figure_metadata = _read_json(project_path / "results" / "figure_metadata.json", {})
    entries = _formula_entries(manifest, figure_metadata, {"project_path": str(project_path)})
    payload = {
        "status": "written",
        "generated_at": utc_now(),
        "formula_count": len(entries),
        "formulas": entries,
    }
    _write_json(project_path / "methods" / "method_formula_manifest.json", payload)
    lines = ["% Auto-generated from verified method metrics and figure metadata.", ""]
    for entry in entries:
        lines.extend([
            f"% {entry['id']}: {entry['name']} ({entry['source']})",
            entry["latex"],
            _safe_latex_text(entry.get("variable_explanations", "")),
            "",
        ])
    if not entries:
        lines.append("% No explicit mathematical formula was inferred from the verified outputs.")
    (project_path / "methods" / "method_formulas.tex").write_text("\n".join(lines), encoding="utf-8")


def _safe_latex_text(text: Any) -> str:
    return safe_latex_text(text)


def _latex_formula_entries(context: dict[str, Any]) -> list[dict[str, Any]]:
    payload = context.get("formula_manifest") if isinstance(context.get("formula_manifest"), dict) else {}
    entries = payload.get("formulas") if isinstance(payload, dict) else []
    if not isinstance(entries, list):
        entries = []
    normalized = [entry for entry in entries if isinstance(entry, dict) and str(entry.get("latex") or "").strip()]
    ast_payload = context.get("analysis_formula_ast") if isinstance(context.get("analysis_formula_ast"), dict) else {}
    seen = {str(item.get("formula_id") or item.get("name") or item.get("latex")) for item in normalized}
    for formula in ast_payload.get("formulas") or []:
        if not isinstance(formula, dict) or not formula.get("latex"):
            continue
        formula_id = str(formula.get("formula_id") or formula.get("latex"))
        if formula_id in seen:
            continue
        variables = [item for item in formula.get("variables") or [] if isinstance(item, dict)]
        explanation = "; ".join(
            f"${item.get('symbol')}$ denotes {item.get('meaning')}"
            for item in variables if item.get("symbol") and item.get("meaning")
        )
        normalized.append({
            "formula_id": formula_id,
            "name": formula_id.replace("_", " "),
            "method_step": "validation" if any(token in formula_id.lower() for token in ("ece", "auc", "f1", "metric")) else "model",
            "latex": formula.get("latex"),
            "variables": [item.get("symbol") for item in variables if item.get("symbol")],
            "variable_explanations": explanation + ("." if explanation else ""),
            "analysis_spec_id": formula.get("analysis_spec_id"),
        })
        seen.add(formula_id)
    return normalized


def _render_formula_block(entries: list[dict[str, Any]], *, only_steps: set[str] | None = None) -> str:
    rendered: list[str] = []
    for entry in entries:
        haystack = " ".join(str(entry.get(key) or "") for key in ["id", "name", "method_step", "source"]).lower()
        if only_steps and not any(token in haystack for token in only_steps):
            continue
        name = _safe_latex_text(entry.get("name") or "Method expression")
        latex = str(entry.get("latex") or "").strip()
        if latex and "\\begin{equation}" not in latex:
            latex = "\\begin{equation}" + latex + "\\end{equation}"
        variable_text = _drop_internal_method_sentences(entry.get("variable_explanations") or "")
        if not variable_text and entry.get("variables"):
            variable_text = "Variables in this expression include " + ", ".join(str(item) for item in entry.get("variables") or []) + "."
        variables = variable_text if ("$" in variable_text or "\\" in variable_text) else _safe_latex_text(variable_text)
        rendered.append(f"{name}:\n{latex}\n{variables}".strip())
    return "\n\n".join(rendered)


def _formula_step_tokens(entries: list[dict[str, Any]]) -> set[str]:
    text = " ".join(str(entry.get("id") or "") + " " + str(entry.get("method_step") or "") + " " + str(entry.get("name") or "") for entry in entries).lower()
    tokens: set[str] = set()
    if any(term in text for term in ["time", "position", "sequence", "pooling", "embedding"]):
        tokens.add("sequence")
    if any(term in text for term in ["classifier", "softmax", "cross-entropy", "loss", "prediction"]):
        tokens.add("model")
    if any(term in text for term in ["macro", "auc", "confusion", "ablation", "validation", "metric", "pearson", "correlation", "r2"]):
        tokens.add("validation")
    return tokens
