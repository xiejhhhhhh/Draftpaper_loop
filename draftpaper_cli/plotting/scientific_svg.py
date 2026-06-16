from __future__ import annotations

import json
import math
from collections import Counter
from html import escape
from pathlib import Path
from typing import Any


PLOT_BACKEND = "svg_numpy_stdlib"
MISSING_VALUE_THRESHOLD = 2


class ScientificPlotError(RuntimeError):
    """Raised when a planned empirical figure cannot be rendered."""


def _finite_float(value: Any) -> float | None:
    try:
        numeric = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def _numeric_pairs(rows: list[dict[str, str]], x_col: str | None, y_col: str | None) -> list[tuple[float, float]]:
    if not x_col or not y_col:
        return []
    pairs: list[tuple[float, float]] = []
    for row in rows:
        x_value = _finite_float(row.get(x_col))
        y_value = _finite_float(row.get(y_col))
        if x_value is not None and y_value is not None:
            pairs.append((x_value, y_value))
    return pairs


def _column_values(rows: list[dict[str, str]], column: str | None) -> list[float]:
    if not column:
        return []
    values = []
    for row in rows:
        value = _finite_float(row.get(column))
        if value is not None:
            values.append(value)
    return values


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _pearson(pairs: list[tuple[float, float]]) -> float | None:
    if len(pairs) < 2:
        return None
    xs = [item[0] for item in pairs]
    ys = [item[1] for item in pairs]
    x_mean = _mean(xs)
    y_mean = _mean(ys)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in pairs)
    x_den = math.sqrt(sum((x - x_mean) ** 2 for x in xs))
    y_den = math.sqrt(sum((y - y_mean) ** 2 for y in ys))
    if not x_den or not y_den:
        return None
    return numerator / (x_den * y_den)


def _linear_fit(pairs: list[tuple[float, float]]) -> dict[str, float] | None:
    if len(pairs) < 2:
        return None
    xs = [item[0] for item in pairs]
    ys = [item[1] for item in pairs]
    x_mean = _mean(xs)
    y_mean = _mean(ys)
    denominator = sum((x - x_mean) ** 2 for x in xs)
    if denominator == 0:
        return None
    slope = sum((x - x_mean) * (y - y_mean) for x, y in pairs) / denominator
    intercept = y_mean - slope * x_mean
    ss_tot = sum((y - y_mean) ** 2 for y in ys)
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in pairs)
    r2 = 1 - ss_res / ss_tot if ss_tot else 0.0
    return {"slope": slope, "intercept": intercept, "r2": r2}


def _axis_range(values: list[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 1.0
    low = min(values)
    high = max(values)
    if low == high:
        pad = abs(low) * 0.05 or 1.0
        return low - pad, high + pad
    pad = (high - low) * 0.06
    return low - pad, high + pad


def _scale(value: float, low: float, high: float, start: float, size: float, *, invert: bool = False) -> float:
    span = (high - low) or 1.0
    fraction = (value - low) / span
    if invert:
        fraction = 1 - fraction
    return start + fraction * size


def _format_number(value: float | None) -> str:
    if value is None:
        return "n/a"
    if abs(value) >= 1000 or (abs(value) < 0.01 and value != 0):
        return f"{value:.2e}"
    return f"{value:.3g}"


def _svg_base(width: int, height: int, title: str, subtitle: str = "") -> list[str]:
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="36" y="42" font-family="Arial, sans-serif" font-size="22" font-weight="700" fill="#111827">{escape(title)}</text>',
    ]
    if subtitle:
        parts.append(f'<text x="36" y="68" font-family="Arial, sans-serif" font-size="12" fill="#4b5563">{escape(subtitle[:150])}</text>')
    return parts


def _axis(parts: list[str], *, left: int, top: int, width: int, height: int, x_label: str, y_label: str) -> None:
    parts.append(f'<rect x="{left}" y="{top}" width="{width}" height="{height}" fill="#f8fafc" stroke="#d1d5db"/>')
    parts.append(f'<line x1="{left}" y1="{top + height}" x2="{left + width}" y2="{top + height}" stroke="#111827" stroke-width="1.2"/>')
    parts.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + height}" stroke="#111827" stroke-width="1.2"/>')
    parts.append(f'<text x="{left + width / 2:.1f}" y="{top + height + 48}" text-anchor="middle" font-family="Arial, sans-serif" font-size="13" fill="#374151">{escape(x_label)}</text>')
    parts.append(f'<text x="{left - 52}" y="{top + height / 2:.1f}" transform="rotate(-90 {left - 52} {top + height / 2:.1f})" text-anchor="middle" font-family="Arial, sans-serif" font-size="13" fill="#374151">{escape(y_label)}</text>')


