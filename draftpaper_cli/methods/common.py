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
    METHOD_WRITING_BRIEF_JSON,
]


METHOD_OUTPUTS = [
    "methods/method_writing_context.json",
    "methods/method_writing_context.html",
    METHOD_WRITING_BRIEF_JSON,
    METHOD_WRITING_BRIEF_HTML,
    EVIDENCE_REGISTRY_JSON,
    "methods/method_formula_manifest.json",
    "methods/method_formulas.tex",
    "methods/methods.tex",
]


class MethodsGateError(RuntimeError):
    """Raised when Methods writing is attempted before successful code verification."""


SHELL_OPERATOR_TOKENS = {"&&", "||", "|", ";", "&", ">", ">>", "<", "2>", "1>"}


SHELL_EXECUTABLE_NAMES = {"cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh", "pwsh.exe", "bash", "bash.exe", "sh", "sh.exe"}


VERIFY_LOG_LIMIT = 4000


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
    try:
        return resolve_confined_path(project_path, relative, must_exist=False)
    except BoundaryViolation as exc:
        raise MethodsGateError(f"Output path escapes project directory: {relative}") from exc


def _validate_project_paths(project_path: Path, values: list[str], *, role: str) -> list[str]:
    normalized: list[str] = []
    for value in values:
        relative = str(value).strip().replace("\\", "/")
        if not relative:
            continue
        try:
            resolve_confined_path(project_path, relative, must_exist=False)
        except BoundaryViolation as exc:
            raise MethodsGateError(f"{role.capitalize()} path escapes project directory: {relative}") from exc
        normalized.append(relative)
    return list(dict.fromkeys(normalized))


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


def _clean_sentence(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _strip_forbidden_paths(text: str) -> str:
    replacements = [
        (r"\bbkg[_-]?pha(?:[_-]?(?:file|path|filename|pathname))\b", "background spectra (PHA)"),
        (r"\bpha(?:[_-]?(?:file|path|filename|pathname))\b", "source spectra (PHA)"),
        (r"\barf(?:[_-]?(?:file|path|filename|pathname))\b", "effective-area response products (ARF)"),
        (r"\brmf(?:[_-]?(?:file|path|filename|pathname))\b", "redistribution response matrices (RMF)"),
        (r"\b(?:bkg[_-]?)?lc(?:[_-]?(?:file|path|filename|pathname))\b", "source and background light-curve products"),
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


def _drop_internal_method_sentences(text: Any) -> str:
    cleaned = _strip_forbidden_paths(_clean_sentence(text))
    if not cleaned:
        return ""
    pieces = re.split(r"(?<=[.!?])\s+", cleaned)
    kept = []
    forbidden = [
        "method notes are maintained",
        "synchronized by",
        "this section should be regenerated",
        "manuscript should",
        "if later verification changes",
        "documented analysis evidence",
        "manifest",
        "workflow",
        "software operations",
        "documented method component",
        "the method section should",
        "write this section",
        "define the modeled samples",
        "explain how",
        "describe the statistical",
        "describe held-out",
        "define the reported metrics",
        "state the optimization target",
    ]
    for piece in pieces:
        lowered = piece.lower()
        if any(token in lowered for token in forbidden):
            continue
        if piece and piece not in kept:
            kept.append(piece)
    return " ".join(kept).strip()


METHOD_TOKEN_LABELS = {
    "event_level_samples": "event-level sample table",
    "current_observation_tokens": "current-observation tokens",
    "history_lc_tokens": "historical light-curve tokens",
    "history_event_id": "historical event identifier",
    "history_obs_id": "historical observation identifier",
    "history_detnam": "historical detector designation",
    "current_n_tokens": "current-observation token count",
    "history_n_tokens": "historical token count",
    "has_pha": "availability of source spectral products",
    "has_bkg_pha": "availability of background spectral products",
    "has_arf": "availability of effective-area response products",
    "has_rmf": "availability of redistribution response matrices",
    "has_photon_lc": "availability of photon light-curve products",
    "event_spectral_quick_features": "event-level spectral summary features",
    "history_light_curve": "historical light curves",
    "history_lc": "historical light curves",
    "class_label": "class label",
    "label": "class label",
    "source_id": "source identifier",
    "event_id": "event identifier",
    "obs_id": "observation identifier",
    "detnam": "detector metadata",
    "category": "class label",
    "classification": "classification target",
    "version": "processing-version metadata",
    "lv_version": "processing-version metadata",
    "source_in_det": "detector-level source availability",
    "obs_start_mjd": "observation start time",
    "obs_end_mjd": "observation end time",
    "train_validation_test_split": "train-validation-test split",
    "source_holdout_validation": "source-level holdout validation",
    "ablation_study": "ablation study",
    "roc_auc": "ROC-AUC",
    "f1_macro": "macro-F1",
}
