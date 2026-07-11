# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import math
import struct
import zlib
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from draftpaper_cli.figure_semantics import rendered_semantic_metadata
except ModuleNotFoundError:  # Project-local generated runtime.
    from figure_semantics import rendered_semantic_metadata


PLOT_BACKEND = "png_scientific_runtime"
MISSING_VALUE_THRESHOLD = 2
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
DEFAULT_FIGURE_SIZE = (7.1, 4.6)
HEATMAP_FIGURE_SIZE = (7.1, 5.2)
PUBLICATION_COLORS = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#8c564b", "#17becf"]


class ScientificPlotError(RuntimeError):
    """Raised when a planned empirical figure cannot be rendered."""


def _finite_float(value: Any) -> float | None:
    try:
        numeric = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def _column_values(rows: list[dict[str, str]], column: str | None) -> list[float]:
    if not column:
        return []
    values = []
    for row in rows:
        value = _finite_float(row.get(column))
        if value is not None:
            values.append(value)
    return values


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


def _format_number(value: float | None) -> str:
    if value is None:
        return "n/a"
    if abs(value) >= 1000 or (abs(value) < 0.01 and value != 0):
        return f"{value:.2e}"
    return f"{value:.3g}"


def _planned_columns(figure: dict[str, Any], numeric: list[str], label_column: str | None) -> list[str]:
    requested = [str(item) for item in figure.get("required_columns") or [] if isinstance(item, str)]
    requested.extend(str(figure.get(key) or "") for key in ("x", "y", "group") if figure.get(key))
    columns: list[str] = []
    for column in requested + numeric + ([label_column] if label_column else []):
        if column and column not in columns:
            columns.append(column)
    return columns


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


def _scale(value: float, low: float, high: float, start: int, size: int, *, invert: bool = False) -> int:
    span = (high - low) or 1.0
    fraction = (value - low) / span
    if invert:
        fraction = 1 - fraction
    return int(start + fraction * size)