def _planned_columns(figure: dict[str, Any], numeric: list[str], label_column: str | None) -> list[str]:
    requested = [str(item) for item in figure.get("required_columns") or [] if isinstance(item, str)]
    requested.extend(str(figure.get(key) or "") for key in ("x", "y", "group") if figure.get(key))
    columns = []
    for column in requested + numeric + ([label_column] if label_column else []):
        if column and column not in columns:
            columns.append(column)
    return columns


def _scatter_regression(path: Path, figure: dict[str, Any], rows: list[dict[str, str]], numeric: list[str], label_column: str | None) -> dict[str, Any]:
    columns = _planned_columns(figure, numeric, label_column)
    numeric_columns = [column for column in columns if column in numeric]
    x_col = str(figure.get("x") or (numeric_columns[0] if numeric_columns else ""))
    y_col = str(figure.get("y") or (numeric_columns[1] if len(numeric_columns) > 1 else ""))
    pairs = _numeric_pairs(rows, x_col, y_col)
    if len(pairs) < MISSING_VALUE_THRESHOLD:
        raise ScientificPlotError(f"Figure {figure.get('id')} requires at least two paired numeric values for {x_col}/{y_col}.")
    xs = [item[0] for item in pairs]
    ys = [item[1] for item in pairs]
    x_low, x_high = _axis_range(xs)
    y_low, y_high = _axis_range(ys)
    fit = _linear_fit(pairs)
    r_value = _pearson(pairs)

    left, top, width, height = 92, 96, 744, 292
    parts = _svg_base(920, 470, str(figure.get("title") or "Scientific relationship"), str(figure.get("scientific_question") or ""))
    _axis(parts, left=left, top=top, width=width, height=height, x_label=x_col, y_label=y_col)
    for x_value, y_value in pairs[:900]:
        px = _scale(x_value, x_low, x_high, left, width)
        py = _scale(y_value, y_low, y_high, top, height, invert=True)
        parts.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="3.1" fill="#2563eb" fill-opacity="0.68"/>')
    if fit:
        x1, x2 = min(xs), max(xs)
        y1 = fit["slope"] * x1 + fit["intercept"]
        y2 = fit["slope"] * x2 + fit["intercept"]
        parts.append(
            f'<line x1="{_scale(x1, x_low, x_high, left, width):.2f}" y1="{_scale(y1, y_low, y_high, top, height, invert=True):.2f}" '
            f'x2="{_scale(x2, x_low, x_high, left, width):.2f}" y2="{_scale(y2, y_low, y_high, top, height, invert=True):.2f}" stroke="#dc2626" stroke-width="2.4"/>'
        )
    stat_text = f"n={len(pairs)}, r={_format_number(r_value)}, R2={_format_number((fit or {}).get('r2'))}"
    parts.append(f'<text x="{left}" y="{top + height + 24}" font-family="Arial, sans-serif" font-size="12" fill="#111827">{escape(stat_text)}</text>')
    parts.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts), encoding="utf-8")
    direction = "positive" if (r_value or 0) > 0 else "negative" if (r_value or 0) < 0 else "near-zero"
    return {
        "n": len(pairs),
        "variables": {"x": x_col, "y": y_col},
        "statistics": {"pearson_r": r_value, **(fit or {})},
        "interpretation_summary": f"{x_col} and {y_col} show a {direction} association across {len(pairs)} paired observations (r={_format_number(r_value)}, R2={_format_number((fit or {}).get('r2'))}).",
        "has_axes": True,
    }


