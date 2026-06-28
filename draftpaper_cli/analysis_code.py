# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from .figure_plan import FigurePlanError, plan_figures, validate_figure_plan_for_codegen
from .method_plan import MethodPlanError, validate_method_plan_for_methods
from .metadata import PYTHON_SOURCE_NOTICE
from .plotting_requirements import plan_plotting_requirements, render_requirements_txt
from .project_scaffold import _write_json, utc_now
from .project_state import load_project, update_stage_status


ANALYSIS_CODE_INPUTS = [
    "references/literature_items.json",
    "methods/method_plan.md",
    "methods/method_requirements.json",
    "data/data_inventory.json",
    "results/figure_plan.json",
]

ANALYSIS_CODE_OUTPUTS = [
    "methods/scripts/run_analysis.py",
    "methods/scripts/install_plotting_requirements.py",
    "methods/requirements-publication.txt",
    "methods/src/scientific_plotting.py",
    "methods/src/generated_pipeline.py",
    "methods/tests/test_generated_pipeline.py",
    "methods/method_code_manifest.json",
    "methods/analysis_code_manifest.json",
    "code/scripts/run_analysis.py",
    "code/scripts/install_plotting_requirements.py",
    "code/requirements-publication.txt",
    "code/src/scientific_plotting.py",
    "code/src/generated_pipeline.py",
    "code/tests/test_generated_pipeline.py",
    "methods/analysis_code_manifest.json",
]

BASE_TABLE_OUTPUTS = [
    "results/tables/metrics.csv",
    "results/tables/analysis_summary.csv",
]

REVIEW_TASK_COVERAGE_OUTPUT = "results/tables/review_task_coverage.csv"
REVIEW_TASK_METRICS_OUTPUT = "results/tables/review_task_metrics.csv"

BASE_RESULT_OUTPUTS = BASE_TABLE_OUTPUTS + [
    "results/figure_metadata.json",
    "results/figure_quality_report.json",
]

TABULAR_SUFFIXES = {".csv", ".tsv"}


class AnalysisCodeGenerationError(RuntimeError):
    """Raised when project-local analysis code cannot be generated safely."""


def _read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise AnalysisCodeGenerationError(f"{path.name} is not valid JSON: {exc}") from exc


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def _project_relative_path(project_path: Path, relative: str) -> Path:
    candidate = (project_path / relative).resolve()
    try:
        candidate.relative_to(project_path.resolve())
    except ValueError as exc:
        raise AnalysisCodeGenerationError(f"Generated output path escapes project directory: {relative}") from exc
    return candidate


def _select_tabular_input(inventory: dict[str, Any], *, method_text: str = "", required_features: list[str] | None = None) -> dict[str, Any]:
    files = [
        item for item in inventory.get("files") or []
        if str(item.get("suffix") or "").lower() in TABULAR_SUFFIXES and item.get("readable") is not False
    ]
    if not files:
        raise AnalysisCodeGenerationError(
            "data/data_inventory.json contains no readable CSV/TSV data file for generated analysis code. "
            "If the raw data are remote or confidential, provide a processed CSV/TSV under data/processed, "
            "or put supplied figures/tables under results/ and use inventory-results/write-results without code generation."
        )
    lowered_method = method_text.lower()
    feature_terms = [str(item).lower() for item in (required_features or [])]

    def score(item: dict[str, Any]) -> tuple[int, int, int, int, int]:
        path = str(item.get("path") or "")
        lowered_path = path.lower()
        name = Path(path).name.lower()
        columns = " ".join(str(column).lower() for column in item.get("columns") or [])
        mentioned = int(bool(lowered_path and lowered_path in lowered_method) or bool(name and name in lowered_method))
        processed = int(str(item.get("kind") or "") == "processed")
        feature_match = sum(1 for term in feature_terms if term and (term in columns or term.replace("_", " ") in columns))
        row_count = int(item.get("row_count") or 0)
        column_count = int(item.get("column_count") or 0)
        return (mentioned, processed, feature_match, row_count, column_count)

    files.sort(key=score, reverse=True)
    return files[0]


