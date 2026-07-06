# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import csv
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from .data_feasibility import DataGateError, validate_data_feasibility_for_methods
from .html_utils import write_html_report
from .io_utils import read_json, read_text
from .latex_utils import safe_latex_text
from .method_plan import MethodPlanError, validate_method_plan_for_methods
from .observations import load_observations
from .project_scaffold import _write_json, utc_now
from .project_state import load_project, update_stage_status
from .reference_usage import ensure_reference_usage_plan, missing_entries_for_section


METHOD_INPUTS = [
    "methods/method_plan.md",
    "methods/method_requirements.json",
    "methods/method_blueprint.json",
    "methods/method_code_manifest.json",
    "methods/run_manifest.yaml",
]

METHOD_WRITING_INPUTS = [
    "methods/method_plan.md",
    "methods/method_requirements.json",
    "methods/method_blueprint.json",
    "methods/method_code_manifest.json",
    "methods/run_manifest.yaml",
    "methods/method_writing_context.json",
]

METHOD_OUTPUTS = [
    "methods/method_writing_context.json",
    "methods/method_writing_context.html",
    "methods/method_formula_manifest.json",
    "methods/method_formulas.tex",
    "methods/methods.tex",
]


class MethodsGateError(RuntimeError):
    """Raised when Methods writing is attempted before successful code verification."""


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise MethodsGateError(f"methods/run_manifest.yaml is not valid JSON-compatible YAML: {exc}") from exc


def _write_manifest(path: Path, payload: dict[str, Any]) -> None:
    _write_json(path, payload)


def _read_json(path: Path, fallback: Any) -> Any:
    return read_json(path, fallback)


def _read_text(path: Path) -> str:
    return read_text(path)


def _ensure_method_plan(project_path: Path) -> Path:
    path = project_path / "methods" / "method_plan.md"
    if not path.exists():
        state = load_project(project_path)
        content = (
            "# Method Plan\n\n"
            f"Research idea: {state.metadata.get('idea')}\n\n"
            "This file is a planning placeholder. Formal `methods.tex` can only be generated after "
            "`methods/run_manifest.yaml` records a successful method/code run and all declared output files exist.\n"
        )
        path.write_text(content, encoding="utf-8")
    return path


def _project_relative_path(project_path: Path, relative: str) -> Path:
    candidate = (project_path / relative).resolve()
    try:
        candidate.relative_to(project_path.resolve())
    except ValueError as exc:
        raise MethodsGateError(f"Output path escapes project directory: {relative}") from exc
    return candidate


def _missing_declared_outputs(project_path: Path, manifest: dict[str, Any]) -> list[str]:
    missing = []
    for relative in manifest.get("output_files") or []:
        if not _project_relative_path(project_path, str(relative)).exists():
            missing.append(str(relative))
    return missing


def _method_code_manifest(project_path: Path) -> dict[str, Any]:
    payload = _read_json(project_path / "methods" / "method_code_manifest.json", {})
    return payload if isinstance(payload, dict) else {}


def _manifest_list(payload: dict[str, Any], *keys: str) -> list[str]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
    return []


def _resolve_verification_inputs(
    project_path: Path,
    command: str | None,
    output_files: list[str] | None,
    input_data: list[str] | None,
) -> tuple[str, list[str], list[str], dict[str, Any]]:
    manifest = _method_code_manifest(project_path)
    resolved_command = command or str(manifest.get("verify_command") or manifest.get("command") or "").strip()
    if not resolved_command:
        raise MethodsGateError(
            "No method verification command was provided. Pass --command or generate methods/method_code_manifest.json with verify_command."
        )
    resolved_outputs = output_files if output_files is not None else _manifest_list(manifest, "declared_outputs", "output_files")
    resolved_inputs = input_data if input_data is not None else _manifest_list(manifest, "input_data", "input_files")
    selected_input = manifest.get("selected_input_data")
    if selected_input and str(selected_input) not in resolved_inputs:
        resolved_inputs.append(str(selected_input))
    return resolved_command, resolved_outputs, resolved_inputs, manifest