def _histogram(path: Path, figure: dict[str, Any], rows: list[dict[str, str]], numeric: list[str]) -> dict[str, Any]:
    column = str(figure.get("x") or (figure.get("required_columns") or numeric or [""])[0])
    values = _column_values(rows, column)
    if len(values) < MISSING_VALUE_THRESHOLD:
        raise ScientificPlotError(f"Figure {figure.get('id')} requires numeric values for {column}.")
    bins = min(14, max(6, int(math.sqrt(len(values)))))
    low, high = min(values), max(values)
    span = (high - low) or 1.0
    counts = [0] * bins
    for value in values:
        counts[min(bins - 1, int((value - low) / span * bins))] += 1
    max_count = max(counts) or 1
    left, top, width, height = 92, 96, 744, 260
    parts = _svg_base(920, 430, str(figure.get("title") or "Distribution"), str(figure.get("scientific_question") or ""))
    _axis(parts, left=left, top=top, width=width, height=height, x_label=column, y_label="count")
    for index, count in enumerate(counts):
        bar_width = width / bins - 8
        bar_height = height * count / max_count
        x = left + index * (width / bins) + 4
        y = top + height - bar_height
        parts.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{bar_width:.2f}" height="{bar_height:.2f}" fill="#059669"/>')
    parts.append(f'<text x="{left}" y="{top + height + 24}" font-family="Arial, sans-serif" font-size="12" fill="#111827">n={len(values)}, mean={_format_number(_mean(values))}, range={_format_number(low)} to {_format_number(high)}</text>')
    parts.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts), encoding="utf-8")
    return {
        "n": len(values),
        "variables": {"x": column},
        "statistics": {"mean": _mean(values), "min": low, "max": high, "bin_count": bins},
        "interpretation_summary": f"{column} has {len(values)} usable observations with mean {_format_number(_mean(values))} and range {_format_number(low)} to {_format_number(high)}.",
        "has_axes": True,
    }


def _class_balance(path: Path, figure: dict[str, Any], rows: list[dict[str, str]], label_column: str | None) -> dict[str, Any]:
    column = str(figure.get("group") or label_column or (figure.get("required_columns") or [""])[0])
    counts = Counter(str(row.get(column, "")).strip() for row in rows if str(row.get(column, "")).strip())
    if not counts:
        raise ScientificPlotError(f"Figure {figure.get('id')} requires a categorical label column.")
    max_count = max(counts.values()) or 1
    parts = _svg_base(920, 460, str(figure.get("title") or "Class support"), str(figure.get("scientific_question") or ""))
    left, top = 252, 94
    parts.append(f'<text x="48" y="88" font-family="Arial, sans-serif" font-size="13" fill="#374151">Column: {escape(column)}</text>')
    for index, (label, count) in enumerate(counts.most_common(14)):
        y = top + index * 24
        width = 560 * count / max_count
        parts.append(f'<text x="48" y="{y + 15}" font-family="Arial, sans-serif" font-size="12" fill="#374151">{escape(label[:30])}</text>')
        parts.append(f'<rect x="{left}" y="{y}" width="{width:.2f}" height="17" fill="#7c3aed"/>')
        parts.append(f'<text x="{left + width + 8:.2f}" y="{y + 14}" font-family="Arial, sans-serif" font-size="11" fill="#111827">{count}</text>')
    parts.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts), encoding="utf-8")
    imbalance = max_count / max(1, min(counts.values()))
    return {
        "n": sum(counts.values()),
        "variables": {"group": column},
        "statistics": {"class_count": len(counts), "max_min_imbalance": imbalance, "counts": dict(counts)},
        "interpretation_summary": f"{column} contains {len(counts)} observed classes across {sum(counts.values())} samples; the largest-to-smallest support ratio is {_format_number(imbalance)}.",
        "has_axes": True,
    }


