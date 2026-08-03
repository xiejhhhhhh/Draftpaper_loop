# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

"""Publication-quality figure scoring tied to scientific contracts and runs."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import struct
from pathlib import Path
from typing import Any

from .project_scaffold import utc_now
from .project_state import load_project


REPORT = "results/scientific_figure_quality_report.json"
MINIMUM_SCORE = 0.95
MIN_OCR_CONFIDENCE = 0.45
MIN_OCR_TEXT_LENGTH = 10
INTERNAL_DISPLAY_LABEL_PATTERN = re.compile(
    r"\b(?:current_only|current_spectrum|full_fusion|naive_history|reliability_aware|quality_weighted_history|"
    r"detection_only_history|history_only|token_transformer_reliability_gated|"
    r"time_encoding_(?:none|fixed_sinusoidal|relative_gap|time2vec))\b",
    re.IGNORECASE,
)
CODE_STYLE_LABEL_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(?:[a-z][a-z0-9]*_)+[a-z0-9]+(?![A-Za-z0-9])"
)
MODEL_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$")
MODEL_COLUMNS = {"model", "model_name", "comparison_model", "baseline_model"}

# Keep the optional OCR backend lazy. Importing onnxruntime at module import
# time can emit platform-specific device warnings into CLI stderr, which must
# remain machine-readable JSON for commands that do not inspect figures.
RapidOCR = None


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _png_dimensions(path: Path) -> tuple[int, int]:
    try:
        header = path.read_bytes()[:24]
    except OSError:
        return 0, 0
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        return 0, 0
    return struct.unpack(">II", header[16:24])


def _pixel_evidence(path: Path) -> dict[str, Any]:
    try:
        from PIL import Image, ImageStat

        with Image.open(path) as image:
            image = image.convert("L")
            image.thumbnail((512, 512))
            width, height = image.size
            pixels = list(image.getdata())
            dark = [value < 235 for value in pixels]
            nonwhite_fraction = sum(dark) / max(len(dark), 1)
            variance = float(ImageStat.Stat(image).var[0])
            edge_count = 0
            for y in range(height):
                row = y * width
                for x in range(1, width):
                    edge_count += abs(pixels[row + x] - pixels[row + x - 1]) > 28
            edge_density = edge_count / max(height * max(width - 1, 1), 1)
            left_width = max(1, width // 5)
            bottom_start = max(0, height * 4 // 5)
            left_density = sum(dark[y * width + x] for y in range(height) for x in range(left_width)) / max(height * left_width, 1)
            bottom_density = sum(dark[y * width + x] for y in range(bottom_start, height) for x in range(width)) / max((height - bottom_start) * width, 1)
            occupancy = []
            for index in range(24):
                start = index * width // 24
                end = max(start + 1, (index + 1) * width // 24)
                density = sum(dark[y * width + x] for y in range(height) for x in range(start, end)) / max(height * (end - start), 1)
                occupancy.append(density > 0.006)
            groups = 0
            active = False
            for occupied in occupancy:
                if occupied and not active:
                    groups += 1
                active = occupied
            # Titles, legends, and long tick labels can bridge otherwise distinct
            # subplots when occupancy is measured over the full canvas.  Measure
            # a second, finer profile through the plotting body so genuine
            # multi-panel figures are not rejected merely because their text
            # spans the inter-panel whitespace.
            body_top = max(0, height * 18 // 100)
            body_bottom = max(body_top + 1, height * 75 // 100)
            body_occupancy = []
            for index in range(64):
                start = index * width // 64
                end = max(start + 1, (index + 1) * width // 64)
                density = sum(
                    dark[y * width + x]
                    for y in range(body_top, body_bottom)
                    for x in range(start, end)
                ) / max((body_bottom - body_top) * (end - start), 1)
                body_occupancy.append(density > 0.04)
            body_groups = 0
            active = False
            for occupied in body_occupancy:
                if occupied and not active:
                    body_groups += 1
                active = occupied
            groups = max(groups, body_groups)
            textured_cells = 0
            grid_cells = 8
            for grid_y in range(2):
                for grid_x in range(4):
                    cell_left = grid_x * width // 4
                    cell_right = (grid_x + 1) * width // 4
                    cell_top = grid_y * height // 2
                    cell_bottom = (grid_y + 1) * height // 2
                    x0 = cell_left + max(1, (cell_right - cell_left) * 12 // 100)
                    x1 = cell_right - max(1, (cell_right - cell_left) * 12 // 100)
                    y0 = cell_top + max(1, (cell_bottom - cell_top) * 22 // 100)
                    y1 = cell_bottom - max(1, (cell_bottom - cell_top) * 10 // 100)
                    values = [pixels[y * width + x] for y in range(y0, y1) for x in range(x0, x1)]
                    if not values:
                        continue
                    mean = sum(values) / len(values)
                    cell_variance = sum((value - mean) ** 2 for value in values) / len(values)
                    edges = 0
                    comparisons = 0
                    for y in range(y0, y1):
                        for x in range(x0 + 1, x1):
                            edges += abs(pixels[y * width + x] - pixels[y * width + x - 1]) > 18
                            comparisons += 1
                    if cell_variance >= 12.0 and edges / max(comparisons, 1) >= 0.003:
                        textured_cells += 1
            return {
                "decoded": True,
                "nonwhite_fraction": round(nonwhite_fraction, 6),
                "luminance_variance": round(variance, 3),
                "edge_density": round(edge_density, 6),
                "axis_region_evidence": left_density > 0.004 and bottom_density > 0.004,
                "text_edge_evidence": edge_density > 0.004,
                "inferred_horizontal_content_groups": groups,
                "inferred_plot_body_content_groups": body_groups,
                "textured_grid_cells": textured_cells,
                "textured_grid_fraction": round(textured_cells / grid_cells, 3),
                "nonblank": nonwhite_fraction >= 0.002 and variance >= 4.0 and edge_density >= 0.001,
            }
    except Exception as exc:
        return {"decoded": False, "nonblank": False, "error": str(exc)}


def _read_ledger_events(project_path: Path) -> list[dict[str, Any]]:
    events = []
    for relative in ("data/plugin_execution_ledger.jsonl", "methods/plugin_execution_ledger.jsonl"):
        path = project_path / relative
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                events.append(item)
    return events


def _source_artifact_evidence(project_path: Path, item: dict[str, Any], trace: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    event_id = str(trace.get("run_output_event_id") or "")
    event = next((candidate for candidate in reversed(events) if str(candidate.get("event_id") or "") == event_id), {})
    output_hashes = event.get("output_hashes") if isinstance(event.get("output_hashes"), dict) else {}
    declared = []
    for key in ("source_tables", "underlying_tables", "source_artifacts", "data_sources"):
        value = item.get(key)
        declared.extend(value if isinstance(value, list) else [value] if value else [])
    if item.get("path"):
        declared.append(item.get("path"))
    declared.extend(path for path in output_hashes if str(path).lower().endswith((".csv", ".tsv", ".json", ".parquet", ".fits", ".tif", ".tiff")))
    paths = list(dict.fromkeys(str(value).replace("\\", "/") for value in declared if str(value).strip()))
    verified = []
    table_values: list[float] = []
    for relative in paths:
        path = project_path / relative
        if not path.is_file():
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        expected = str(output_hashes.get(relative) or "")
        hash_matches = not expected or expected == digest
        verified.append({"path": relative, "sha256": digest, "run_hash_matches": hash_matches})
        if path.suffix.lower() in {".csv", ".tsv"}:
            delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
            try:
                with path.open("r", encoding="utf-8-sig", newline="") as handle:
                    for row in csv.DictReader(handle, delimiter=delimiter):
                        for value in row.values():
                            try:
                                table_values.append(float(value))
                            except (TypeError, ValueError):
                                continue
            except OSError:
                pass
    statistics = item.get("statistics") if isinstance(item.get("statistics"), dict) else {}
    statistic_values = []
    for value in statistics.values():
        try:
            statistic_values.append(float(value))
        except (TypeError, ValueError):
            continue
    table_bound = all(
        any(abs(value - candidate) <= max(1e-8, abs(candidate) * 5e-5) for candidate in table_values)
        for value in statistic_values
    ) if statistic_values else bool(verified)
    verified_by_path = {artifact["path"]: artifact for artifact in verified}
    run_bound_metadata = verified_by_path.get("results/figure_metadata.json", {}).get("run_hash_matches") is True
    figure_relative = str(item.get("path") or "").replace("\\", "/")
    run_bound_figure = verified_by_path.get(figure_relative, {}).get("run_hash_matches") is True
    statistics_bound = table_bound or (bool(statistics) and run_bound_metadata and run_bound_figure)
    return {
        "event_found": bool(event),
        "event_status": event.get("status"),
        "verified_artifacts": verified,
        "all_hashes_match": bool(verified) and all(artifact["run_hash_matches"] for artifact in verified),
        "statistics_bound_to_table": statistics_bound,
    }


def _values(value: object) -> set[str]:
    if isinstance(value, dict):
        raw = value.keys()
    elif isinstance(value, list):
        raw = value
    elif value:
        raw = [value]
    else:
        raw = []
    return {str(item).strip().lower() for item in raw if str(item).strip()}


def _model_identifiers(project_path: Path, metadata: list[dict[str, Any]]) -> set[str]:
    """Collect machine-readable model identifiers that require display labels."""
    identifiers: set[str] = set()
    for item in metadata:
        if not isinstance(item, dict):
            continue
        statistics = item.get("statistics")
        if not isinstance(statistics, dict):
            continue
        for value in statistics.get("models") or []:
            candidate = str(value).strip()
            if MODEL_ID_PATTERN.fullmatch(candidate):
                identifiers.add(candidate)

    table_paths = [
        project_path / "results" / "tables" / "metrics.csv",
        project_path / "results" / "tables" / "factorial_metrics.csv",
    ]
    table_paths.extend(sorted((project_path / "methods" / "results").glob("**/*.csv")))
    for path in table_paths:
        if not path.exists():
            continue
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                field_lookup = {
                    str(field or "").strip().lower(): str(field or "")
                    for field in (reader.fieldnames or [])
                }
                model_fields = [field_lookup[field] for field in MODEL_COLUMNS if field in field_lookup]
                for row in reader:
                    for field in model_fields:
                        candidate = str(row.get(field) or "").strip()
                        if MODEL_ID_PATTERN.fullmatch(candidate):
                            identifiers.add(candidate)
        except (OSError, UnicodeError, csv.Error):
            continue
    return identifiers


def _display_label_issues(
    item: dict[str, Any],
    model_identifiers: set[str] | None = None,
) -> list[dict[str, Any]]:
    visible: list[str] = []
    for key in (
        "axis_labels",
        "legend_labels",
        "display_labels",
        "text_elements",
        "rendered_text",
        "title",
    ):
        value = item.get(key)
        if isinstance(value, str):
            visible.append(value)
        elif isinstance(value, dict):
            visible.extend(str(entry) for entry in value.values())
        elif isinstance(value, list):
            visible.extend(str(entry) for entry in value)

    issues: list[dict[str, Any]] = []
    match = INTERNAL_DISPLAY_LABEL_PATTERN.search(" ".join(visible))
    if match:
        issues.append({
            "kind": "internal_model_identifier_in_display_label",
            "identifier": match.group(0),
        })

    if item.get("display_labels_checked") is not True:
        return issues
    label_map = item.get("display_label_map")
    if not isinstance(label_map, dict) or not label_map:
        issues.append({"kind": "display_label_dictionary_missing"})
        return issues

    raw_keys = sorted(
        str(key) for key in label_map if INTERNAL_DISPLAY_LABEL_PATTERN.search(str(key))
    )
    code_values = sorted(
        str(value) for value in label_map.values() if CODE_STYLE_LABEL_PATTERN.search(str(value))
    )
    if raw_keys:
        issues.append({
            "kind": "internal_identifier_in_display_label_dictionary",
            "identifiers": raw_keys,
        })
    if code_values:
        issues.append({"kind": "code_style_display_label_dictionary", "labels": code_values})

    required = model_identifiers or set()
    missing = sorted(identifier for identifier in required if identifier not in label_map)
    invalid = sorted(
        identifier
        for identifier in required
        if identifier in label_map
        and (
            not str(label_map[identifier]).strip()
            or CODE_STYLE_LABEL_PATTERN.search(str(label_map[identifier])) is not None
        )
    )
    if missing:
        issues.append({"kind": "display_label_dictionary_incomplete", "identifiers": missing})
    if invalid:
        issues.append({"kind": "display_label_dictionary_invalid", "identifiers": invalid})
    return issues


def _ocr_png(path: Path) -> tuple[str, str, float]:
    global RapidOCR

    if RapidOCR is None:
        try:
            from rapidocr_onnxruntime import RapidOCR as rapidocr_class  # type: ignore

            RapidOCR = rapidocr_class
        except ImportError:  # pragma: no cover - optional publication-render dependency
            RapidOCR = None
    if RapidOCR is None or not path.exists():
        return "", "RapidOCR unavailable", 0.0
    try:
        import numpy as np
        from PIL import Image

        result, _ = RapidOCR()(np.asarray(Image.open(path).convert("RGB")))
    except Exception as exc:  # pragma: no cover - defensive render audit
        return "", f"RapidOCR error: {type(exc).__name__}", 0.0
    if not result:
        return "", "rapidocr_onnxruntime", 0.0

    text_parts: list[str] = []
    scores: list[float] = []
    for entry in result:
        if len(entry) < 3:
            continue
        text = str(entry[1]).strip()
        if not text:
            continue
        text_parts.append(text)
        try:
            scores.append(float(entry[2]))
        except (TypeError, ValueError):
            continue
    mean_confidence = sum(scores) / len(scores) if scores else 0.0
    return "\n".join(text_parts), "rapidocr_onnxruntime", float(mean_confidence)


def _figure_code_quality(project_path: Path) -> list[dict[str, Any]]:
    """Detect presentation leaks that pixel occupancy and metadata cannot prove."""
    issues: list[dict[str, Any]] = []
    roots = [project_path / "methods" / "scripts", project_path / "methods" / "src"]
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            try:
                source = path.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeError):
                continue
            relative = str(path.relative_to(project_path)).replace("\\", "/")
            if re.search(
                r"(?:plt|fig|ax|axes?|figure)(?:\s*\[[^\n\]]+\])?\s*\.\s*"
                r"(?:suptitle|set_suptitle|set_title|title)\s*\(",
                source,
                re.IGNORECASE,
            ):
                issues.append({"kind": "figure_level_title_forbidden", "source": relative})
            if (
                re.search(r"MODEL_LABELS\.get\([^\n]*,\s*name\s*\)", source)
                or re.search(r"\.map\(MODEL_LABELS\)\.fillna\(", source)
                or re.search(
                    r"\.fillna\(\s*(?:summary|metrics|token|combined)\s*"
                    r"\[\s*['\"]model_name",
                    source,
                )
            ):
                issues.append({"kind": "unmapped_internal_label_fallback", "source": relative})
    return issues


def assess_scientific_figure_quality(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    contracts_payload = _read_json(state.path / "results" / "figure_contracts.json")
    contracts = contracts_payload.get("main_contracts") or contracts_payload.get("contracts") or []
    metadata = _read_json(state.path / "results" / "figure_metadata.json").get("figures") or []
    trace_payload = _read_json(state.path / "results" / "figure_plugin_trace_report.json")
    traces = trace_payload.get("figure_checks") or []
    metadata_by_id = {str(item.get("figure_id") or item.get("storyboard_id") or item.get("id") or ""): item for item in metadata if isinstance(item, dict)}
    metadata_by_path = {str(item.get("path") or "").replace("\\", "/"): item for item in metadata if isinstance(item, dict) and item.get("path")}
    trace_by_id = {str(item.get("figure_id") or ""): item for item in traces if isinstance(item, dict)}
    checks = []
    all_issues = []
    code_quality_issues = _figure_code_quality(state.path)
    model_identifiers = _model_identifiers(state.path, metadata)
    ledger_events = _read_ledger_events(state.path)
    journal_intent = _read_json(state.path / "journal_profile" / "journal_intent.json")
    target_widths = journal_intent.get("figure_widths") if isinstance(journal_intent.get("figure_widths"), dict) else {}
    for index, contract in enumerate(contracts, start=1):
        if not isinstance(contract, dict) or str(contract.get("manuscript_role") or "main").lower() == "appendix":
            continue
        figure_id = str(contract.get("figure_id") or contract.get("storyboard_id") or contract.get("id") or f"figure_{index:02d}")
        contract_path = str(contract.get("path") or "").replace("\\", "/")
        item = metadata_by_id.get(figure_id) or metadata_by_path.get(contract_path) or {}
        trace = trace_by_id.get(figure_id) or {}
        path = state.path / str(item.get("path") or contract.get("path") or "")
        width, height = _png_dimensions(path)
        pixels = _pixel_evidence(path)
        ocr_text, ocr_backend, ocr_mean_confidence = _ocr_png(path)
        ocr_raw_identifiers = sorted(set(INTERNAL_DISPLAY_LABEL_PATTERN.findall(ocr_text)))
        ocr_code_style_labels = sorted(set(CODE_STYLE_LABEL_PATTERN.findall(ocr_text)))
        sources = _source_artifact_evidence(state.path, item, trace, ledger_events)
        issues = [dict(issue) for issue in code_quality_issues]
        issues.extend(_display_label_issues(item, model_identifiers))
        png_valid = bool(width and height and pixels.get("nonblank"))
        if not png_valid:
            issues.append({"kind": "invalid_missing_or_blank_png", "pixel_evidence": pixels})
        if ocr_backend != "rapidocr_onnxruntime":
            issues.append({"kind": "rendered_ocr_unavailable", "backend": ocr_backend})
        if len(ocr_text.strip()) < MIN_OCR_TEXT_LENGTH:
            issues.append({
                "kind": "rendered_ocr_text_insufficient",
                "text_length": len(ocr_text.strip()),
                "minimum": MIN_OCR_TEXT_LENGTH,
            })
        if ocr_mean_confidence < MIN_OCR_CONFIDENCE:
            issues.append({
                "kind": "rendered_ocr_confidence_low",
                "mean_confidence": ocr_mean_confidence,
                "minimum": MIN_OCR_CONFIDENCE,
            })
        if ocr_raw_identifiers:
            issues.append({
                "kind": "rendered_internal_model_identifier",
                "identifiers": ocr_raw_identifiers,
            })
        if ocr_code_style_labels:
            issues.append({"kind": "rendered_code_style_label", "labels": ocr_code_style_labels})
        rendered_label_contract_ok = bool(
            ocr_backend == "rapidocr_onnxruntime"
            and len(ocr_text.strip()) >= MIN_OCR_TEXT_LENGTH
            and ocr_mean_confidence >= MIN_OCR_CONFIDENCE
            and not ocr_raw_identifiers
            and not ocr_code_style_labels
        )
        artifact_integrity = 1.0 if (
            png_valid and rendered_label_contract_ok and not code_quality_issues
        ) else 0.0
        legibility = 1.0 if width >= 1200 and height >= 800 and pixels.get("axis_region_evidence") and pixels.get("text_edge_evidence") else 0.0
        if width < 1200 or height < 800:
            issues.append({"kind": "insufficient_pixel_dimensions", "width": width, "height": height})
        if not pixels.get("axis_region_evidence") or not pixels.get("text_edge_evidence"):
            issues.append({"kind": "rendered_axis_or_text_evidence_missing"})
        render_qa = {
            "target_width_inches": target_widths.get("double_column_inches") or 6.9,
            "minimum_font_points": item.get("minimum_font_points"),
            "panel_overlap_detected": bool(item.get("panel_overlap_detected")),
            "content_cropped": bool(item.get("content_cropped")),
            "colorblind_safe": item.get("colorblind_safe"),
            "caption_self_contained": item.get("caption_self_contained"),
            "panel_finite_check": item.get("panel_finite_check"),
            "global_title": item.get("global_title"),
            "display_labels_checked": item.get("display_labels_checked"),
        }
        if render_qa["panel_overlap_detected"]:
            legibility = 0.0
            issues.append({"kind": "journal_width_panel_overlap"})
        if render_qa["content_cropped"]:
            legibility = 0.0
            issues.append({"kind": "journal_width_content_cropped"})
        if isinstance(render_qa["minimum_font_points"], (int, float)) and render_qa["minimum_font_points"] < 7:
            legibility = 0.0
            issues.append({"kind": "journal_width_font_below_minimum", "minimum_font_points": render_qa["minimum_font_points"]})
        if not isinstance(render_qa["minimum_font_points"], (int, float)):
            legibility = 0.0
            issues.append({"kind": "missing_render_font_measurement"})
        if render_qa["colorblind_safe"] is not True:
            legibility = 0.0
            issues.append({"kind": "colorblind_safety_not_verified"})
        caption_qa_ok = render_qa["caption_self_contained"] is True
        if not caption_qa_ok:
            issues.append({"kind": "caption_self_containment_not_verified"})
        if render_qa["panel_finite_check"] is not True:
            artifact_integrity = 0.0
            issues.append({"kind": "panel_finite_values_not_verified"})
        finite_count = item.get("panel_finite_value_count")
        nonfinite_count = item.get("panel_nonfinite_value_count")
        if not isinstance(finite_count, (int, float)) or int(finite_count) <= 0:
            artifact_integrity = 0.0
            issues.append({"kind": "panel_finite_value_count_missing_or_zero", "value": finite_count})
        if not isinstance(nonfinite_count, (int, float)) or int(nonfinite_count) != 0:
            artifact_integrity = 0.0
            issues.append({"kind": "panel_nonfinite_value_count_nonzero", "value": nonfinite_count})
        if render_qa["global_title"] is not False:
            artifact_integrity = 0.0
            issues.append({"kind": "global_title_status_not_verified"})
        if render_qa["display_labels_checked"] is not True:
            artifact_integrity = 0.0
            issues.append({"kind": "display_label_mapping_not_verified"})
        if str(contract.get("plot_grammar") or item.get("plot_grammar") or "").lower() == "image_gallery":
            if float(pixels.get("textured_grid_fraction") or 0.0) < 0.5:
                artifact_integrity = 0.0
                issues.append({
                    "kind": "empty_image_gallery_panels",
                    "textured_grid_fraction": pixels.get("textured_grid_fraction"),
                })

        required_roles = _values(contract.get("required_variable_roles"))
        if not required_roles:
            required_roles = _values(contract.get("required_data_roles")) | _values(contract.get("required_data"))
        plugin_data_roles = {
            str(value).split(":", 1)[-1].strip().lower()
            for value in trace.get("data_plugin_ids") or [] if str(value).strip()
        }
        observed_roles = _values(item.get("variable_roles")) | _values(item.get("variables")) | plugin_data_roles
        required_outputs = _values(contract.get("required_method_outputs"))
        observed_outputs = _values(item.get("method_outputs")) | _values(item.get("statistics"))
        semantic_complete = bool(contract.get("scientific_question") or contract.get("research_question")) and required_roles <= observed_roles and required_outputs <= observed_outputs
        semantic_alignment = 1.0 if semantic_complete else 0.0
        if not semantic_complete:
            issues.append({
                "kind": "semantic_contract_incomplete",
                "missing_variable_roles": sorted(required_roles - observed_roles),
                "missing_method_outputs": sorted(required_outputs - observed_outputs),
            })

        evidence_reporting = 1.0 if item.get("statistics") and item.get("interpretation_summary") and sources.get("statistics_bound_to_table") else 0.0
        if not caption_qa_ok:
            evidence_reporting = 0.0
        if not evidence_reporting:
            issues.append({"kind": "missing_statistical_or_interpretive_evidence"})
        trace_decision_passes = trace.get("decision") == "pass" or (
            not trace.get("decision") and trace_payload.get("decision") == "pass"
        )
        plugin_trace = 1.0 if (
            trace_decision_passes
            and trace.get("method_plugin_ids")
            and trace.get("run_output_event_id")
            and sources.get("event_found")
            and sources.get("all_hashes_match")
        ) else 0.0
        if not plugin_trace:
            issues.append({"kind": "missing_plugin_run_trace"})

        required_panels = _values(contract.get("required_panels"))
        observed_panels = _values(item.get("panels"))
        inferred_groups = int(pixels.get("inferred_horizontal_content_groups") or 0)
        panel_completeness = 1.0 if not required_panels or (required_panels <= observed_panels and inferred_groups >= min(len(required_panels), 2)) else 0.0
        if not panel_completeness:
            issues.append({"kind": "missing_required_panels", "panels": sorted(required_panels - observed_panels)})
        dimensions = {
            "artifact_integrity": artifact_integrity,
            "legibility": legibility,
            "semantic_alignment": semantic_alignment,
            "evidence_reporting": evidence_reporting,
            "plugin_run_trace": plugin_trace,
            "panel_completeness": panel_completeness,
        }
        weights = {"artifact_integrity": 0.15, "legibility": 0.15, "semantic_alignment": 0.25, "evidence_reporting": 0.15, "plugin_run_trace": 0.20, "panel_completeness": 0.10}
        score = round(sum(dimensions[key] * weights[key] for key in weights), 4)
        check = {
            "figure_id": figure_id,
            "score": score,
            "decision": "pass" if score >= MINIMUM_SCORE else "repair_required",
            "dimensions": dimensions,
            "pixel_evidence": pixels,
            "rendered_text_audit": {
                "backend": ocr_backend,
                "text_length": len(ocr_text.strip()),
                "mean_confidence": ocr_mean_confidence,
                "raw_internal_identifiers": ocr_raw_identifiers,
                "code_style_labels": ocr_code_style_labels,
            },
            "publication_render_qa": render_qa,
            "source_artifact_evidence": sources,
            "issues": issues,
        }
        checks.append(check)
        all_issues.extend({**issue, "figure_id": figure_id} for issue in issues)
    score = round(sum(item["score"] for item in checks) / max(1, len(checks)), 4)
    report = {
        "status": "written",
        "schema_version": "dpl.scientific_figure_quality.v3",
        "generated_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "score": score,
        "minimum_score": MINIMUM_SCORE,
        "decision": "pass" if checks and all(item["decision"] == "pass" for item in checks) else "repair_required",
        "figure_checks": checks,
        "issues": all_issues,
        "journal_figure_widths": target_widths,
        "policy": "Metadata is never self-proving: publication readiness requires nonblank rendered pixels, journal-width legibility, finite panel values, human-readable display labels, no figure-level title, rendered PNG OCR with a usable backend, no raw internal identifiers or code-style labels in the raster output, explicit render QA, visible layout evidence, run-hashed source artifacts, table-bound statistics, semantic contracts, plugin execution, and panel completeness.",
    }
    _write_json(state.path / REPORT, report)
    return report