def _figure_contract_issues(project_path: Path) -> tuple[list[str], dict[str, Any]]:
    contracts_payload = _read_json(project_path / "results" / "figure_contracts.json", {})
    contracts = contracts_payload.get("contracts") if isinstance(contracts_payload, dict) else []
    if not isinstance(contracts, list) or not contracts:
        return [], {"status": "not_applicable", "contract_count": 0, "satisfied_count": 0, "issues": []}
    metadata = _read_json(project_path / "results" / "figure_metadata.json", {})
    metadata_items = metadata.get("figures") if isinstance(metadata, dict) else []
    if not isinstance(metadata_items, list):
        metadata_items = []
    metadata_by_path = {
        str(item.get("path") or "").replace("\\", "/"): item
        for item in metadata_items
        if isinstance(item, dict) and item.get("path")
    }
    metadata_by_storyboard = {
        str(item.get("storyboard_id") or item.get("figure_id") or ""): item
        for item in metadata_items
        if isinstance(item, dict) and (item.get("storyboard_id") or item.get("figure_id"))
    }
    issues: list[str] = []
    satisfied = 0
    for contract in contracts:
        if not isinstance(contract, dict):
            continue
        path_text = str(contract.get("path") or "").replace("\\", "/")
        storyboard_id = str(contract.get("storyboard_id") or contract.get("figure_id") or "")
        if not path_text:
            issues.append(f"{storyboard_id or 'main figure contract'} is missing a planned output path.")
            continue
        path = _project_relative_path(project_path, path_text)
        if not _valid_png(path):
            issues.append(f"{path_text} is required by the main figure contract but is missing or is not a valid PNG.")
            continue
        metadata_item = metadata_by_path.get(path_text) or metadata_by_storyboard.get(storyboard_id)
        if not metadata_item:
            issues.append(f"{path_text} is required by the main figure contract but has no matching figure metadata.")
            continue
        if storyboard_id and str(metadata_item.get("storyboard_id") or metadata_item.get("figure_id") or "") not in {storyboard_id, ""}:
            issues.append(f"{path_text} metadata does not match storyboard contract {storyboard_id}.")
            continue
        if metadata_item.get("is_placeholder"):
            issues.append(f"{path_text} is marked as placeholder and cannot satisfy a main figure contract.")
            continue
        satisfied += 1
    checks = {
        "status": "passed" if not issues else "failed",
        "contract_count": len([item for item in contracts if isinstance(item, dict)]),
        "satisfied_count": satisfied,
        "issues": issues,
    }
    return issues, checks


def verify_methods(
    project: str | Path,
    *,
    command: str | None = None,
    output_files: list[str] | None = None,
    input_data: list[str] | None = None,
) -> dict[str, Any]:
    """Run a method verification command and write methods/run_manifest.yaml."""
    state = load_project(project)
    try:
        validate_method_plan_for_methods(state.path)
    except MethodPlanError as exc:
        raise MethodsGateError(str(exc)) from exc
    methods_dir = state.path / "methods"
    methods_dir.mkdir(parents=True, exist_ok=True)
    _ensure_method_plan(state.path)
    command, declared_outputs, resolved_input_data, method_code_manifest = _resolve_verification_inputs(
        state.path,
        command,
        output_files,
        input_data,
    )

    started_at = utc_now()
    completed = subprocess.run(command, cwd=state.path, shell=True, capture_output=True, text=True)
    finished_at = utc_now()
    missing_outputs = _missing_declared_outputs(state.path, {"output_files": declared_outputs})
    figure_quality_issues = _validate_generated_figure_outputs(state.path, declared_outputs)
    figure_contract_issues, figure_contract_checks = _figure_contract_issues(state.path)
    review_task_coverage_issues = _review_task_coverage_issues(state.path)
    status = (
        "success"
        if completed.returncode == 0
        and not missing_outputs
        and not figure_quality_issues
        and not figure_contract_issues
        and not review_task_coverage_issues
        else "failed"
    )
    parsed_metrics = _read_metrics_from_outputs(state.path, declared_outputs)
    manifest = {
        "status": status,
        "command": command,
        "returncode": completed.returncode,
        "input_data": resolved_input_data,
        "output_files": declared_outputs,
        "method_code_manifest": method_code_manifest,
        "metrics": parsed_metrics,
        "figures_generated": [item for item in declared_outputs if item.lower().endswith((".png", ".jpg", ".jpeg", ".pdf", ".svg"))],
        "tables_generated": [item for item in declared_outputs if item.lower().endswith((".csv", ".tsv", ".xlsx", ".json"))],
        "started_at": started_at,
        "finished_at": finished_at,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
        "missing_outputs": missing_outputs,
        "figure_quality_issues": figure_quality_issues,
        "figure_contract_issues": figure_contract_issues,
        "figure_contract_checks": figure_contract_checks,
        "review_task_coverage_issues": review_task_coverage_issues,
    }
    _write_manifest(methods_dir / "run_manifest.yaml", manifest)
    if status == "success":
        _write_method_formulas(state.path, manifest)
    update_stage_status(state.path, "methods", "approved" if status == "success" else "failed")
    return {
        "status": status,
        "project_path": str(state.path),
        "run_manifest": str(methods_dir / "run_manifest.yaml"),
        "returncode": completed.returncode,
        "missing_outputs": missing_outputs,
        "figure_quality_issues": figure_quality_issues,
        "figure_contract_issues": figure_contract_issues,
        "figure_contract_checks": figure_contract_checks,
        "review_task_coverage_issues": review_task_coverage_issues,
    }