def _correlation_heatmap(path: Path, figure: dict[str, Any], rows: list[dict[str, str]], numeric: list[str]) -> dict[str, Any]:
    columns = [column for column in _planned_columns(figure, numeric, None) if column in numeric][:6]
    if len(columns) < 2:
        raise ScientificPlotError(f"Figure {figure.get('id')} requires at least two numeric columns for a correlation heatmap.")
    matrix: list[list[float | None]] = []
    max_abs = 0.0
    for x_col in columns:
        row_values = []
        for y_col in columns:
            value = _pearson(_numeric_pairs(rows, x_col, y_col))
            row_values.append(value)
            max_abs = max(max_abs, abs(value or 0.0))
        matrix.append(row_values)
    cell = 52
    left, top = 210, 100
    parts = _svg_base(920, 510, str(figure.get("title") or "Correlation heatmap"), str(figure.get("scientific_question") or ""))
    for i, x_col in enumerate(columns):
        parts.append(f'<text x="{left + i * cell + cell / 2:.1f}" y="{top - 14}" transform="rotate(-35 {left + i * cell + cell / 2:.1f} {top - 14})" text-anchor="end" font-family="Arial, sans-serif" font-size="11" fill="#374151">{escape(x_col[:18])}</text>')
    for j, y_col in enumerate(columns):
        parts.append(f'<text x="{left - 12}" y="{top + j * cell + 31}" text-anchor="end" font-family="Arial, sans-serif" font-size="11" fill="#374151">{escape(y_col[:22])}</text>')
    for j, row_values in enumerate(matrix):
        for i, value in enumerate(row_values):
            normalized = (value or 0.0) / (max_abs or 1.0)
            color = "#dc2626" if normalized >= 0 else "#2563eb"
            opacity = 0.18 + abs(normalized) * 0.72
            parts.append(f'<rect x="{left + i * cell}" y="{top + j * cell}" width="{cell}" height="{cell}" fill="{color}" fill-opacity="{opacity:.2f}" stroke="#ffffff"/>')
            parts.append(f'<text x="{left + i * cell + cell / 2:.1f}" y="{top + j * cell + 31}" text-anchor="middle" font-family="Arial, sans-serif" font-size="10" fill="#111827">{escape(_format_number(value))}</text>')
    parts.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts), encoding="utf-8")
    strongest = None
    for j, y_col in enumerate(columns):
        for i, x_col in enumerate(columns):
            if i >= j:
                continue
            value = matrix[j][i]
            if value is not None and (strongest is None or abs(value) > abs(strongest[2])):
                strongest = (x_col, y_col, value)
    summary = "No interpretable pairwise correlation was available."
    if strongest:
        summary = f"The strongest pairwise association is {strongest[0]} versus {strongest[1]} with r={_format_number(strongest[2])}."
    return {
        "n": len(rows),
        "variables": {"columns": columns},
        "statistics": {"correlation_matrix": matrix, "strongest_pair": strongest},
        "interpretation_summary": summary,
        "has_axes": True,
    }


def _metric_summary(path: Path, figure: dict[str, Any], metrics: dict[str, Any]) -> dict[str, Any]:
    numeric_metrics: list[tuple[str, float]] = []
    for key, value in metrics.items():
        numeric = _finite_float(value)
        if numeric is not None:
            numeric_metrics.append((str(key), numeric))
    if not numeric_metrics:
        raise ScientificPlotError(f"Figure {figure.get('id')} requires numeric metrics.")
    max_value = max(abs(value) for _, value in numeric_metrics) or 1.0
    parts = _svg_base(920, 410, str(figure.get("title") or "Metric summary"), str(figure.get("scientific_question") or ""))
    for index, (key, value) in enumerate(numeric_metrics[:10]):
        y = 96 + index * 28
        width = 560 * abs(value) / max_value
        parts.append(f'<text x="58" y="{y + 15}" font-family="Arial, sans-serif" font-size="12" fill="#374151">{escape(key)}</text>')
        parts.append(f'<rect x="260" y="{y}" width="{width:.2f}" height="19" fill="#dc2626"/>')
        parts.append(f'<text x="{270 + width:.2f}" y="{y + 15}" font-family="Arial, sans-serif" font-size="11" fill="#111827">{escape(_format_number(value))}</text>')
    parts.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts), encoding="utf-8")
    primary = numeric_metrics[0]
    return {
        "n": len(numeric_metrics),
        "variables": {"metrics": [key for key, _ in numeric_metrics]},
        "statistics": dict(numeric_metrics),
        "interpretation_summary": f"The metric summary reports {primary[0]}={_format_number(primary[1])} with {len(numeric_metrics)} numeric metrics available.",
        "has_axes": True,
    }


