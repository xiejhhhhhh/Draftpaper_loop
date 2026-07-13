# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

"""Publication-quality figure scoring tied to scientific contracts and runs."""

from __future__ import annotations

import csv
import hashlib
import json
import struct
from pathlib import Path
from typing import Any

from .project_scaffold import utc_now
from .project_state import load_project


REPORT = "results/scientific_figure_quality_report.json"
MINIMUM_SCORE = 0.95


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


def assess_scientific_figure_quality(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    contracts_payload = _read_json(state.path / "results" / "figure_contracts.json")
    contracts = contracts_payload.get("main_contracts") or contracts_payload.get("contracts") or []
    metadata = _read_json(state.path / "results" / "figure_metadata.json").get("figures") or []
    traces = _read_json(state.path / "results" / "figure_plugin_trace_report.json").get("figure_checks") or []
    metadata_by_id = {str(item.get("figure_id") or item.get("storyboard_id") or item.get("id") or ""): item for item in metadata if isinstance(item, dict)}
    metadata_by_path = {str(item.get("path") or "").replace("\\", "/"): item for item in metadata if isinstance(item, dict) and item.get("path")}
    trace_by_id = {str(item.get("figure_id") or ""): item for item in traces if isinstance(item, dict)}
    checks = []
    all_issues = []
    ledger_events = _read_ledger_events(state.path)
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
        sources = _source_artifact_evidence(state.path, item, trace, ledger_events)
        issues = []
        artifact_integrity = 1.0 if width and height and pixels.get("nonblank") else 0.0
        if not artifact_integrity:
            issues.append({"kind": "invalid_missing_or_blank_png", "pixel_evidence": pixels})
        legibility = 1.0 if width >= 1200 and height >= 800 and pixels.get("axis_region_evidence") and pixels.get("text_edge_evidence") else 0.0
        if width < 1200 or height < 800:
            issues.append({"kind": "insufficient_pixel_dimensions", "width": width, "height": height})
        if not pixels.get("axis_region_evidence") or not pixels.get("text_edge_evidence"):
            issues.append({"kind": "rendered_axis_or_text_evidence_missing"})
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
        if not evidence_reporting:
            issues.append({"kind": "missing_statistical_or_interpretive_evidence"})
        plugin_trace = 1.0 if trace.get("data_plugin_ids") and trace.get("method_plugin_ids") and sources.get("event_found") and sources.get("all_hashes_match") else 0.0
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
        check = {"figure_id": figure_id, "score": score, "decision": "pass" if score >= MINIMUM_SCORE else "repair_required", "dimensions": dimensions, "pixel_evidence": pixels, "source_artifact_evidence": sources, "issues": issues}
        checks.append(check)
        all_issues.extend({**issue, "figure_id": figure_id} for issue in issues)
    score = round(sum(item["score"] for item in checks) / max(1, len(checks)), 4)
    report = {
        "status": "written",
        "schema_version": "v0.22.6",
        "generated_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "score": score,
        "minimum_score": MINIMUM_SCORE,
        "decision": "pass" if checks and all(item["decision"] == "pass" for item in checks) else "repair_required",
        "figure_checks": checks,
        "issues": all_issues,
        "policy": "Metadata is never self-proving: publication readiness requires nonblank rendered pixels, visible layout evidence, run-hashed source artifacts, table-bound statistics, semantic contracts, plugin execution, and panel completeness.",
    }
    _write_json(state.path / REPORT, report)
    return report