def _read_metrics_from_outputs(project_path: Path, output_files: list[str]) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for relative in output_files:
        path = _project_relative_path(project_path, relative)
        if not path.exists() or path.suffix.lower() != ".csv":
            continue
        try:
            lines = path.read_text(encoding="utf-8-sig").splitlines()
        except UnicodeDecodeError:
            continue
        if len(lines) < 2:
            continue
        header = [part.strip().lower() for part in lines[0].split(",")]
        if header[:2] != ["metric", "value"]:
            continue
        for line in lines[1:]:
            parts = [part.strip() for part in line.split(",", 1)]
            if len(parts) == 2 and parts[0]:
                metrics[parts[0]] = parts[1]
    return metrics


def _review_task_coverage_issues(project_path: Path) -> list[str]:
    tasks_path = project_path / "review" / "actionable_analysis_tasks.json"
    if not tasks_path.exists():
        return []
    try:
        tasks_payload = json.loads(tasks_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return ["review/actionable_analysis_tasks.json is not valid JSON."]
    required = []
    for task in tasks_payload.get("tasks") or []:
        if not isinstance(task, dict):
            continue
        status = ((task.get("feasibility") or {}).get("status") or "")
        task_id = str(task.get("task_id") or "")
        if status in {"executable", "partial"} and task_id:
            required.append(task_id)
    if not required:
        return []
    coverage_path = project_path / "results" / "tables" / "review_task_coverage.csv"
    if not coverage_path.exists():
        return ["Missing results/tables/review_task_coverage.csv for executable or partial review tasks."]
    try:
        with coverage_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            covered = {
                str(row.get("task_id") or "")
                for row in reader
                if str(row.get("coverage_status") or "").strip().lower() == "covered"
            }
    except OSError as exc:
        return [f"Could not read review task coverage table: {exc}"]
    missing = [task_id for task_id in required if task_id not in covered]
    if missing:
        return ["Review task coverage is missing required task ids: " + ", ".join(missing)]
    return []


def _valid_png(path: Path) -> bool:
    try:
        return path.exists() and path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n" and path.stat().st_size > 100
    except OSError:
        return False


def _validate_generated_figure_outputs(project_path: Path, output_files: list[str]) -> list[str]:
    figure_plan = _read_json(project_path / "results" / "figure_plan.json", {})
    generated_paths = {
        str(item.get("path") or "").replace("\\", "/")
        for item in figure_plan.get("figures") or []
        if item.get("generation_mode") == "generated_code" and item.get("path")
    }
    if not generated_paths:
        return []
    declared = {str(item).replace("\\", "/") for item in output_files}
    metadata = _read_json(project_path / "results" / "figure_metadata.json", {})
    quality = _read_json(project_path / "results" / "figure_quality_report.json", {})
    metadata_by_path = {
        str(item.get("path") or "").replace("\\", "/"): item
        for item in metadata.get("figures") or []
        if item.get("path")
    }
    issues: list[str] = []
    if quality.get("status") != "passed":
        issues.append("results/figure_quality_report.json must exist with status=passed for generated figures.")
    for relative in sorted(generated_paths & declared):
        path = _project_relative_path(project_path, relative)
        if not _valid_png(path):
            issues.append(f"{relative} is not a valid non-empty PNG.")
        item = metadata_by_path.get(relative)
        if not item:
            issues.append(f"{relative} is missing from results/figure_metadata.json.")
            continue
        if item.get("file_format") != "png":
            issues.append(f"{relative} metadata must declare file_format=png.")
        if item.get("is_placeholder"):
            issues.append(f"{relative} metadata marks the figure as placeholder.")
        if not item.get("has_axes"):
            issues.append(f"{relative} metadata must confirm axes or scale.")
        if not item.get("axis_labels"):
            issues.append(f"{relative} metadata must include axis labels.")
        if not item.get("text_elements"):
            issues.append(f"{relative} metadata must include title, label, legend, or annotation text elements.")
        if not item.get("figure_size_inches"):
            issues.append(f"{relative} metadata must include publication figure size.")
        if not item.get("publication_ready"):
            issues.append(f"{relative} must be rendered with a publication plotting backend.")
        if not item.get("statistics"):
            issues.append(f"{relative} metadata must include statistics.")
        if not item.get("interpretation_summary"):
            issues.append(f"{relative} metadata must include an interpretation summary.")
    return issues


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
    for relative in ["methods/method_code_manifest.json", "methods/analysis_code_manifest.json", "methods/method_blueprint.json", "methods/method_requirements.json", "research_plan/method_plan.json", "research_plan/figure_storyboard.json"]:
        project_path = method_context.get("project_path")
        if not project_path:
            continue
        payload = _read_json(Path(str(project_path)) / relative, {})
        if payload:
            parts.append(json.dumps(payload, ensure_ascii=False, default=str))
    return " ".join(parts).lower()


def _formula_entries(manifest: dict[str, Any], figure_metadata: dict[str, Any], method_context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    method_context = method_context or {}
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
            r"The true-positive rate $\mathrm{TPR}$ and false-positive rate $\mathrm{FPR}$ are evaluated across score thresholds $u$. For multiclass tasks, the manuscript should state whether one-vs-rest or macro-averaged AUC is used.",
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
            f"% {entry['name']} ({entry['source']})",
            entry["latex"],
            _safe_latex_text(entry.get("variable_explanations", "")),
            "",
        ])
    if not entries:
        lines.append("% No explicit mathematical formula was inferred from the verified outputs.")
    (project_path / "methods" / "method_formulas.tex").write_text("\n".join(lines), encoding="utf-8")