class _Canvas:
    def __init__(self, width: int = 1200, height: int = 760) -> None:
        self.width = width
        self.height = height
        self.pixels = bytearray([255, 255, 255] * width * height)

    def _offset(self, x: int, y: int) -> int:
        return (y * self.width + x) * 3

    def set_pixel(self, x: int, y: int, color: tuple[int, int, int]) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            offset = self._offset(x, y)
            self.pixels[offset:offset + 3] = bytes(color)

    def line(self, x1: int, y1: int, x2: int, y2: int, color: tuple[int, int, int], width: int = 1) -> None:
        dx = abs(x2 - x1)
        dy = -abs(y2 - y1)
        sx = 1 if x1 < x2 else -1
        sy = 1 if y1 < y2 else -1
        err = dx + dy
        while True:
            for ox in range(-width // 2, width // 2 + 1):
                for oy in range(-width // 2, width // 2 + 1):
                    self.set_pixel(x1 + ox, y1 + oy, color)
            if x1 == x2 and y1 == y2:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x1 += sx
            if e2 <= dx:
                err += dx
                y1 += sy

    def rect(self, x: int, y: int, width: int, height: int, color: tuple[int, int, int], *, fill: bool = True) -> None:
        if fill:
            for yy in range(max(0, y), min(self.height, y + height)):
                for xx in range(max(0, x), min(self.width, x + width)):
                    self.set_pixel(xx, yy, color)
            return
        self.line(x, y, x + width, y, color)
        self.line(x, y + height, x + width, y + height, color)
        self.line(x, y, x, y + height, color)
        self.line(x + width, y, x + width, y + height, color)

    def circle(self, cx: int, cy: int, radius: int, color: tuple[int, int, int]) -> None:
        r2 = radius * radius
        for y in range(cy - radius, cy + radius + 1):
            for x in range(cx - radius, cx + radius + 1):
                if (x - cx) ** 2 + (y - cy) ** 2 <= r2:
                    self.set_pixel(x, y, color)

    def write_png(self, path: Path) -> None:
        rows = bytearray()
        stride = self.width * 3
        for y in range(self.height):
            rows.append(0)
            rows.extend(self.pixels[y * stride:(y + 1) * stride])
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as handle:
            handle.write(PNG_SIGNATURE)
            self._chunk(handle, b"IHDR", struct.pack(">IIBBBBB", self.width, self.height, 8, 2, 0, 0, 0))
            self._chunk(handle, b"IDAT", zlib.compress(bytes(rows), level=6))
            self._chunk(handle, b"IEND", b"")

    @staticmethod
    def _chunk(handle: Any, chunk_type: bytes, payload: bytes) -> None:
        handle.write(struct.pack(">I", len(payload)))
        handle.write(chunk_type)
        handle.write(payload)
        checksum = zlib.crc32(chunk_type)
        checksum = zlib.crc32(payload, checksum)
        handle.write(struct.pack(">I", checksum & 0xFFFFFFFF))


def _try_matplotlib() -> tuple[Any, str] | tuple[None, None]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return None, None
    backend = "matplotlib_publication"
    try:
        import scienceplots  # noqa: F401
        plt.style.use(["science", "no-latex"])
        backend = "matplotlib_scienceplots"
    except Exception:
        try:
            plt.style.use("seaborn-v0_8-whitegrid")
        except Exception:
            pass
    plt.rcParams.update({
        "figure.dpi": 180,
        "savefig.dpi": 300,
        "font.size": 9,
        "axes.labelsize": 9,
        "axes.titlesize": 10,
        "legend.fontsize": 8,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "axes.linewidth": 0.8,
        "lines.linewidth": 1.4,
        "lines.markersize": 4,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "savefig.facecolor": "white",
        "savefig.bbox": "tight",
    })
    return plt, backend


def _finish_matplotlib(plt: Any, path: Path, title: str) -> tuple[float, float]:
    figure = plt.gcf()
    figure.suptitle(title, fontsize=12, y=0.99)
    figure.tight_layout(rect=(0, 0, 1, 0.96))
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180, bbox_inches="tight")
    size = tuple(float(value) for value in figure.get_size_inches())
    plt.close(figure)
    return size


def _quality_payload(
    *,
    backend: str,
    axis_labels: dict[str, str],
    text_elements: list[str],
    figure_size_inches: tuple[float, float],
    legend_present: bool = False,
    colorbar_present: bool = False,
) -> dict[str, Any]:
    return {
        "backend": backend,
        "publication_ready": bool(axis_labels and text_elements and backend != "png_stdlib_fallback"),
        "axis_labels": axis_labels,
        "legend_present": legend_present,
        "colorbar_present": colorbar_present,
        "text_elements": [item for item in text_elements if item],
        "figure_size_inches": [round(float(figure_size_inches[0]), 3), round(float(figure_size_inches[1]), 3)],
        "style_profile": {
            "name": "SciencePlots science/no-latex" if backend == "matplotlib_scienceplots" else "DraftPaper publication rcParams",
            "font_size": 9,
            "line_width": 1.4,
            "savefig_dpi": 300,
            "palette": PUBLICATION_COLORS[:4],
        },
    }


def _draw_axes(canvas: _Canvas, left: int, top: int, width: int, height: int) -> None:
    canvas.rect(left, top, width, height, (248, 250, 252), fill=True)
    for index in range(1, 5):
        x = left + index * width // 5
        y = top + index * height // 5
        canvas.line(x, top, x, top + height, (226, 232, 240))
        canvas.line(left, y, left + width, y, (226, 232, 240))
    canvas.rect(left, top, width, height, (17, 24, 39), fill=False)


def _fallback_scatter(path: Path, pairs: list[tuple[float, float]], fit: dict[str, float] | None) -> None:
    canvas = _Canvas()
    left, top, width, height = 130, 90, 930, 540
    _draw_axes(canvas, left, top, width, height)
    xs = [item[0] for item in pairs]
    ys = [item[1] for item in pairs]
    x_low, x_high = _axis_range(xs)
    y_low, y_high = _axis_range(ys)
    for x_value, y_value in pairs[:1600]:
        canvas.circle(_scale(x_value, x_low, x_high, left, width), _scale(y_value, y_low, y_high, top, height, invert=True), 4, (37, 99, 235))
    if fit:
        x1, x2 = min(xs), max(xs)
        y1 = fit["slope"] * x1 + fit["intercept"]
        y2 = fit["slope"] * x2 + fit["intercept"]
        canvas.line(
            _scale(x1, x_low, x_high, left, width),
            _scale(y1, y_low, y_high, top, height, invert=True),
            _scale(x2, x_low, x_high, left, width),
            _scale(y2, y_low, y_high, top, height, invert=True),
            (220, 38, 38),
            3,
        )
    canvas.write_png(path)


def _fallback_bars(path: Path, values: list[float], *, horizontal: bool = False) -> None:
    canvas = _Canvas()
    left, top, width, height = 130, 90, 930, 540
    _draw_axes(canvas, left, top, width, height)
    if not values:
        canvas.write_png(path)
        return
    max_value = max(abs(value) for value in values) or 1.0
    if horizontal:
        bar_h = max(10, height // max(1, len(values)) - 8)
        for index, value in enumerate(values[:20]):
            y = top + index * (bar_h + 8) + 8
            bar_w = int(width * abs(value) / max_value)
            canvas.rect(left, y, bar_w, bar_h, (124, 58, 237), fill=True)
    else:
        bar_w = max(8, width // max(1, len(values)) - 8)
        for index, value in enumerate(values[:30]):
            bar_h = int(height * abs(value) / max_value)
            x = left + index * (bar_w + 8) + 4
            canvas.rect(x, top + height - bar_h, bar_w, bar_h, (5, 150, 105), fill=True)
    canvas.write_png(path)


def _fallback_heatmap(path: Path, matrix: list[list[float | None]]) -> None:
    canvas = _Canvas()
    size = min(92, 650 // max(1, len(matrix)))
    left, top = 220, 80
    for row_index, row in enumerate(matrix):
        for col_index, value in enumerate(row):
            normalized = max(-1.0, min(1.0, float(value or 0.0)))
            if normalized >= 0:
                color = (255, int(235 - 120 * normalized), int(235 - 150 * normalized))
            else:
                color = (int(235 + 20 * normalized), int(238 + 10 * normalized), 255)
            canvas.rect(left + col_index * size, top + row_index * size, size - 2, size - 2, color, fill=True)
    canvas.write_png(path)


def _scatter_regression(path: Path, figure: dict[str, Any], rows: list[dict[str, str]], numeric: list[str], label_column: str | None) -> dict[str, Any]:
    columns = _planned_columns(figure, numeric, label_column)
    numeric_columns = [column for column in columns if column in numeric]
    if len(numeric_columns) < 2:
        numeric_columns = list(numeric)
    requested_x = str(figure.get("x") or "")
    requested_y = str(figure.get("y") or "")
    x_col = requested_x if requested_x in numeric else (numeric_columns[0] if numeric_columns else "")
    y_col = requested_y if requested_y in numeric and requested_y != x_col else ""
    if not y_col:
        y_col = next((column for column in numeric_columns if column != x_col), "")
    pairs = _numeric_pairs(rows, x_col, y_col)
    if len(pairs) < MISSING_VALUE_THRESHOLD:
        raise ScientificPlotError(f"Figure {figure.get('id')} requires at least two paired numeric values for {x_col}/{y_col}.")
    fit = _linear_fit(pairs)
    r_value = _pearson(pairs)
    plt, backend = _try_matplotlib()
    if plt:
        xs = [item[0] for item in pairs]
        ys = [item[1] for item in pairs]
        _, ax = plt.subplots(figsize=DEFAULT_FIGURE_SIZE)
        ax.scatter(xs, ys, s=18, alpha=0.72, color=PUBLICATION_COLORS[0], edgecolors="none", label="Observed samples")
        if fit:
            x1, x2 = min(xs), max(xs)
            ax.plot([x1, x2], [fit["slope"] * x1 + fit["intercept"], fit["slope"] * x2 + fit["intercept"]], color=PUBLICATION_COLORS[1], linewidth=1.8, label="Linear fit")
        ax.set_xlabel(x_col)
        ax.set_ylabel(y_col)
        ax.grid(True, alpha=0.25)
        ax.text(0.02, 0.98, f"n={len(pairs)}, r={_format_number(r_value)}, R2={_format_number((fit or {}).get('r2'))}", transform=ax.transAxes, va="top")
        ax.legend(frameon=False, loc="best")
        figure_size = _finish_matplotlib(plt, path, str(figure.get("title") or "Scientific relationship"))
    else:
        backend = "png_stdlib_fallback"
        _fallback_scatter(path, pairs, fit)
        figure_size = (6.7, 4.2)
    direction = "positive" if (r_value or 0) > 0 else "negative" if (r_value or 0) < 0 else "near-zero"
    return {
        "n": len(pairs),
        "variables": {"x": x_col, "y": y_col},
        "statistics": {"pearson_r": r_value, **(fit or {})},
        "interpretation_summary": f"{x_col} and {y_col} show a {direction} association across {len(pairs)} paired observations (r={_format_number(r_value)}, R2={_format_number((fit or {}).get('r2'))}).",
        "has_axes": True,
        **_quality_payload(
            backend=backend,
            axis_labels={"x": x_col, "y": y_col},
            legend_present=True,
            text_elements=[str(figure.get("title") or "Scientific relationship"), x_col, y_col, "Observed samples", "Linear fit", "n/r/R2 annotation"],
            figure_size_inches=figure_size,
        ),
    }


def _histogram(path: Path, figure: dict[str, Any], rows: list[dict[str, str]], numeric: list[str]) -> dict[str, Any]:
    requested = str(figure.get("x") or "")
    column = requested if requested in numeric else (numeric[0] if numeric else str((figure.get("required_columns") or [""])[0]))
    values = _column_values(rows, column)
    if len(values) < MISSING_VALUE_THRESHOLD:
        raise ScientificPlotError(f"Figure {figure.get('id')} requires numeric values for {column}.")
    bins = min(16, max(6, int(math.sqrt(len(values)))))
    plt, backend = _try_matplotlib()
    if plt:
        _, ax = plt.subplots(figsize=DEFAULT_FIGURE_SIZE)
        ax.hist(values, bins=bins, color=PUBLICATION_COLORS[2], alpha=0.82, edgecolor="white", label=column)
        ax.set_xlabel(column)
        ax.set_ylabel("count")
        ax.grid(True, axis="y", alpha=0.25)
        ax.legend(frameon=False, loc="best")
        figure_size = _finish_matplotlib(plt, path, str(figure.get("title") or "Distribution"))
    else:
        backend = "png_stdlib_fallback"
        low, high = min(values), max(values)
        span = (high - low) or 1.0
        counts = [0] * bins
        for value in values:
            counts[min(bins - 1, int((value - low) / span * bins))] += 1
        _fallback_bars(path, [float(value) for value in counts])
        figure_size = (6.7, 4.2)
    return {
        "n": len(values),
        "variables": {"x": column},
        "statistics": {"mean": _mean(values), "min": min(values), "max": max(values), "bin_count": bins},
        "interpretation_summary": f"{column} has {len(values)} usable observations with mean {_format_number(_mean(values))} and range {_format_number(min(values))} to {_format_number(max(values))}.",
        "has_axes": True,
        **_quality_payload(
            backend=backend,
            axis_labels={"x": column, "y": "count"},
            legend_present=True,
            text_elements=[str(figure.get("title") or "Distribution"), column, "count", "histogram bins"],
            figure_size_inches=figure_size,
        ),
    }


def _class_balance(path: Path, figure: dict[str, Any], rows: list[dict[str, str]], label_column: str | None) -> dict[str, Any]:
    column = str(figure.get("group") or label_column or (figure.get("required_columns") or [""])[0])
    counts = Counter(str(row.get(column, "")).strip() for row in rows if str(row.get(column, "")).strip())
    if not counts:
        raise ScientificPlotError(f"Figure {figure.get('id')} requires a categorical label column.")
    labels, values = zip(*counts.most_common(20))
    plt, backend = _try_matplotlib()
    if plt:
        _, ax = plt.subplots(figsize=DEFAULT_FIGURE_SIZE)
        ax.barh(list(labels)[::-1], list(values)[::-1], color=PUBLICATION_COLORS[3], alpha=0.86, label="Class support")
        ax.set_xlabel("sample count")
        ax.set_ylabel(column)
        ax.grid(True, axis="x", alpha=0.25)
        ax.legend(frameon=False, loc="best")
        figure_size = _finish_matplotlib(plt, path, str(figure.get("title") or "Class support"))
    else:
        backend = "png_stdlib_fallback"
        _fallback_bars(path, [float(value) for value in values], horizontal=True)
        figure_size = (6.7, 4.2)
    imbalance = max(values) / max(1, min(values))
    return {
        "n": sum(values),
        "variables": {"group": column},
        "statistics": {"class_count": len(counts), "max_min_imbalance": imbalance, "counts": dict(counts)},
        "interpretation_summary": f"{column} contains {len(counts)} observed classes across {sum(values)} samples; the largest-to-smallest support ratio is {_format_number(imbalance)}.",
        "has_axes": True,
        **_quality_payload(
            backend=backend,
            axis_labels={"x": "sample count", "y": column},
            legend_present=True,
            text_elements=[str(figure.get("title") or "Class support"), "sample count", column, "Class support"],
            figure_size_inches=figure_size,
        ),
    }


def _correlation_heatmap(path: Path, figure: dict[str, Any], rows: list[dict[str, str]], numeric: list[str]) -> dict[str, Any]:
    columns = [column for column in _planned_columns(figure, numeric, None) if column in numeric][:6]
    if len(columns) < 2:
        raise ScientificPlotError(f"Figure {figure.get('id')} requires at least two numeric columns for a correlation heatmap.")
    matrix: list[list[float | None]] = []
    for y_col in columns:
        matrix.append([_pearson(_numeric_pairs(rows, x_col, y_col)) for x_col in columns])
    plt, backend = _try_matplotlib()
    if plt:
        _, ax = plt.subplots(figsize=HEATMAP_FIGURE_SIZE)
        numeric_matrix = [[float(value or 0.0) for value in row] for row in matrix]
        image = ax.imshow(numeric_matrix, vmin=-1, vmax=1, cmap="coolwarm")
        ax.set_xticks(range(len(columns)), labels=columns, rotation=35, ha="right")
        ax.set_yticks(range(len(columns)), labels=columns)
        ax.set_xlabel("predictor variable")
        ax.set_ylabel("predictor variable")
        plt.colorbar(image, ax=ax, fraction=0.046, pad=0.04, label="Pearson r")
        figure_size = _finish_matplotlib(plt, path, str(figure.get("title") or "Correlation heatmap"))
    else:
        backend = "png_stdlib_fallback"
        _fallback_heatmap(path, matrix)
        figure_size = (6.7, 4.8)
    strongest: tuple[str, str, float] | None = None
    for row_index, y_col in enumerate(columns):
        for col_index, x_col in enumerate(columns):
            if col_index >= row_index:
                continue
            value = matrix[row_index][col_index]
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
        **_quality_payload(
            backend=backend,
            axis_labels={"x": "predictor variable", "y": "predictor variable"},
            colorbar_present=True,
            text_elements=[str(figure.get("title") or "Correlation heatmap"), "Pearson r", *columns[:6]],
            figure_size_inches=figure_size,
        ),
    }


def _metric_summary(path: Path, figure: dict[str, Any], metrics: dict[str, Any]) -> dict[str, Any]:
    numeric_metrics = [(str(key), numeric) for key, value in metrics.items() if (numeric := _finite_float(value)) is not None]
    if not numeric_metrics:
        raise ScientificPlotError(f"Figure {figure.get('id')} requires numeric metrics.")
    labels, values = zip(*numeric_metrics[:12])
    plt, backend = _try_matplotlib()
    if plt:
        _, ax = plt.subplots(figsize=DEFAULT_FIGURE_SIZE)
        ax.barh(list(labels)[::-1], list(values)[::-1], color=PUBLICATION_COLORS[1], alpha=0.86, label="Verified metric")
        ax.set_xlabel("metric value")
        ax.set_ylabel("metric")
        ax.grid(True, axis="x", alpha=0.25)
        ax.legend(frameon=False, loc="best")
        figure_size = _finish_matplotlib(plt, path, str(figure.get("title") or "Metric summary"))
    else:
        backend = "png_stdlib_fallback"
        _fallback_bars(path, [float(value) for value in values], horizontal=True)
        figure_size = (6.7, 4.2)
    primary = numeric_metrics[0]
    return {
        "n": len(numeric_metrics),
        "variables": {"metrics": [key for key, _ in numeric_metrics]},
        "statistics": dict(numeric_metrics),
        "interpretation_summary": f"The metric summary reports {primary[0]}={_format_number(primary[1])} with {len(numeric_metrics)} numeric metrics available.",
        "has_axes": True,
        **_quality_payload(
            backend=backend,
            axis_labels={"x": "metric value", "y": "metric"},
            legend_present=True,
            text_elements=[str(figure.get("title") or "Metric summary"), "metric value", "metric", "Verified metric"],
            figure_size_inches=figure_size,
        ),
    }


def _data_overview(path: Path, figure: dict[str, Any], rows: list[dict[str, str]], numeric: list[str], label_column: str | None) -> dict[str, Any]:
    if numeric:
        return _histogram(path, {**figure, "x": numeric[0], "title": figure.get("title") or "Primary variable distribution"}, rows, numeric)
    if label_column:
        return _class_balance(path, figure, rows, label_column)
    raise ScientificPlotError(f"Figure {figure.get('id')} cannot be rendered because no numeric or categorical variable was detected.")


def _ensure_png_path(root: Path, figure: dict[str, Any]) -> Path:
    relative = str(figure.get("path") or "")
    if not relative:
        raise ScientificPlotError(f"Figure {figure.get('id')} has no output path.")
    path = root / relative
    if path.suffix.lower() != ".png":
        path = path.with_suffix(".png")
        figure["path"] = str(path.relative_to(root)).replace("\\", "/")
    return path


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
    path = _ensure_png_path(root, figure)
    kind = str(figure.get("figure_type") or figure.get("visualization_type") or "").lower()
    if kind in {"class_balance", "confusion_matrix"}:
        payload = _class_balance(path, figure, rows, label_column)
    elif kind in {"histogram", "feature_distribution"}:
        payload = _histogram(path, figure, rows, numeric)
    elif kind in {"correlation_heatmap"}:
        payload = _correlation_heatmap(path, figure, rows, numeric)
    elif kind in {"metric_summary", "performance", "model_performance"}:
        payload = _metric_summary(path, figure, metrics)
    elif kind in {"data_overview", "sample_overview", "coverage_overview"}:
        payload = _data_overview(path, figure, rows, numeric, label_column)
    elif kind in {"scatter_regression", "feature_relationship", "feature_response", "spatial_or_ranked_scatter", "time_series"}:
        payload = _scatter_regression(path, figure, rows, numeric, label_column)
    elif str(figure.get("figure_role") or "main_result").lower() in {"main", "main_result", "primary"}:
        raise ScientificPlotError(
            f"Unsupported main-result figure type '{kind}' for {figure.get('id')}; "
            "a bound plugin method output or project-specific implementation is required instead of a generic data-overview substitution."
        )
    elif figure.get("no_flowchart_fallback", True):
        payload = _data_overview(path, figure, rows, numeric, label_column)
    else:
        raise ScientificPlotError(f"Unsupported empirical figure type: {kind}")
    payload.update({
        "figure_id": figure.get("id") or figure.get("figure_id") or figure.get("storyboard_id"),
        "storyboard_id": figure.get("storyboard_id") or figure.get("id") or figure.get("figure_id"),
        "title": figure.get("title"),
        "path": str(path.relative_to(root)).replace("\\", "/"),
        "figure_type": kind or "data_overview",
        "figure_role": figure.get("figure_role") or "main_result",
        "manuscript_role": figure.get("manuscript_role") or ("appendix" if figure.get("counts_toward_main_figures") is False else "main"),
        "counts_toward_main_figures": figure.get("counts_toward_main_figures") is not False,
        "file_format": "png",
        "backend": payload.get("backend") or PLOT_BACKEND,
        "is_placeholder": False,
        "caption_draft": figure.get("caption_draft") or figure.get("title") or "",
        "result_claim_template": figure.get("result_claim_template") or "",
        **rendered_semantic_metadata(figure, payload),
    })
    return payload


def _is_png(path: Path) -> bool:
    return path.exists() and path.read_bytes()[:8] == PNG_SIGNATURE and path.stat().st_size > 100


def write_figure_metadata_report(root: Path, metadata: list[dict[str, Any]], errors: list[str] | None = None) -> tuple[str, str]:
    metadata_path = root / "results" / "figure_metadata.json"
    quality_path = root / "results" / "figure_quality_report.json"
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps({"figures": metadata}, ensure_ascii=False, indent=2), encoding="utf-8")
    issues = []
    for item in metadata:
        path = root / str(item.get("path") or "")
        if item.get("is_placeholder"):
            issues.append({"severity": "error", "code": "placeholder_figure", "message": f"{item.get('path')} is a placeholder figure."})
        if item.get("file_format") != "png" or not _is_png(path):
            issues.append({"severity": "error", "code": "invalid_png_figure", "message": f"{item.get('path')} is not a valid non-empty PNG figure."})
        if not item.get("has_axes"):
            issues.append({"severity": "error", "code": "missing_axes", "message": f"{item.get('path')} lacks scientific axes or scale metadata."})
        if not item.get("axis_labels"):
            issues.append({"severity": "error", "code": "missing_axis_labels", "message": f"{item.get('path')} lacks axis-label metadata."})
        if not item.get("text_elements"):
            issues.append({"severity": "error", "code": "missing_text_elements", "message": f"{item.get('path')} lacks title, label, legend, or annotation metadata."})
        if not item.get("figure_size_inches"):
            issues.append({"severity": "error", "code": "missing_figure_size", "message": f"{item.get('path')} lacks publication-size metadata."})
        if not item.get("publication_ready"):
            issues.append({"severity": "error", "code": "figure_not_publication_ready", "message": f"{item.get('path')} was not rendered with a publication plotting backend."})
        if not item.get("statistics"):
            issues.append({"severity": "error", "code": "missing_statistics", "message": f"{item.get('path')} has no statistical metadata."})
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