def _data_overview(path: Path, figure: dict[str, Any], rows: list[dict[str, str]], numeric: list[str], label_column: str | None) -> dict[str, Any]:
    if numeric:
        return _histogram(path, {**figure, "x": numeric[0], "title": figure.get("title") or "Primary variable distribution"}, rows, numeric)
    if label_column:
        return _class_balance(path, figure, rows, label_column)
    raise ScientificPlotError(f"Figure {figure.get('id')} cannot be rendered because no numeric or categorical variable was detected.")


def render_scientific_figure(
    root: Path,
    figure: dict[str, Any],
    rows: list[dict[str, str]],
    metrics: dict[str, Any],
    numeric: list[str],
    label_column: str | None,
) -> dict[str, Any] | None:
    if figure.get("generation_mode") != "generated_code":
        return None
    path = root / str(figure.get("path") or "")
    kind = str(figure.get("figure_type") or figure.get("visualization_type") or "").lower()
    if kind in {"class_balance", "confusion_matrix"}:
        payload = _class_balance(path, figure, rows, label_column)
    elif kind in {"histogram", "feature_distribution"}:
        payload = _histogram(path, figure, rows, numeric)
    elif kind in {"correlation_heatmap"}:
        payload = _correlation_heatmap(path, figure, rows, numeric)
    elif kind in {"metric_summary", "performance", "model_performance"}:
        payload = _metric_summary(path, figure, metrics)
    elif kind in {"scatter_regression", "feature_relationship", "feature_response", "spatial_or_ranked_scatter", "time_series"}:
        payload = _scatter_regression(path, figure, rows, numeric, label_column)
    elif figure.get("no_flowchart_fallback", True):
        payload = _data_overview(path, figure, rows, numeric, label_column)
    else:
        raise ScientificPlotError(f"Unsupported empirical figure type: {kind}")
    payload.update({
        "figure_id": figure.get("id"),
        "title": figure.get("title"),
        "path": str(path.relative_to(root)).replace("\\", "/"),
        "figure_type": kind or "data_overview",
        "backend": PLOT_BACKEND,
        "is_placeholder": False,
        "caption_draft": figure.get("caption_draft") or figure.get("title") or "",
        "result_claim_template": figure.get("result_claim_template") or "",
    })
    return payload


def write_figure_metadata_report(root: Path, metadata: list[dict[str, Any]], errors: list[str] | None = None) -> tuple[str, str]:
    metadata_path = root / "results" / "figure_metadata.json"
    quality_path = root / "results" / "figure_quality_report.json"
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps({"figures": metadata}, ensure_ascii=False, indent=2), encoding="utf-8")
    issues = []
    for item in metadata:
        if item.get("is_placeholder"):
            issues.append({"severity": "error", "code": "placeholder_figure", "message": f"{item.get('path')} is a placeholder figure."})
        if not item.get("has_axes"):
            issues.append({"severity": "error", "code": "missing_axes", "message": f"{item.get('path')} lacks scientific axes or scale metadata."})
        if not item.get("interpretation_summary"):
            issues.append({"severity": "error", "code": "missing_interpretation", "message": f"{item.get('path')} has no interpretation metadata."})
    for error in errors or []:
        issues.append({"severity": "error", "code": "figure_render_error", "message": error})
    status = "passed" if not any(issue["severity"] == "error" for issue in issues) else "failed"
    quality_path.write_text(json.dumps({
        "status": status,
        "backend": PLOT_BACKEND,
        "figure_count": len(metadata),
        "issues": issues,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(metadata_path), str(quality_path)