def _safe_latex_text(text: Any) -> str:
    return safe_latex_text(text)


def _clean_sentence(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _strip_forbidden_paths(text: str) -> str:
    replacements = [
        (r"\b(?:bkg[_-]?)?pha(?:[_-]?file|[_-]?path)?\b", "source and background spectral products"),
        (r"\barf(?:[_-]?file|[_-]?path)?\b", "effective-area response products"),
        (r"\brmf(?:[_-]?file|[_-]?path)?\b", "energy-redistribution response products"),
        (r"\b(?:bkg[_-]?)?lc(?:[_-]?file|[_-]?path)?\b", "source and background light-curve products"),
        (r"\b(?:training_)?smoke[_-]?test\b", "execution check"),
        (r"\b(?:XRB|TDE|AGN)[_-]?verify\b", "class-specific verification subset"),
        (r"\b(stage-owned|manifest internals|manifest|workflow\.html|formula extraction layer|figure-code trace)\b", "documented analysis evidence"),
    ]
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    text = re.sub(r"[A-Za-z]:\\[^\s,.;)]+", "documented analysis evidence", text)
    text = re.sub(r"\b(?:data|results|code|methods)/(?:raw|processed|figures|tables|scripts|code_templates)/[^\s,.;)]+", "documented analysis evidence", text, flags=re.IGNORECASE)
    text = re.sub(r"\b[\w.-]+\.(?:csv|tsv|xlsx|xls|json|py|svg|png|jpg|jpeg|html|md|tex|fits|zip)\b", "documented analysis evidence", text, flags=re.IGNORECASE)
    text = re.sub(r"\b\w+(?:_file|_path|_filename|_pathname)\b", "data-product descriptor", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _method_family_text(requirements: dict[str, Any]) -> str:
    families = [str(item).replace("_", " ") for item in requirements.get("method_families") or []]
    if not families or families == ["method family requires user confirmation"]:
        return "The method family requires user confirmation and should be described conservatively."
    return "The planned method family is " + ", ".join(families) + "."


def _metrics_text(manifest: dict[str, Any], requirements: dict[str, Any]) -> str:
    metrics = manifest.get("metrics") or {}
    primary = requirements.get("primary_metric") or next(iter(metrics.keys()), "primary metric")
    observed = metrics.get(primary)
    threshold = requirements.get("minimum_primary_metric")
    if observed is not None and threshold is not None:
        return f"The verification run reports {primary}={observed} against a configured minimum value of {threshold}."
    if observed is not None:
        return f"The verification run reports {primary}={observed}; interpretation should remain conditional because no explicit threshold was configured."
    if metrics:
        compact = ", ".join(f"{key}={value}" for key, value in list(metrics.items())[:5])
        return "The verification run reports scalar outputs including " + compact + "."
    return "The verification run completed without parsed scalar metrics, so the method narrative should focus on the validated workflow rather than performance magnitude."


def _analysis_steps_text(requirements: dict[str, Any], observations: list[dict[str, Any]], analysis_manifest: dict[str, Any]) -> str:
    observed = " ".join(_clean_sentence(item.get("text")) for item in observations if item.get("kind") in {"method_rationale", "agent_analysis", "code_design", "method_summary"})
    user_method = _clean_sentence(requirements.get("user_method"))
    if observed and user_method:
        return (user_method + " " + observed)[:1600]
    if observed:
        return observed[:1400]
    if user_method:
        return user_method
    method_excerpt = _clean_sentence(analysis_manifest.get("method_plan_excerpt"))
    if method_excerpt:
        return method_excerpt[:1000]
    code_plan = analysis_manifest.get("method_code_plan") or {}
    method_families = ", ".join(str(item).replace("_", " ") for item in code_plan.get("method_families") or [])
    validation_checks = ", ".join(str(item).replace("_", " ") for item in code_plan.get("validation_checks") or [])
    if method_families or validation_checks:
        return ("The implemented method follows the discipline-aware method blueprint. "
                f"Planned method families include {method_families or 'general analytical modelling'}; "
                f"validation checks include {validation_checks or 'basic execution and output verification'}.")
    return "The method should be described as an implemented analytical design whose steps are constrained by the method plan and available data."


def _data_role_text(manifest: dict[str, Any], analysis_manifest: dict[str, Any]) -> str:
    selected = analysis_manifest.get("selected_input_profile") or {}
    columns = selected.get("columns") or []
    column_text = ", ".join(_strip_forbidden_paths(str(column)) for column in columns[:8])
    if column_text:
        return "The analysis uses the prepared scientific variables " + column_text + " to connect the data evidence with the planned analysis."
    inputs = manifest.get("input_data") or []
    if inputs:
        return "The analysis uses user-specified, analysis-ready inputs rather than making unverified raw-data claims."
    return "The analysis uses the evidence approved by the data feasibility gate."


def _method_code_trace_text(analysis_manifest: dict[str, Any], formula_manifest: dict[str, Any], figure_code_trace: dict[str, Any]) -> str:
    files = analysis_manifest.get("files") if isinstance(analysis_manifest, dict) else []
    formula_count = int(formula_manifest.get("formula_count") or len(formula_manifest.get("formulas") or [])) if isinstance(formula_manifest, dict) else 0
    trace_count = int(figure_code_trace.get("trace_count") or len(figure_code_trace.get("traces") or [])) if isinstance(figure_code_trace, dict) else 0
    pieces = []
    if isinstance(files, list) and files:
        roles = sorted({str(item.get("code_role") or "method_code") for item in files if isinstance(item, dict)})
        pieces.append(
            f"The implemented method is supported by {len(files)} documented method component(s) covering "
            + ", ".join(role.replace("_", " ") for role in roles[:5])
            + "."
        )
    else:
        pieces.append("No dedicated method-code summary was found, so the method narrative must remain conservative.")
    if formula_count:
        pieces.append(f"The mathematical description is organized around {formula_count} expression(s) derived from the implemented analysis.")
    else:
        pieces.append("No method formula has been extracted yet; formula-bearing methods should regenerate the method context before final Methods writing.")
    if trace_count:
        pieces.append(f"The result figures are linked to {trace_count} documented analysis component(s), which constrains how the method can be described.")
    return " ".join(pieces)


def _render_method_context_md(context: dict[str, Any]) -> str:
    lines = [
        "# Method Writing Context",
        "",
        "## Narrative Summary",
        "",
        context.get("narrative_summary", ""),
        "",
        "## Analysis Steps",
        "",
        context.get("analysis_steps", ""),
        "",
        "## Data Role",
        "",
        context.get("data_role", ""),
        "",
        "## Method Code and Formula Trace",
        "",
        context.get("code_trace_summary", ""),
        "",
        "## Verification",
        "",
        context.get("verification_summary", ""),
        "",
        "## Claim Boundary",
        "",
        context.get("claim_boundary", ""),
        "",
    ]
    return "\n".join(lines)


def build_method_writing_context(project: str | Path) -> dict[str, Any]:
    """Build a manuscript-facing Methods context from method plan, code manifests, and observations."""
    state = load_project(project)
    manifest = _validate_successful_manifest(state.path)
    requirements = validate_method_plan_for_methods(state.path)
    feasibility = validate_data_feasibility_for_methods(state.path)
    observations = load_observations(state.path, stage="methods")
    analysis_manifest = _read_json(state.path / "methods" / "method_code_manifest.json", {})
    if not analysis_manifest:
        analysis_manifest = _read_json(state.path / "methods" / "analysis_code_manifest.json", {})
    formula_manifest = _read_json(state.path / "methods" / "method_formula_manifest.json", {})
    figure_code_trace = _read_json(state.path / "results" / "figure_code_trace.json", {})
    method_blueprint = _read_json(state.path / "methods" / "method_blueprint.json", {})
    if method_blueprint and "method_code_plan" not in analysis_manifest:
        analysis_manifest["method_code_plan"] = method_blueprint.get("method_code_plan") or {}
    family_summary = _method_family_text(requirements)
    analysis_steps = _strip_forbidden_paths(_analysis_steps_text(requirements, observations, analysis_manifest))
    data_role = _strip_forbidden_paths(_data_role_text(manifest, analysis_manifest))
    code_trace_summary = _strip_forbidden_paths(_method_code_trace_text(analysis_manifest, formula_manifest, figure_code_trace))
    verification_summary = _strip_forbidden_paths(_metrics_text(manifest, requirements))
    claim_boundary = _clean_sentence(feasibility.get("supported_claim_level"))
    if claim_boundary:
        claim_boundary = "Interpretation is bounded by the data feasibility gate: " + claim_boundary + "."
    else:
        claim_boundary = "Interpretation should remain aligned with the current data and result-validity gates."
    narrative_summary = " ".join([family_summary, data_role, analysis_steps, code_trace_summary, verification_summary, claim_boundary]).strip()
    context = {
        "project_id": state.metadata.get("project_id"),
        "project_path": str(state.path),
        "method_family_summary": family_summary,
        "data_role": data_role,
        "analysis_steps": analysis_steps,
        "code_trace_summary": code_trace_summary,
        "verification_summary": verification_summary,
        "claim_boundary": claim_boundary,
        "observation_count": len(observations),
        "observations": observations,
        "method_blueprint": method_blueprint,
        "method_code_manifest": analysis_manifest,
        "formula_manifest": formula_manifest if isinstance(formula_manifest, dict) else {},
        "figure_code_trace": figure_code_trace if isinstance(figure_code_trace, dict) else {},
        "narrative_summary": narrative_summary,
        "forbidden_in_manuscript": ["local filesystem paths", "execution commands", "manifest field dumps", "raw output file lists"],
    }
    context_path = state.path / "methods" / "method_writing_context.json"
    _write_json(context_path, context)
    write_html_report(state.path / "methods" / "method_writing_context.html", _render_method_context_md(context), title="Method Writing Context")
    _set_methods_writing_manifest(state.path)
    return context


def _validate_successful_manifest(project_path: Path) -> dict[str, Any]:
    _ensure_method_plan(project_path)
    try:
        validate_method_plan_for_methods(project_path)
    except MethodPlanError as exc:
        raise MethodsGateError(str(exc)) from exc
    try:
        validate_data_feasibility_for_methods(project_path)
    except DataGateError as exc:
        raise MethodsGateError(str(exc)) from exc
    manifest_path = project_path / "methods" / "run_manifest.yaml"
    if not manifest_path.exists():
        raise MethodsGateError("methods/run_manifest.yaml is required before writing methods.tex.")
    manifest = _read_manifest(manifest_path)
    if manifest.get("status") != "success":
        raise MethodsGateError("methods/run_manifest.yaml must have status=success before writing methods.tex.")
    missing = _missing_declared_outputs(project_path, manifest)
    if missing:
        raise MethodsGateError("Declared method output files are missing: " + ", ".join(missing))
    return manifest


def _render_methods_tex(project_meta: dict[str, Any], manifest: dict[str, Any], context: dict[str, Any]) -> str:
    data_role = _safe_latex_text(_strip_forbidden_paths(context.get("data_role", "")))
    analysis_steps = _safe_latex_text(_strip_forbidden_paths(context.get("analysis_steps", "")))
    verification = _safe_latex_text(_strip_forbidden_paths(context.get("verification_summary", "")))
    code_trace = _safe_latex_text(_strip_forbidden_paths(context.get("code_trace_summary", "")))
    boundary = _safe_latex_text(_strip_forbidden_paths(context.get("claim_boundary", "")))
    family = _safe_latex_text(_strip_forbidden_paths(context.get("method_family_summary", "")))
    formulas = ""
    project_path = context.get("project_path")
    if project_path:
        formulas = _read_text(Path(str(project_path)) / "methods" / "method_formulas.tex").strip()
    citation_paragraphs: list[str] = []
    if project_path:
        project_dir = Path(str(project_path))
        ensure_reference_usage_plan(project_dir)
        existing = "\n\n".join([family, data_role, analysis_steps, verification, boundary])
        entries = missing_entries_for_section(project_dir, "methods", existing)
        if entries:
            sentences = []
            for entry in entries:
                key = str(entry.get("citation_key") or "")
                evidence = _strip_forbidden_paths(_clean_sentence(entry.get("evidence_summary") or entry.get("title")))
                if key and evidence:
                    sentences.append(f"{_safe_latex_text(evidence)} \\citep{{{key}}}.")
            for index in range(0, len(sentences), 4):
                citation_paragraphs.append(
                    "The retained method-oriented references define the methodological context for the verified analysis route. "
                    + " ".join(sentences[index:index + 4])
                )
    formula_block = f"\n\n{formulas}\n" if formulas else "\n"
    citation_block = ("\n\n" + "\n\n".join(citation_paragraphs)) if citation_paragraphs else ""
    return (
        "\\section{Methods}\n"
        f"{family} {data_role} The methodological description follows the implemented analytical design and explains why the chosen model or statistical route is appropriate for the available variables, expected response, and scientific question. This keeps the method tied to the research plan while avoiding a procedural account of software operations.\n\n"
        f"{analysis_steps} In manuscript form, these steps define the transformation from prepared data to interpretable empirical evidence: variables are selected or engineered according to the data gate, the analysis model is fitted or evaluated under the declared validation logic, and the resulting metrics and figures are interpreted only inside the claim boundary established by the project. {code_trace} If later verification changes the input data, validation split, model family, primary metric, or figure-generation code, this section should be regenerated before the Results and Discussion are revised.\n\n"
        f"{verification} {boundary} The method description is therefore tied to successful execution and to the scientific structure of the analysis rather than to commands or storage details. The mathematical expressions below organize the Methods section: each expression is a compact description of the model objective, statistical relationship, validation metric, or diagnostic quantity implemented by the analysis code, with the variables explained in the surrounding prose."
        f"{citation_block}"
        f"{formula_block}"
    )


def _set_methods_manifest(project_path: Path) -> None:
    manifest_path = project_path / "methods" / "stage_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["input_files"] = METHOD_INPUTS
    manifest["output_files"] = ["methods/run_manifest.yaml", "methods/method_formula_manifest.json", "methods/method_formulas.tex"]
    _write_json(manifest_path, manifest)


def _set_methods_writing_manifest(project_path: Path) -> None:
    manifest_path = project_path / "methods_writing" / "stage_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["input_files"] = METHOD_WRITING_INPUTS + ["results/results.tex", "core_evidence/core_evidence_report.json"]
    manifest["output_files"] = METHOD_OUTPUTS
    _write_json(manifest_path, manifest)


def write_methods(project: str | Path) -> dict[str, Any]:
    """Write methods.tex only if methods/run_manifest.yaml proves a successful run."""
    state = load_project(project)
    manifest = _validate_successful_manifest(state.path)
    context = build_method_writing_context(state.path)
    methods_dir = state.path / "methods"
    output_path = methods_dir / "methods.tex"
    output_path.write_text(_render_methods_tex(state.metadata, manifest, context), encoding="utf-8")
    update_stage_status(state.path, "methods_writing", "draft")
    _set_methods_writing_manifest(state.path)
    return {
        "status": "written",
        "project_path": str(state.path),
        "methods": str(output_path),
        "run_manifest": str(methods_dir / "run_manifest.yaml"),
        "outputs": METHOD_OUTPUTS,
    }
