# Copyright (c) 2026 xiejhhhhhh
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
from .method_plan import MethodPlanError, validate_method_plan_for_methods
from .observations import load_observations
from .project_scaffold import _write_json, utc_now
from .project_state import load_project, update_stage_status


METHOD_INPUTS = [
    "methods/method_plan.md",
    "methods/method_requirements.json",
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
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return fallback


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


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


def verify_methods(
    project: str | Path,
    *,
    command: str,
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

    started_at = utc_now()
    completed = subprocess.run(command, cwd=state.path, shell=True, capture_output=True, text=True)
    finished_at = utc_now()
    declared_outputs = output_files or []
    missing_outputs = _missing_declared_outputs(state.path, {"output_files": declared_outputs})
    figure_quality_issues = _validate_generated_figure_outputs(state.path, declared_outputs)
    review_task_coverage_issues = _review_task_coverage_issues(state.path)
    status = "success" if completed.returncode == 0 and not missing_outputs and not figure_quality_issues and not review_task_coverage_issues else "failed"
    parsed_metrics = _read_metrics_from_outputs(state.path, declared_outputs)
    manifest = {
        "status": status,
        "command": command,
        "returncode": completed.returncode,
        "input_data": input_data or [],
        "output_files": declared_outputs,
        "metrics": parsed_metrics,
        "figures_generated": [item for item in declared_outputs if item.lower().endswith((".png", ".jpg", ".jpeg", ".pdf", ".svg"))],
        "tables_generated": [item for item in declared_outputs if item.lower().endswith((".csv", ".tsv", ".xlsx", ".json"))],
        "started_at": started_at,
        "finished_at": finished_at,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
        "missing_outputs": missing_outputs,
        "figure_quality_issues": figure_quality_issues,
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


def _formula_entries(manifest: dict[str, Any], figure_metadata: dict[str, Any]) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    metrics = {str(key).lower(): value for key, value in (manifest.get("metrics") or {}).items()}
    if "f1" in metrics or "f1_score" in metrics:
        entries.append({
            "id": "f1_score",
            "name": "F1 score",
            "latex": r"\begin{equation}F_1 = 2\cdot \frac{\mathrm{precision}\cdot \mathrm{recall}}{\mathrm{precision}+\mathrm{recall}}.\end{equation}",
            "source": "verified metric output",
        })
    if "baseline_accuracy" in metrics:
        entries.append({
            "id": "majority_baseline",
            "name": "Majority-class baseline",
            "latex": r"\begin{equation}\mathrm{Acc}_{\mathrm{baseline}} = \max_k \frac{n_k}{N}.\end{equation}",
            "source": "verified metric output",
        })
    for item in figure_metadata.get("figures") or []:
        statistics = item.get("statistics") or {}
        figure_id = str(item.get("figure_id") or item.get("path") or "figure")
        if "pearson_r" in statistics:
            entries.append({
                "id": f"{figure_id}_pearson_r",
                "name": "Pearson correlation",
                "latex": r"\begin{equation}r = \frac{\sum_i (x_i-\bar{x})(y_i-\bar{y})}{\sqrt{\sum_i (x_i-\bar{x})^2}\sqrt{\sum_i (y_i-\bar{y})^2}}.\end{equation}",
                "source": figure_id,
            })
        if "r2" in statistics:
            entries.append({
                "id": f"{figure_id}_linear_r2",
                "name": "Linear response and coefficient of determination",
                "latex": r"\begin{equation}y_i = \beta_0+\beta_1x_i+\epsilon_i,\qquad R^2 = 1-\frac{\sum_i (y_i-\hat{y}_i)^2}{\sum_i (y_i-\bar{y})^2}.\end{equation}",
                "source": figure_id,
            })
        if "correlation_matrix" in statistics:
            entries.append({
                "id": f"{figure_id}_correlation_matrix",
                "name": "Pairwise correlation matrix",
                "latex": r"\begin{equation}\mathbf{R}_{jk} = \mathrm{corr}(X_j, X_k).\end{equation}",
                "source": figure_id,
            })
        if "counts" in statistics:
            entries.append({
                "id": f"{figure_id}_class_support",
                "name": "Class-support ratio",
                "latex": r"\begin{equation}\rho_{\mathrm{imbalance}} = \frac{\max_k n_k}{\min_k n_k}.\end{equation}",
                "source": figure_id,
            })
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
    entries = _formula_entries(manifest, figure_metadata)
    payload = {
        "status": "written",
        "generated_at": utc_now(),
        "formula_count": len(entries),
        "formulas": entries,
    }
    _write_json(project_path / "methods" / "method_formula_manifest.json", payload)
    lines = ["% Auto-generated from verified method metrics and figure metadata.", ""]
    for entry in entries:
        lines.extend([f"% {entry['name']} ({entry['source']})", entry["latex"], ""])
    if not entries:
        lines.append("% No explicit mathematical formula was inferred from the verified outputs.")
    (project_path / "methods" / "method_formulas.tex").write_text("\n".join(lines), encoding="utf-8")


def _safe_latex_text(text: Any) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in str(text or ""))


def _clean_sentence(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _strip_forbidden_paths(text: str) -> str:
    text = re.sub(r"[A-Za-z]:\\[^\s,.;)]+", "the verified local workflow", text)
    text = re.sub(r"\b(?:data|results|code)/(?:raw|processed|figures|tables|scripts)/[^\s,.;)]+", "the verified local workflow", text)
    text = re.sub(r"\b[\w.-]+\.(?:csv|tsv|xlsx|xls|json|py|svg|png|jpg|jpeg)\b", "the verified local workflow", text, flags=re.IGNORECASE)
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
    return "The method should be described as a verified local analytical workflow whose steps are constrained by the method plan and available data."


def _data_role_text(manifest: dict[str, Any], analysis_manifest: dict[str, Any]) -> str:
    selected = analysis_manifest.get("selected_input_profile") or {}
    columns = selected.get("columns") or []
    column_text = ", ".join(str(column) for column in columns[:8])
    if column_text:
        return "The verified workflow uses the analysis-ready data variables " + column_text + " to connect the data evidence with the planned analysis."
    inputs = manifest.get("input_data") or []
    if inputs:
        return "The verified workflow uses user-specified analysis-ready input data rather than unverified raw-data access."
    return "The verified workflow uses the data artifacts approved by the data feasibility gate."


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
    analysis_manifest = _read_json(state.path / "methods" / "analysis_code_manifest.json", {})
    family_summary = _method_family_text(requirements)
    analysis_steps = _strip_forbidden_paths(_analysis_steps_text(requirements, observations, analysis_manifest))
    data_role = _strip_forbidden_paths(_data_role_text(manifest, analysis_manifest))
    verification_summary = _strip_forbidden_paths(_metrics_text(manifest, requirements))
    claim_boundary = _clean_sentence(feasibility.get("supported_claim_level"))
    if claim_boundary:
        claim_boundary = "Interpretation is bounded by the data feasibility gate: " + claim_boundary + "."
    else:
        claim_boundary = "Interpretation should remain aligned with the current data and result-validity gates."
    narrative_summary = " ".join([family_summary, data_role, analysis_steps, verification_summary, claim_boundary]).strip()
    context = {
        "project_id": state.metadata.get("project_id"),
        "project_path": str(state.path),
        "method_family_summary": family_summary,
        "data_role": data_role,
        "analysis_steps": analysis_steps,
        "verification_summary": verification_summary,
        "claim_boundary": claim_boundary,
        "observation_count": len(observations),
        "observations": observations,
        "narrative_summary": narrative_summary,
        "forbidden_in_manuscript": ["local filesystem paths", "execution commands", "manifest field dumps", "raw output file lists"],
    }
    context_path = state.path / "methods" / "method_writing_context.json"
    _write_json(context_path, context)
    write_html_report(state.path / "methods" / "method_writing_context.html", _render_method_context_md(context), title="Method Writing Context")
    _set_methods_manifest(state.path)
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
    boundary = _safe_latex_text(_strip_forbidden_paths(context.get("claim_boundary", "")))
    family = _safe_latex_text(_strip_forbidden_paths(context.get("method_family_summary", "")))
    formulas = ""
    project_path = context.get("project_path")
    if project_path:
        formulas = _read_text(Path(str(project_path)) / "methods" / "method_formulas.tex").strip()
    formula_block = f"\n\n{formulas}\n" if formulas else "\n"
    return (
        "\\section{Methods}\n"
        f"{family} {data_role} The methodological description is written from the verified analytical design rather than from local execution details, so the section should explain why the chosen model or statistical route is appropriate for the available variables, expected response, and scientific question. This keeps the method tied to the research plan while avoiding a purely procedural account of software operations.\n\n"
        f"{analysis_steps} In manuscript form, these steps define the transformation from prepared data to interpretable empirical evidence: variables are selected or engineered according to the data gate, the analysis model is fitted or evaluated under the declared validation logic, and the resulting metrics and figures are interpreted only inside the claim boundary established by the project. If later verification changes the input data, validation split, model family, or primary metric, this section should be regenerated before the Results and Discussion are revised.\n\n"
        f"{verification} {boundary} The method description is therefore tied to successful execution and to the scientific structure of the analysis rather than to commands, filenames, or manifest internals. The mathematical expressions below summarize the measurable quantities inferred from the verified outputs and should be expanded when the project uses additional estimators, loss functions, sampling assumptions, or domain-specific indices."
        f"{formula_block}"
    )


def _set_methods_manifest(project_path: Path) -> None:
    manifest_path = project_path / "methods" / "stage_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["input_files"] = METHOD_INPUTS
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
    update_stage_status(state.path, "methods", "draft")
    _set_methods_manifest(state.path)
    return {
        "status": "written",
        "project_path": str(state.path),
        "methods": str(output_path),
        "run_manifest": str(methods_dir / "run_manifest.yaml"),
        "outputs": METHOD_OUTPUTS,
    }