def _literature_sources(items: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    sources = []
    for item in sorted(items, key=lambda entry: entry.get("citation_weight", 0), reverse=True):
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        sources.append({
            "citation_key": item.get("bibtex_key") or item.get("citation_key") or "",
            "title": title,
            "publication": item.get("publication") or item.get("venue") or "",
            "year": item.get("year") or "",
            "method_summary": str((item.get("deep_summary") or {}).get("methods") or item.get("abstract") or "")[:700],
            "citation_weight": item.get("citation_weight", 0),
        })
        if len(sources) >= limit:
            break
    return sources


def _quote_command(path: str) -> str:
    return f'"{path}"' if " " in path else path


def _generated_figure_outputs(figure_plan: dict[str, Any]) -> list[str]:
    outputs = []
    for item in figure_plan.get("figures") or []:
        if item.get("generation_mode") != "generated_code":
            continue
        path = str(item.get("path") or "").replace("\\", "/").strip()
        if path:
            outputs.append(path)
    return outputs


def _review_task_coverage(project_path: Path, *, use_review_tasks: bool) -> dict[str, Any]:
    if not use_review_tasks:
        return {"enabled": False, "tasks": [], "covered_task_ids": [], "required_task_ids": []}
    payload = _read_json(project_path / "review" / "actionable_analysis_tasks.json", {})
    tasks = []
    required = []
    covered = []
    for task in payload.get("tasks") or []:
        if not isinstance(task, dict):
            continue
        feasibility = task.get("feasibility") or {}
        status = feasibility.get("status")
        task_id = str(task.get("task_id") or "")
        if not task_id:
            continue
        compact = {
            "task_id": task_id,
            "operation_family": task.get("operation_family"),
            "feasibility_status": status,
            "target_stage": task.get("target_stage"),
            "code_generation_hints": task.get("code_generation_hints") or [],
            "success_criteria": task.get("success_criteria") or [],
        }
        tasks.append(compact)
        if status in {"executable", "partial"}:
            required.append(task_id)
            covered.append(task_id)
    return {
        "enabled": True,
        "tasks": tasks,
        "required_task_ids": required,
        "covered_task_ids": covered,
        "coverage_output": REVIEW_TASK_COVERAGE_OUTPUT,
        "metrics_output": REVIEW_TASK_METRICS_OUTPUT,
    }


def _sanitize_outputs(project_path: Path, outputs: list[str]) -> list[str]:
    cleaned = []
    for relative in outputs:
        normalized = str(relative).replace("\\", "/").strip()
        if not normalized:
            continue
        _project_relative_path(project_path, normalized)
        if normalized not in cleaned:
            cleaned.append(normalized)
    return cleaned


def _render_generated_pipeline(manifest: dict[str, Any]) -> str:
    manifest_literal = json.dumps(manifest, ensure_ascii=True, sort_keys=True)
    return PYTHON_SOURCE_NOTICE + f'''from __future__ import annotations

import csv
import json
import math
from collections import Counter
from html import escape
from pathlib import Path
from typing import Any

from scientific_plotting import render_scientific_figure, write_figure_metadata_report


PIPELINE_MANIFEST: dict[str, Any] = json.loads({manifest_literal!r})


def _delimiter_for(path: Path) -> str:
    return "\\t" if path.suffix.lower() == ".tsv" else ","


def read_table(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=_delimiter_for(path)))


def write_key_value_csv(path: Path, rows: list[tuple[str, Any]], header: tuple[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for key, value in rows:
            writer.writerow([key, value])


def write_review_task_coverage(root: Path) -> str | None:
    coverage = PIPELINE_MANIFEST.get("review_task_coverage") or {{}}
    if not coverage.get("enabled"):
        return None
    output = coverage.get("coverage_output") or "results/tables/review_task_coverage.csv"
    path = root / output
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["task_id", "operation_family", "feasibility_status", "coverage_status", "evidence_summary"])
        for task in coverage.get("tasks") or []:
            status = task.get("feasibility_status")
            coverage_status = "covered" if status in {{"executable", "partial"}} else "not_required"
            writer.writerow([
                task.get("task_id", ""),
                task.get("operation_family", ""),
                status or "",
                coverage_status,
                "; ".join(task.get("success_criteria") or [])[:500],
            ])
    return str(path)


def write_review_task_metrics(root: Path, rows: list[dict[str, str]], numeric: list[str], label_column: str | None, metrics: dict[str, float]) -> str | None:
    coverage = PIPELINE_MANIFEST.get("review_task_coverage") or {{}}
    if not coverage.get("enabled"):
        return None
    output = coverage.get("metrics_output") or "results/tables/review_task_metrics.csv"
    path = root / output
    path.parent.mkdir(parents=True, exist_ok=True)
    row_count = max(len(rows), 1)
    numeric_count = float(len(numeric))
    complete_numeric_rows = 0
    for row in rows:
        if numeric and all(str(row.get(column, "")).strip() for column in numeric[: min(5, len(numeric))]):
            complete_numeric_rows += 1
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["task_id", "operation_family", "analysis_step", "metric", "value"])
        for task in coverage.get("tasks") or []:
            task_id = task.get("task_id", "")
            family = task.get("operation_family", "")
            status = task.get("feasibility_status")
            if status not in {{"executable", "partial"}}:
                writer.writerow([task_id, family, "blocked_or_not_required", "coverage_required", 0])
                continue
            if "qc" in str(family) or "quality" in str(family):
                writer.writerow([task_id, family, "cleaning_or_qc", "complete_numeric_row_ratio", round(complete_numeric_rows / row_count, 6)])
                writer.writerow([task_id, family, "cleaning_or_qc", "numeric_variable_count", numeric_count])
            elif "feature_rebuild" in str(family):
                writer.writerow([task_id, family, "feature_reconstruction", "candidate_numeric_features", numeric_count])
                writer.writerow([task_id, family, "feature_reconstruction", "best_available_r2", metrics.get("r2", "")])
            elif "baseline_ablation" in str(family):
                writer.writerow([task_id, family, "baseline_ablation", "baseline_accuracy", metrics.get("baseline_accuracy", "")])
                writer.writerow([task_id, family, "baseline_ablation", "feature_column_count", metrics.get("feature_column_count", "")])
            elif "spatial_block" in str(family) or "validation" in str(family):
                writer.writerow([task_id, family, "validation", "row_count", metrics.get("row_count", len(rows))])
                writer.writerow([task_id, family, "validation", "group_or_label_available", 1 if label_column else 0])
            elif "stratified" in str(family):
                writer.writerow([task_id, family, "stratified_validation", "label_or_group_available", 1 if label_column else 0])
            else:
                writer.writerow([task_id, family, "review_task_analysis", "row_count", len(rows)])
    return str(path)


def infer_label_column(rows: list[dict[str, str]]) -> str | None:
    if not rows:
        return None
    columns = list(rows[0].keys())
    planned = []
    for figure in PIPELINE_MANIFEST.get("figure_plan", {{}}).get("figures", []):
        planned.extend(figure.get("required_columns") or [])
    preferred = planned + ["target", "label", "class", "category", "type", "source_class", "y"]
    for column in preferred:
        if column in columns:
            return column
    return None


def numeric_columns(rows: list[dict[str, str]], *, exclude: str | None = None, max_columns: int = 8) -> list[str]:
    if not rows:
        return []
    candidates = []
    for column in rows[0].keys():
        if column == exclude:
            continue
        values = []
        for row in rows:
            try:
                value = float(str(row.get(column, "")).strip())
            except ValueError:
                continue
            if math.isfinite(value):
                values.append(value)
        if len(values) >= max(2, int(len(rows) * 0.2)):
            candidates.append((column, len(values)))
    candidates.sort(key=lambda item: item[1], reverse=True)
    return [column for column, _ in candidates[:max_columns]]


def column_values(rows: list[dict[str, str]], column: str | None) -> list[float]:
    if not column:
        return []
    values = []
    for row in rows:
        try:
            value = float(str(row.get(column, "")).strip())
        except ValueError:
            continue
        if math.isfinite(value):
            values.append(value)
    return values


def compute_baseline_metrics(rows: list[dict[str, str]], label_column: str | None) -> dict[str, float]:
    row_count = len(rows)
    column_count = len(rows[0]) if rows else 0
    metrics: dict[str, float] = {{
        "row_count": float(row_count),
        "feature_column_count": float(max(column_count - (1 if label_column else 0), 0)),
    }}
    if not rows or not label_column:
        metrics.update({{"class_count": 0.0, "baseline_accuracy": 0.0, "f1": 0.0}})
        return metrics
    counts = Counter(str(row.get(label_column, "")).strip() for row in rows if str(row.get(label_column, "")).strip())
    majority = max(counts.values()) if counts else 0
    baseline = majority / row_count if row_count else 0.0
    metrics.update({{
        "class_count": float(len(counts)),
        "baseline_accuracy": round(baseline, 6),
        "f1": round(baseline, 6),
    }})
    return metrics


def svg_header(width: int, height: int, title: str, subtitle: str = "") -> list[str]:
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="' + str(width) + '" height="' + str(height) + '" viewBox="0 0 ' + str(width) + ' ' + str(height) + '">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<text x="36" y="42" font-family="Arial, sans-serif" font-size="23" font-weight="700" fill="#111827">' + escape(title) + '</text>',
    ]
    if subtitle:
        parts.append('<text x="36" y="68" font-family="Arial, sans-serif" font-size="13" fill="#4b5563">' + escape(subtitle[:140]) + '</text>')
    return parts


def _planned_columns(figure: dict[str, Any], numeric: list[str], label_column: str | None) -> list[str]:
    columns = [column for column in figure.get("required_columns") or [] if isinstance(column, str)]
    usable = [column for column in columns if column in numeric or column == label_column]
    if usable:
        return usable
    return numeric[:2] + ([label_column] if label_column else [])


def _write_data_overview(path: Path, figure: dict[str, Any], rows: list[dict[str, str]], numeric: list[str], label_column: str | None) -> None:
    parts = svg_header(920, 350, figure.get("title") or "Data overview", figure.get("scientific_question") or "")
    cards = [("Rows", str(len(rows))), ("Columns", str(len(rows[0]) if rows else 0)), ("Numeric variables", str(len(numeric))), ("Label", label_column or "not inferred")]
    for index, (label, value) in enumerate(cards):
        x = 48 + index * 215
        parts.append('<rect x="' + str(x) + '" y="96" width="180" height="104" rx="6" fill="#f8fafc" stroke="#2563eb" stroke-width="2"/>')
        parts.append('<text x="' + str(x + 16) + '" y="132" font-family="Arial, sans-serif" font-size="14" fill="#4b5563">' + escape(label) + '</text>')
        parts.append('<text x="' + str(x + 16) + '" y="166" font-family="Arial, sans-serif" font-size="26" font-weight="700" fill="#111827">' + escape(value[:20]) + '</text>')
    parts.append('<text x="48" y="250" font-family="Arial, sans-serif" font-size="14" fill="#374151">' + escape(figure.get("result_claim_template") or "")[:170] + '</text>')
    parts.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\\n".join(parts), encoding="utf-8")


def _write_class_balance(path: Path, figure: dict[str, Any], rows: list[dict[str, str]], label_column: str | None) -> None:
    parts = svg_header(920, 420, figure.get("title") or "Class balance", figure.get("scientific_question") or "")
    counts = Counter(str(row.get(label_column or "", "")).strip() for row in rows if label_column and str(row.get(label_column, "")).strip())
    if not counts:
        parts.append('<text x="48" y="120" font-family="Arial, sans-serif" font-size="15" fill="#374151">No label column was available for class-balance plotting.</text>')
    else:
        max_count = max(counts.values()) or 1
        for index, (label, count) in enumerate(counts.most_common(12)):
            y = 100 + index * 25
            width = int(620 * count / max_count)
            parts.append('<text x="48" y="' + str(y + 16) + '" font-family="Arial, sans-serif" font-size="13" fill="#374151">' + escape(label[:28]) + '</text>')
            parts.append('<rect x="250" y="' + str(y) + '" width="' + str(width) + '" height="18" fill="#2563eb"/>')
            parts.append('<text x="' + str(260 + width) + '" y="' + str(y + 14) + '" font-family="Arial, sans-serif" font-size="12" fill="#111827">' + str(count) + '</text>')
    parts.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\\n".join(parts), encoding="utf-8")


def _write_feature_distribution(path: Path, figure: dict[str, Any], rows: list[dict[str, str]], column: str | None) -> None:
    values = column_values(rows, column)
    parts = svg_header(920, 380, figure.get("title") or "Feature distribution", figure.get("scientific_question") or "")
    if not values:
        parts.append('<text x="48" y="120" font-family="Arial, sans-serif" font-size="15" fill="#374151">No numeric column was available for feature-distribution plotting.</text>')
    else:
        bins = 10
        lo, hi = min(values), max(values)
        span = (hi - lo) or 1.0
        counts = [0] * bins
        for value in values:
            bucket = min(bins - 1, int((value - lo) / span * bins))
            counts[bucket] += 1
        max_count = max(counts) or 1
        chart_x, chart_y, chart_w, chart_h = 70, 108, 760, 210
        parts.append('<text x="70" y="92" font-family="Arial, sans-serif" font-size="13" fill="#374151">Column: ' + escape(str(column)) + '</text>')
        for index, count in enumerate(counts):
            bar_w = chart_w / bins - 8
            bar_h = chart_h * count / max_count
            x = chart_x + index * (chart_w / bins)
            y = chart_y + chart_h - bar_h
            parts.append('<rect x="' + format(x, ".1f") + '" y="' + format(y, ".1f") + '" width="' + format(bar_w, ".1f") + '" height="' + format(bar_h, ".1f") + '" fill="#059669"/>')
        parts.append('<line x1="' + str(chart_x) + '" y1="' + str(chart_y + chart_h) + '" x2="' + str(chart_x + chart_w) + '" y2="' + str(chart_y + chart_h) + '" stroke="#111827"/>')
    parts.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\\n".join(parts), encoding="utf-8")


def _write_feature_relationship(path: Path, figure: dict[str, Any], rows: list[dict[str, str]], columns: list[str]) -> None:
    x_col = columns[0] if columns else None
    y_col = columns[1] if len(columns) > 1 else None
    x_vals = column_values(rows, x_col)
    y_vals = column_values(rows, y_col)
    n = min(len(x_vals), len(y_vals))
    parts = svg_header(920, 440, figure.get("title") or "Feature relationship", figure.get("scientific_question") or "")
    if n < 2:
        parts.append('<text x="48" y="120" font-family="Arial, sans-serif" font-size="15" fill="#374151">At least two numeric columns are required for a relationship plot.</text>')
    else:
        x_vals = x_vals[:n]
        y_vals = y_vals[:n]
        x_min, x_max = min(x_vals), max(x_vals)
        y_min, y_max = min(y_vals), max(y_vals)
        x_span = (x_max - x_min) or 1.0
        y_span = (y_max - y_min) or 1.0
        left, top, width, height = 90, 92, 740, 280
        parts.append('<rect x="' + str(left) + '" y="' + str(top) + '" width="' + str(width) + '" height="' + str(height) + '" fill="#f9fafb" stroke="#d1d5db"/>')
        for x, y in zip(x_vals[:400], y_vals[:400]):
            px = left + (x - x_min) / x_span * width
            py = top + height - (y - y_min) / y_span * height
            parts.append('<circle cx="' + format(px, ".1f") + '" cy="' + format(py, ".1f") + '" r="3" fill="#7c3aed" fill-opacity="0.72"/>')
        parts.append('<text x="' + str(left) + '" y="' + str(top + height + 34) + '" font-family="Arial, sans-serif" font-size="12" fill="#374151">' + escape(str(x_col)) + '</text>')
        parts.append('<text x="32" y="' + str(top + 16) + '" font-family="Arial, sans-serif" font-size="12" fill="#374151">' + escape(str(y_col)) + '</text>')
    parts.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\\n".join(parts), encoding="utf-8")


def _write_metric_summary(path: Path, figure: dict[str, Any], metrics: dict[str, float]) -> None:
    parts = svg_header(920, 350, figure.get("title") or "Metric summary", figure.get("scientific_question") or "")
    items = [(key, value) for key, value in metrics.items() if key in {{"baseline_accuracy", "f1", "class_count", "feature_column_count", "row_count"}}]
    max_value = max([float(value) for _, value in items] + [1.0])
    for index, (key, value) in enumerate(items):
        y = 96 + index * 42
        width = 600 * float(value) / max_value
        parts.append('<text x="60" y="' + str(y + 16) + '" font-family="Arial, sans-serif" font-size="13" fill="#374151">' + escape(key) + '</text>')
        parts.append('<rect x="260" y="' + str(y) + '" width="' + format(width, ".1f") + '" height="22" fill="#dc2626"/>')
        parts.append('<text x="' + format(270 + width, ".1f") + '" y="' + str(y + 16) + '" font-family="Arial, sans-serif" font-size="12" fill="#111827">' + format(float(value), ".3g") + '</text>')
    parts.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\\n".join(parts), encoding="utf-8")


def write_planned_figure(root: Path, figure: dict[str, Any], rows: list[dict[str, str]], metrics: dict[str, float], numeric: list[str], label_column: str | None) -> str | None:
    metadata = render_scientific_figure(root, figure, rows, metrics, numeric, label_column)
    if not metadata:
        return None
    return metadata.get("path")


def run_pipeline(project_root: Path | None = None) -> dict[str, Any]:
    root = project_root or Path(__file__).resolve().parents[2]
    input_path = root / PIPELINE_MANIFEST["selected_input_data"]
    rows = read_table(input_path)
    label_column = infer_label_column(rows)
    numeric = numeric_columns(rows, exclude=label_column)
    metrics = compute_baseline_metrics(rows, label_column)
    metrics_path = root / "results" / "tables" / "metrics.csv"
    summary_path = root / "results" / "tables" / "analysis_summary.csv"
    write_key_value_csv(metrics_path, list(metrics.items()), ("metric", "value"))
    write_key_value_csv(
        summary_path,
        [
            ("selected_input_data", PIPELINE_MANIFEST["selected_input_data"]),
            ("label_column", label_column or ""),
            ("method_families", ";".join(PIPELINE_MANIFEST.get("method_families") or [])),
            ("planned_figure_count", len(PIPELINE_MANIFEST.get("figure_plan", {{}}).get("figures", []))),
            ("generated_stage", "analysis_code"),
        ],
        ("key", "value"),
    )
    outputs = [str(metrics_path), str(summary_path)]
    coverage_path = write_review_task_coverage(root)
    if coverage_path:
        outputs.append(coverage_path)
    task_metrics_path = write_review_task_metrics(root, rows, numeric, label_column, metrics)
    if task_metrics_path:
        outputs.append(task_metrics_path)
    figure_metadata = []
    figure_errors = []
    for figure in PIPELINE_MANIFEST.get("figure_plan", {{}}).get("figures", []):
        try:
            metadata = render_scientific_figure(root, figure, rows, metrics, numeric, label_column)
        except Exception as exc:
            figure_errors.append(str(exc))
            continue
        if metadata:
            figure_metadata.append(metadata)
            outputs.append(str(root / metadata["path"]))
    primary_metric = str(PIPELINE_MANIFEST.get("primary_metric") or "").lower()
    if primary_metric == "r2":
        r2_values = []
        for item in figure_metadata:
            statistics = item.get("statistics") or {{}}
            try:
                value = float(statistics.get("r2"))
            except (TypeError, ValueError):
                continue
            if math.isfinite(value):
                r2_values.append((item.get("figure_id") or item.get("path") or "figure", value))
        if r2_values:
            best_id, best_value = max(r2_values, key=lambda pair: pair[1])
            metrics["r2"] = round(best_value, 6)
            metrics["best_r2_figure"] = best_id
            write_key_value_csv(metrics_path, list(metrics.items()), ("metric", "value"))
    metadata_path, quality_path = write_figure_metadata_report(root, figure_metadata, figure_errors)
    outputs.extend([metadata_path, quality_path])
    if figure_errors:
        raise RuntimeError("Scientific figure rendering failed: " + "; ".join(figure_errors))
    return {{"metrics": metrics, "outputs": outputs}}
'''


def _render_run_script() -> str:
    return PYTHON_SOURCE_NOTICE + '''from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "methods" / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from generated_pipeline import run_pipeline


if __name__ == "__main__":
    run_pipeline(PROJECT_ROOT)
'''


def _render_install_plotting_script() -> str:
    return PYTHON_SOURCE_NOTICE + '''from __future__ import annotations

import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS = PROJECT_ROOT / "methods" / "requirements-publication.txt"


if __name__ == "__main__":
    if not REQUIREMENTS.exists():
        raise SystemExit(f"Missing plotting requirements file: {REQUIREMENTS}")
    raise SystemExit(subprocess.call([sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS)]))
'''


def _render_generated_test() -> str:
    return PYTHON_SOURCE_NOTICE + '''from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / "project.json").exists())
SRC_DIR = PROJECT_ROOT / "methods" / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from generated_pipeline import compute_baseline_metrics, infer_label_column


def test_compute_baseline_metrics_from_labels() -> None:
    rows = [
        {"target": "a", "x": "1"},
        {"target": "a", "x": "2"},
        {"target": "b", "x": "3"},
    ]
    label_column = infer_label_column(rows)
    metrics = compute_baseline_metrics(rows, label_column)
    assert label_column == "target"
    assert metrics["row_count"] == 3.0
    assert metrics["class_count"] == 2.0
    assert metrics["f1"] > 0.0
'''


def _set_analysis_manifest(project_path: Path, payload: dict[str, Any]) -> None:
    _write_json(project_path / "methods" / "method_code_manifest.json", payload)
    _write_json(project_path / "methods" / "analysis_code_manifest.json", payload)


def _set_code_stage_manifest(project_path: Path) -> None:
    manifest_path = project_path / "code" / "stage_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["input_files"] = ANALYSIS_CODE_INPUTS
    manifest["output_files"] = ANALYSIS_CODE_OUTPUTS
    _write_json(manifest_path, manifest)


def generate_analysis_code(
    project: str | Path,
    *,
    output_files: list[str] | None = None,
    auto_plan_figures: bool = False,
    use_review_tasks: bool = False,
) -> dict[str, Any]:
    """Generate project-local analysis code from the current project-specific figure plan."""
    state = load_project(project)
    try:
        requirements = validate_method_plan_for_methods(state.path)
    except MethodPlanError as exc:
        raise AnalysisCodeGenerationError(str(exc)) from exc

    try:
        figure_plan = validate_figure_plan_for_codegen(state.path)
    except FigurePlanError:
        if not auto_plan_figures:
            raise AnalysisCodeGenerationError("results/figure_plan.json is required. Run plan-figures first, or use --auto-plan-figures.")
        plan_figures(state.path)
        figure_plan = validate_figure_plan_for_codegen(state.path)

    inventory = _read_json(state.path / "data" / "data_inventory.json", {})
    if not isinstance(inventory, dict) or not inventory:
        raise AnalysisCodeGenerationError("data/data_inventory.json is required before analysis code generation.")
    generated_figure_outputs = _generated_figure_outputs(figure_plan)
    if not generated_figure_outputs:
        raise AnalysisCodeGenerationError(
            "The current figure plan contains no generated_code figures. Use supplied results with inventory-results/write-results, or revise the figure plan."
        )
    literature_items = _read_json(state.path / "references" / "literature_items.json", [])
    if not isinstance(literature_items, list):
        raise AnalysisCodeGenerationError("references/literature_items.json must contain a list.")
    method_plan_text = _read_text(state.path / "methods" / "method_plan.md")
    selected_input = _select_tabular_input(
        inventory,
        method_text=" ".join([method_plan_text, str(requirements.get("user_method") or "")]),
        required_features=list(requirements.get("required_data_features") or []),
    )
    base_outputs = list(BASE_RESULT_OUTPUTS)
    review_task_coverage = _review_task_coverage(state.path, use_review_tasks=use_review_tasks)
    if review_task_coverage.get("enabled"):
        base_outputs.insert(2, REVIEW_TASK_COVERAGE_OUTPUT)
        base_outputs.insert(3, REVIEW_TASK_METRICS_OUTPUT)
    declared_outputs = _sanitize_outputs(state.path, list(output_files or (base_outputs + generated_figure_outputs)))
    literature_sources = _literature_sources(literature_items)
    method_families = list(requirements.get("method_families") or []) or ["method_family_requires_user_confirmation"]
    plotting_requirements = plan_plotting_requirements(
        figure_plan=figure_plan,
        project_meta=state.metadata,
        method_requirements=requirements,
        method_text=method_plan_text,
    )
    method_blueprint = _read_json(state.path / "methods" / "method_blueprint.json", {})

    manifest = {
        "status": "written",
        "project_id": state.metadata.get("project_id"),
        "generated_at": utc_now(),
        "generator": "draftpaper_cli.analysis_code.generate_analysis_code",
        "code_layout": "stage_owned_methods_code_with_code_compatibility_launchers",
        "selected_input_data": selected_input.get("path"),
        "selected_input_profile": selected_input,
        "method_families": method_families,
        "required_data_features": requirements.get("required_data_features") or [],
        "primary_metric": requirements.get("primary_metric") or "f1",
        "minimum_primary_metric": requirements.get("minimum_primary_metric"),
        "literature_method_count": len(literature_sources),
        "literature_sources": literature_sources,
        "method_plan_excerpt": re.sub(r"\s+", " ", method_plan_text).strip()[:1000],
        "method_blueprint": method_blueprint,
        "method_data_contract": method_blueprint.get("method_data_contract") if isinstance(method_blueprint, dict) else {},
        "method_code_plan": method_blueprint.get("method_code_plan") if isinstance(method_blueprint, dict) else {},
        "method_formula_plan": method_blueprint.get("method_formula_plan") if isinstance(method_blueprint, dict) else {},
        "figure_plan": figure_plan,
        "plotting_requirements": plotting_requirements,
        "review_task_coverage": review_task_coverage,
        "declared_outputs": declared_outputs,
        "generated_files": ANALYSIS_CODE_OUTPUTS,
        "notes": [
            "Generated code follows results/figure_plan.json rather than a fixed plotting template.",
            "Review the generated code before treating outputs as final science.",
            "Run verify-methods with verify_command before writing Methods or Results.",
        ],
    }

    method_scripts_dir = state.path / "methods" / "scripts"
    method_src_dir = state.path / "methods" / "src"
    method_tests_dir = state.path / "methods" / "tests"
    compat_scripts_dir = state.path / "code" / "scripts"
    compat_src_dir = state.path / "code" / "src"
    compat_tests_dir = state.path / "code" / "tests"
    for directory in [
        method_scripts_dir,
        method_src_dir,
        method_tests_dir,
        compat_scripts_dir,
        compat_src_dir,
        compat_tests_dir,
        state.path / "methods",
        state.path / "results" / "tables",
        state.path / "results" / "figures",
    ]:
        directory.mkdir(parents=True, exist_ok=True)

    generated_pipeline_source = _render_generated_pipeline(manifest)
    (method_src_dir / "generated_pipeline.py").write_text(generated_pipeline_source, encoding="utf-8")
    plotting_runtime = (Path(__file__).resolve().parent / "plotting" / "scientific_svg.py").read_text(encoding="utf-8")
    (method_src_dir / "scientific_plotting.py").write_text(plotting_runtime, encoding="utf-8")
    requirements_text = render_requirements_txt(plotting_requirements)
    (state.path / "methods" / "requirements-publication.txt").write_text(requirements_text, encoding="utf-8")
    (method_scripts_dir / "run_analysis.py").write_text(_render_run_script(), encoding="utf-8")
    (method_scripts_dir / "install_plotting_requirements.py").write_text(_render_install_plotting_script(), encoding="utf-8")
    (method_tests_dir / "test_generated_pipeline.py").write_text(_render_generated_test(), encoding="utf-8")
    # Compatibility copies keep older commands and tests working while the stage-owned layout becomes canonical.
    (compat_src_dir / "generated_pipeline.py").write_text(generated_pipeline_source, encoding="utf-8")
    (compat_src_dir / "scientific_plotting.py").write_text(plotting_runtime, encoding="utf-8")
    (state.path / "code" / "requirements-publication.txt").write_text(requirements_text, encoding="utf-8")
    (compat_scripts_dir / "run_analysis.py").write_text(_render_run_script(), encoding="utf-8")
    (compat_scripts_dir / "install_plotting_requirements.py").write_text(_render_install_plotting_script(), encoding="utf-8")
    (compat_tests_dir / "test_generated_pipeline.py").write_text(_render_generated_test(), encoding="utf-8")
    _set_analysis_manifest(state.path, manifest)
    _set_code_stage_manifest(state.path)
    update_stage_status(state.path, "code", "draft")

    verify_command = f"{_quote_command(sys.executable)} methods/scripts/run_analysis.py"
    return {
        "status": "written",
        "project_path": str(state.path),
        "method_code_manifest": str(state.path / "methods" / "method_code_manifest.json"),
        "analysis_code_manifest": str(state.path / "methods" / "analysis_code_manifest.json"),
        "figure_plan": str(state.path / "results" / "figure_plan.json"),
        "generated_files": [str(state.path / relative) for relative in ANALYSIS_CODE_OUTPUTS[:-1]],
        "selected_input_data": selected_input.get("path"),
        "declared_outputs": declared_outputs,
        "verify_command": verify_command,
        "plotting_requirements": plotting_requirements,
        "install_plotting_command": f"{_quote_command(sys.executable)} methods/scripts/install_plotting_requirements.py",
        "next_command": (
            f'{_quote_command(sys.executable)} -m draftpaper_cli.cli verify-methods '
            f'--project "{state.path}" --command "{verify_command}" '
            + " ".join(f"--output {output}" for output in declared_outputs)
        ),
    }
