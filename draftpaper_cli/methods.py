# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import ast
import csv
import hashlib
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

from .data_feasibility import DataGateError, validate_data_feasibility_for_methods
from .html_utils import write_html_report
from .io_utils import read_json, read_text
from .latex_utils import safe_latex_text
from .method_plan import MethodPlanError, validate_method_plan_for_methods
from .manuscript_composer import SectionCompositionError, select_validated_section_draft
from .observations import load_observations
from .project_scaffold import _write_json, utc_now
from .project_state import load_project, mark_stage_stale, update_stage_status
from .reference_usage import ensure_reference_usage_plan, missing_entries_for_section
from .evidence_registry import EVIDENCE_REGISTRY_JSON, build_scientific_evidence_registry, ensure_registry_consistent
from .result_evidence import ResultEvidenceError, resolve_result_evidence
from .writing_brief import METHOD_WRITING_BRIEF_HTML, METHOD_WRITING_BRIEF_JSON, build_method_writing_brief


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


def _strip_outer_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _split_legacy_command(command: str) -> list[str]:
    try:
        argv = shlex.split(command, posix=False)
    except ValueError as exc:
        raise MethodsGateError(f"Method verification command is not parseable as argv: {exc}") from exc
    normalized = []
    for token in argv:
        text = _strip_outer_quotes(token.strip())
        if not text:
            continue
        normalized.append(sys.executable if text in {"{python}", "${PYTHON}", "$PYTHON"} else text)
    if not normalized:
        raise MethodsGateError("Method verification command is empty after parsing.")
    shell_tokens = [token for token in normalized if token in SHELL_OPERATOR_TOKENS]
    if shell_tokens:
        raise MethodsGateError(
            "Method verification command contains shell operators that are not allowed under v0.16.2 safe execution: "
            + ", ".join(shell_tokens)
            + ". Use methods/method_code_manifest.json verify_command_argv or a single Python runner script instead."
        )
    _reject_shell_runner(normalized)
    return normalized


def _normalize_verify_argv(argv: list[Any]) -> list[str]:
    normalized = []
    for token in argv:
        text = _strip_outer_quotes(str(token).strip())
        if not text:
            continue
        if text in {"{python}", "${PYTHON}", "$PYTHON"}:
            normalized.append(sys.executable)
        else:
            normalized.append(text)
    if not normalized:
        raise MethodsGateError("verify_command_argv is empty.")
    shell_tokens = [token for token in normalized if token in SHELL_OPERATOR_TOKENS]
    if shell_tokens:
        raise MethodsGateError(
            "verify_command_argv contains shell operators that are not allowed: " + ", ".join(shell_tokens)
        )
    _reject_shell_runner(normalized)
    return normalized


def _reject_shell_runner(argv: list[str]) -> None:
    first = Path(argv[0]).name.lower() if argv else ""
    if first in SHELL_EXECUTABLE_NAMES:
        raise MethodsGateError(
            "Method verification cannot invoke an interactive shell runner. "
            "Use verify_command_argv with a direct Python runner such as ['{python}', 'methods/scripts/run_analysis.py']."
        )


def _command_display(argv: list[str]) -> str:
    return subprocess.list2cmdline(argv)


def _existing_output_check_argv(project_path: Path, outputs: list[str]) -> list[str]:
    payload = json.dumps({"project": str(project_path), "outputs": outputs})
    code = (
        "import json, sys; from pathlib import Path; "
        f"payload=json.loads({payload!r}); root=Path(payload['project']); "
        "missing=[p for p in payload['outputs'] if not (root / p).exists()]; "
        "sys.exit(1 if missing else 0)"
    )
    return [sys.executable, "-c", code]


def _infer_verify_command_argv(project_path: Path, manifest: dict[str, Any]) -> tuple[list[str], str, dict[str, Any]] | None:
    """Infer a safe verification route for old projects that predate verify_command_argv."""
    candidates = [
        project_path / "methods" / "scripts" / "run_analysis.py",
        project_path / "code" / "scripts" / "run_analysis.py",
    ]
    plotting_dir = project_path / "methods" / "plotting"
    if plotting_dir.exists():
        candidates.extend(sorted(plotting_dir.glob("run_*pipeline.py")))
    for candidate in candidates:
        if candidate.exists():
            relative = candidate.relative_to(project_path).as_posix()
            return [sys.executable, relative], "inferred_project_runner", {"inferred_runner": relative}

    run_manifest_path = project_path / "methods" / "run_manifest.yaml"
    if run_manifest_path.exists():
        run_manifest = _read_manifest(run_manifest_path)
        legacy = str(run_manifest.get("command") or "").strip()
        if legacy:
            try:
                return _split_legacy_command(legacy), "inferred_from_previous_run_manifest", {"source": "methods/run_manifest.yaml"}
            except MethodsGateError:
                pass
        outputs = _manifest_list(run_manifest, "output_files", "declared_outputs")
        result_validity = _read_json(project_path / "results" / "result_validity_report.json", {})
        if run_manifest.get("status") == "success" and outputs and str((result_validity or {}).get("decision") or "").lower() in {"pass", "passed", "conditional"}:
            return _existing_output_check_argv(project_path, outputs), "inferred_existing_output_check", {"source": "methods/run_manifest.yaml + results/result_validity_report.json", "outputs": outputs}

    outputs = _manifest_list(manifest, "declared_outputs", "output_files")
    if outputs:
        return _existing_output_check_argv(project_path, outputs), "inferred_manifest_output_check", {"source": "methods/method_code_manifest.json", "outputs": outputs}
    return None


def _resolve_verification_inputs(
    project_path: Path,
    command: str | None,
    output_files: list[str] | None,
    input_data: list[str] | None,
) -> tuple[list[str], str, str, list[str], list[str], dict[str, Any]]:
    manifest = _method_code_manifest(project_path)
    command_source = "cli_override" if command else "method_code_manifest"
    if command:
        resolved_argv = _split_legacy_command(command)
    elif isinstance(manifest.get("verify_command_argv"), list):
        resolved_argv = _normalize_verify_argv(manifest.get("verify_command_argv") or [])
    else:
        legacy_command = str(manifest.get("verify_command") or manifest.get("command") or "").strip()
        if legacy_command:
            resolved_argv = _split_legacy_command(legacy_command)
            command_source = "method_code_manifest_legacy_string"
        else:
            inferred = _infer_verify_command_argv(project_path, manifest)
            if not inferred:
                raise MethodsGateError(
                    "No safe method verification command was found. Add methods/method_code_manifest.json verify_command_argv, "
                    "or provide a project runner such as methods/scripts/run_analysis.py."
                )
            resolved_argv, command_source, migration_note = inferred
            manifest.setdefault("migration_note", migration_note)
    if not resolved_argv:
        raise MethodsGateError(
            "No method verification command was provided. Pass --command or generate methods/method_code_manifest.json with verify_command_argv."
        )
    resolved_outputs = output_files if output_files else _manifest_list(manifest, "declared_outputs", "output_files")
    resolved_inputs = input_data if input_data else _manifest_list(manifest, "input_data", "input_files")
    selected_input = manifest.get("selected_input_data")
    if selected_input and str(selected_input) not in resolved_inputs:
        resolved_inputs.append(str(selected_input))
    return resolved_argv, _command_display(resolved_argv), command_source, resolved_outputs, resolved_inputs, manifest


def _write_process_log(log_dir: Path, name: str, text: str) -> dict[str, Any]:
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / name
    path.write_text(text or "", encoding="utf-8", errors="replace")
    return {
        "path": str(path.relative_to(log_dir.parents[1])),
        "characters": len(text or ""),
        "truncated_in_manifest": len(text or "") > VERIFY_LOG_LIMIT,
        "excerpt": (text or "")[-VERIFY_LOG_LIMIT:],
    }


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
    checked_contracts = []
    for contract in contracts:
        if not isinstance(contract, dict):
            continue
        if str(contract.get("manuscript_role") or "").strip().lower() == "appendix":
            continue
        if contract.get("counts_toward_main_figures") is False:
            continue
        checked_contracts.append(contract)
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
        "contract_count": len(checked_contracts),
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
    previous_run = _read_json(methods_dir / "run_manifest.yaml", {})
    previous_output_hashes = (
        previous_run.get("output_artifact_hashes")
        if isinstance(previous_run, dict) and isinstance(previous_run.get("output_artifact_hashes"), dict)
        else {}
    )
    _ensure_method_plan(state.path)
    command_argv, command_display, command_source, declared_outputs, resolved_input_data, method_code_manifest = _resolve_verification_inputs(
        state.path,
        command,
        output_files,
        input_data,
    )

    started_at = utc_now()
    completed = subprocess.run(command_argv, cwd=state.path, shell=False, capture_output=True, text=True)
    finished_at = utc_now()
    log_stamp = re.sub(r"[^0-9A-Za-z_-]", "", started_at)[:24] or "latest"
    run_log_dir = methods_dir / "run_logs"
    stdout_log = _write_process_log(run_log_dir, f"verify_methods_{log_stamp}.stdout.txt", completed.stdout)
    stderr_log = _write_process_log(run_log_dir, f"verify_methods_{log_stamp}.stderr.txt", completed.stderr)
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
    output_artifact_hashes = {
        str(relative).replace("\\", "/"): hashlib.sha256(_project_relative_path(state.path, relative).read_bytes()).hexdigest()
        for relative in declared_outputs
        if _project_relative_path(state.path, relative).is_file()
    }
    manifest = {
        "status": status,
        "command": command_display,
        "command_argv": command_argv,
        "command_source": command_source,
        "shell_used": False,
        "returncode": completed.returncode,
        "input_data": resolved_input_data,
        "output_files": declared_outputs,
        "output_artifact_hashes": output_artifact_hashes,
        "method_code_manifest": method_code_manifest,
        "metrics": parsed_metrics,
        "figures_generated": [item for item in declared_outputs if item.lower().endswith((".png", ".jpg", ".jpeg", ".pdf", ".svg"))],
        "tables_generated": [item for item in declared_outputs if item.lower().endswith((".csv", ".tsv", ".xlsx", ".json"))],
        "started_at": started_at,
        "finished_at": finished_at,
        "stdout": stdout_log["excerpt"],
        "stderr": stderr_log["excerpt"],
        "stdout_log": stdout_log,
        "stderr_log": stderr_log,
        "missing_outputs": missing_outputs,
        "figure_quality_issues": figure_quality_issues,
        "figure_contract_issues": figure_contract_issues,
        "figure_contract_checks": figure_contract_checks,
        "review_task_coverage_issues": review_task_coverage_issues,
    }
    _write_manifest(methods_dir / "run_manifest.yaml", manifest)
    if status == "success":
        _write_method_formulas(state.path, manifest)
        from .plugin_execution import record_project_method_run

        record_project_method_run(state.path, output_files=declared_outputs)
    if status == "success":
        # A verified project-local implementation is a completed code stage;
        # do not force a later generator to overwrite it merely because the
        # implementation was supplied by an Agent rather than codegen.
        update_stage_status(state.path, "code", "approved")
    update_stage_status(state.path, "methods", "approved" if status == "success" else "failed")
    if status == "success" and output_artifact_hashes != previous_output_hashes:
        mark_stage_stale(state.path, "methods")
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
    manifest = _method_code_manifest(project_path)
    coverage_policy = manifest.get("review_task_coverage") if isinstance(manifest, dict) else None
    if isinstance(coverage_policy, dict) and coverage_policy.get("enabled") is False:
        return []
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
        is_workflow_schematic = str(item.get("plot_grammar") or "").lower() == "workflow_schematic"
        if not item.get("has_axes") and not is_workflow_schematic:
            issues.append(f"{relative} metadata must confirm axes or scale.")
        if not item.get("axis_labels") and not is_workflow_schematic:
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


def _drop_internal_method_sentences(text: str) -> str:
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


def _humanize_method_text(text: str) -> str:
    output = str(text or "")
    for token, label in METHOD_TOKEN_LABELS.items():
        output = re.sub(rf"\b{re.escape(token)}\b", label, output)
        output = re.sub(rf"\b{re.escape(token.replace('_', '-'))}\b", label, output)
    output = re.sub(r"\b(?:history|current)_[A-Za-z0-9_]+_id\b", "observation identifier", output, flags=re.I)
    output = re.sub(r"\b[A-Za-z0-9_]+_(?:file|path|filename|pathname)\b", "data-product descriptor", output, flags=re.I)
    output = output.replace("software operations", "analytical steps")
    output = re.sub(r"(^|(?<=[.!?])\s+)Use\s+", r"\1The analysis uses ", output)
    output = re.sub(r"(^|(?<=[.!?])\s+)Build\s+from\s+", r"\1The model is built from ", output)
    output = re.sub(r"(^|(?<=[.!?])\s+)Build\s+", r"\1The model is built to support ", output)
    output = re.sub(r"(^|(?<=[.!?])\s+)Treat\s+", r"\1The planned comparisons treat ", output)
    output = re.sub(r"(^|(?<=[.!?])\s+)Restrict claims to\s+", r"\1Claims are restricted to ", output)
    output = re.sub(r";\s*do not claim\s+", "; claims do not extend to ", output)
    output = output.replace("as planned model comparisons", "as model-comparison axes")
    output = output.replace("Current planned modeling route:", "The modeling route combines")
    output = _canonicalize_method_label_text(output)
    return output


def _canonicalize_method_label_text(text: str) -> str:
    """Clean repeated labels created by layered field-name normalization."""
    output = str(text or "")
    replacements = {
        "classification target target": "classification target",
        "class label label": "class label",
        "processing-processing-version metadata metadata": "processing-version metadata",
        "processing-version metadata metadata": "processing-version metadata",
        "metadata metadata": "metadata",
        "detector detector metadata": "detector metadata",
        "observation observation identifier": "observation identifier",
        "identifier identifier": "identifier",
        "products products": "products",
        "processed research processed research materials": "processed research materials",
    }
    for old, new in replacements.items():
        output = re.sub(re.escape(old), new, output, flags=re.I)
    return output


def _canonical_method_column_label(column: str) -> str:
    """Map an input column or data role to a prose-safe scientific label."""
    raw = _strip_forbidden_paths(str(column or "")).strip()
    if not raw:
        return ""
    normalized = raw.lower().replace("-", "_")
    if normalized in METHOD_TOKEN_LABELS:
        return METHOD_TOKEN_LABELS[normalized]
    label = _humanize_method_text(raw).strip()
    label = re.sub(r"\b[A-Za-z0-9]+_[A-Za-z0-9_]+\b", lambda match: match.group(0).replace("_", " "), label)
    return _canonicalize_method_label_text(label).strip()


def _dedupe_method_labels(labels: list[str]) -> list[str]:
    kept: list[str] = []
    seen: set[str] = set()
    for label in labels:
        cleaned = _canonicalize_method_label_text(label).strip(" ,;.")
        if not cleaned:
            continue
        key = re.sub(r"\s+", " ", cleaned.lower())
        if key in seen:
            continue
        seen.add(key)
        kept.append(cleaned)
    return kept


def _code_output_role_labels(outputs: list[Any]) -> list[str]:
    labels: list[str] = []
    for item in outputs:
        text = str(item or "").replace("\\", "/").lower()
        if not text:
            continue
        if "generated_pipeline" in text or "run_analysis" in text:
            labels.append("stage-owned analysis pipeline")
        elif "scientific_plotting" in text or "plot" in text:
            labels.append("publication figure utilities")
        elif "test_" in text or "/tests/" in text:
            labels.append("execution smoke tests")
        elif "requirements" in text:
            labels.append("declared analysis dependencies")
        elif "manifest" in text:
            labels.append("method-output trace records")
    return _dedupe_method_labels(labels)


def _method_role_label(role: str) -> str:
    normalized = str(role or "").strip().lower()
    labels = {
        "figure_generation": "scientific figure synthesis",
        "method_model_or_analysis": "model fitting and statistical analysis",
        "method_support_library": "reusable analytical utilities",
        "time_aware_transformer_training": "time-aware sequence classification",
        "baseline_model": "baseline model comparison",
        "ablation_study": "ablation analysis",
        "spatial_block_validation": "spatially blocked validation",
    }
    return labels.get(normalized, normalized.replace("_", " ") or "method implementation")


def _section_profile_for_methods(context: dict[str, Any], formula_entries: list[dict[str, Any]]) -> dict[str, str]:
    blob = " ".join(
        str(value or "")
        for value in [
            context.get("method_family_summary"),
            context.get("data_role"),
            context.get("analysis_steps"),
            context.get("code_trace_summary"),
        ]
    ).lower()
    formula_blob = " ".join(str(item.get("method_step") or item.get("name") or "") for item in formula_entries).lower()
    combined = blob + " " + formula_blob
    if any(token in combined for token in ["transformer", "light-curve", "light curve", "spectral", "astronom", "current-observation", "time2vec"]):
        return {
            "design": "Sample Construction and Observation Products",
            "model": "Temporal, Spectral, and Tabular Representation",
            "validation": "Classifier Objective, Validation, and Ablation",
            "bridge": "The method follows the evidence chain used to generate the main figures: event-level sample construction, current-observation tokens, historical time-series context, spectral or tabular features, temporal encoding, feature fusion, validation, ablation, and metrics.",
        }
    if any(token in combined for token in ["random forest", "xgboost", "classification", "regression", "ablation", "baseline"]):
        return {
            "design": "Sample Construction and Feature Sets",
            "model": "Model Formulation and Training Objective",
            "validation": "Validation, Baselines, Ablation, and Metrics",
            "bridge": "The method is organized around sample construction, feature representation, model fitting, validation design, baseline comparison, ablation, and diagnostic metrics.",
        }
    return {
        "design": "Sample Construction and Analytical Design",
        "model": "Model and Feature Formulation",
        "validation": "Validation and Metrics",
        "bridge": "The method is organized around sample construction, representation, model formulation, optimization, validation, and diagnostic metrics so that each empirical claim remains tied to the verified inputs and outputs.",
    }


def _latex_formula_entries(context: dict[str, Any]) -> list[dict[str, Any]]:
    payload = context.get("formula_manifest") if isinstance(context.get("formula_manifest"), dict) else {}
    entries = payload.get("formulas") if isinstance(payload, dict) else []
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict) and str(entry.get("latex") or "").strip()]


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


def _method_citation_paragraphs(project_dir: Path, existing: str) -> list[str]:
    ensure_reference_usage_plan(project_dir)
    entries = missing_entries_for_section(project_dir, "methods", existing)
    if not entries:
        return []
    paragraphs: list[str] = []
    sentences: list[str] = []
    for entry in entries:
        key = str(entry.get("citation_key") or "")
        evidence = _drop_internal_method_sentences(entry.get("evidence_summary") or entry.get("title"))
        if key and evidence:
            sentences.append(f"{_safe_latex_text(evidence)} \\citep{{{key}}}.")
    for index in range(0, len(sentences), 4):
        paragraphs.append(" ".join(sentences[index:index + 4]))
    return paragraphs


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
        return f"Model evaluation reports {_humanize_method_text(str(primary))}={observed} against a predefined acceptance value of {threshold}."
    if observed is not None:
        return f"Model evaluation reports {_humanize_method_text(str(primary))}={observed}; interpretation remains conditional because no explicit acceptance value was configured."
    if metrics:
        compact = ", ".join(f"{_humanize_method_text(str(key))}={value}" for key, value in list(metrics.items())[:5])
        return "Model evaluation reports scalar outputs including " + compact + "."
    return "The implemented analysis completed without parsed scalar metrics, so the method narrative should focus on validated inputs, outputs, and claim boundaries rather than performance magnitude."


def _analysis_steps_text(requirements: dict[str, Any], observations: list[dict[str, Any]], analysis_manifest: dict[str, Any]) -> str:
    observed = " ".join(_clean_sentence(item.get("text")) for item in observations if item.get("kind") in {"method_rationale", "agent_analysis", "code_design", "method_summary"})
    user_method = _clean_sentence(requirements.get("user_method"))
    if observed and user_method:
        return _humanize_method_text(user_method + " " + observed)[:1600]
    if observed:
        return _humanize_method_text(observed)[:1400]
    if user_method:
        return _humanize_method_text(user_method)
    method_excerpt = _clean_sentence(analysis_manifest.get("method_plan_excerpt"))
    if method_excerpt:
        return _humanize_method_text(method_excerpt[:1000])
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
    role_labels: list[str] = []
    for column in columns:
        label = _canonical_method_column_label(str(column))
        if label:
            role_labels.append(label)
    role_labels = _dedupe_method_labels(role_labels)
    if role_labels:
        column_text = ", ".join(role_labels[:10])
        return "The analysis uses prepared scientific variable groups, including " + column_text + ", to connect the data evidence with the planned analysis."
    inputs = manifest.get("input_data") or []
    if inputs:
        return "The analysis uses user-specified, analysis-ready inputs rather than making unverified raw-data claims."
    return "The analysis uses the evidence approved by the data feasibility gate."


def _method_code_trace_text(analysis_manifest: dict[str, Any], formula_manifest: dict[str, Any], figure_code_trace: dict[str, Any]) -> str:
    files = analysis_manifest.get("files") if isinstance(analysis_manifest, dict) else []
    formula_count = int(formula_manifest.get("formula_count") or len(formula_manifest.get("formulas") or [])) if isinstance(formula_manifest, dict) else 0
    trace_count = int(
        figure_code_trace.get("trace_count")
        or len(figure_code_trace.get("traces") or [])
        or len(figure_code_trace.get("figure_checks") or [])
    ) if isinstance(figure_code_trace, dict) else 0
    pieces = []
    if isinstance(files, list) and files:
        roles = sorted({str(item.get("code_role") or "method_code") for item in files if isinstance(item, dict)})
        pieces.append(
            "The implemented analysis scripts cover "
            + ", ".join(_method_role_label(role) for role in roles[:5])
            + "."
        )
    elif isinstance(analysis_manifest, dict) and analysis_manifest.get("canonical_code_outputs"):
        role_labels = _code_output_role_labels(analysis_manifest.get("canonical_code_outputs") or [])
        if role_labels:
            pieces.append(
                "The implemented method package covers "
                + ", ".join(role_labels[:5])
                + "."
            )
        else:
            pieces.append("The implemented method package records stage-owned analysis outputs, so the method narrative remains tied to verified execution rather than unrun design notes.")
    elif isinstance(analysis_manifest, dict) and analysis_manifest.get("method_families"):
        families = [
            _method_role_label(str(item))
            for item in analysis_manifest.get("method_families") or [] if str(item)
        ]
        pieces.append(
            "The verified project-local method implementation covers "
            + ", ".join(families[:8])
            + (", and related validation diagnostics." if len(families) > 8 else ".")
        )
    else:
        pieces.append("No dedicated method-code summary was found, so the method narrative must remain conservative.")
    if formula_count:
        pieces.append("The mathematical specification covers representation, prediction, optimization, validation, and diagnostic metrics where supported by the implemented analysis.")
    else:
        pieces.append("No method formula has been extracted yet; formula-bearing methods should regenerate the method context before final Methods writing.")
    if trace_count:
        pieces.append("Figure-linked summaries are used to align validation metrics and diagnostic quantities with the empirical outputs.")
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


def _ast_call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _ast_call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _safe_ast_literal(node: ast.AST) -> Any:
    try:
        value = ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return None
    if isinstance(value, str) and (re.search(r"[A-Za-z]:[\\/]", value) or value.startswith(("/", "\\\\"))):
        return None
    if isinstance(value, (list, tuple, dict, set)) and len(value) > 40:
        return None
    return value if isinstance(value, (str, int, float, bool, list, tuple, dict, set, type(None))) else None


def _method_reproducibility_contract(project_path: Path) -> dict[str, Any]:
    code_files = sorted({
        *project_path.glob("methods/scripts/**/*.py"),
        *project_path.glob("methods/analysis/**/*.py"),
        *project_path.glob("methods/code/**/*.py"),
    })
    imports: set[str] = set()
    constants: dict[str, Any] = {}
    feature_groups: dict[str, list[str]] = {}
    calls: list[dict[str, Any]] = []
    call_names_seen: set[str] = set()
    for path in code_files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8-sig", errors="replace"))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                value_node = node.value
                value = _safe_ast_literal(value_node) if value_node is not None else None
                for target in targets:
                    if not isinstance(target, ast.Name) or value is None:
                        continue
                    name = target.id
                    lowered = name.lower()
                    if isinstance(value, (list, tuple)) and value and all(isinstance(item, str) for item in value):
                        if any(token in lowered for token in ("feature", "column", "predictor", "covariate", "input")):
                            feature_groups[name] = list(value)
                    elif name.isupper() and name not in {"PROJECT", "RESULTS", "FIGURES", "TABLES"}:
                        constants[name] = value
            elif isinstance(node, ast.Call):
                name = _ast_call_name(node.func).split(".")[-1]
                if not name or name in call_names_seen:
                    continue
                if not (name[:1].isupper() or name.lower().endswith(("split", "score", "metric"))):
                    continue
                kwargs = {}
                for keyword in node.keywords:
                    if keyword.arg:
                        value = _safe_ast_literal(keyword.value)
                        if value is not None:
                            kwargs[keyword.arg] = value
                calls.append({"component": name, "parameters": kwargs})
                call_names_seen.add(name)
    provenance = _read_json(project_path / "methods" / "model_provenance.json", {})
    environment = _read_json(project_path / "methods" / "environment_manifest.json", {})
    splitters = [item for item in calls if any(token in item["component"].lower() for token in ("split", "fold", "kfold"))]
    estimators = [item for item in calls if any(token in item["component"].lower() for token in ("regression", "classifier", "forest", "boost", "svm", "network", "model"))]
    transforms = [item for item in calls if any(token in item["component"].lower() for token in ("imputer", "scaler", "pca", "encoder", "transform"))]
    return {
        "schema_version": "dpl.method_reproducibility_contract.v1",
        "source_file_count": len(code_files),
        "software_modules": sorted(imports),
        "software_versions": environment.get("packages") or environment.get("software_versions") or {},
        "model_provenance": provenance,
        "declared_constants": constants,
        "feature_groups": feature_groups,
        "preprocessing_components": transforms,
        "estimators": estimators,
        "validation_splitters": splitters,
        "all_implemented_components": calls,
        "required_writer_topics": [
            "input and target construction",
            "preprocessing order and train-fold fitting boundary",
            "model or checkpoint provenance",
            "feature groups and exclusions",
            "estimator hyperparameters and convergence",
            "validation splitter, group unit, seeds, and tuning policy",
            "metric aggregation and uncertainty interpretation",
            "software environment or explicitly unavailable version metadata",
            "preprocessing scope for every compared model or pipeline variant",
            "whether the comparison is a nested feature addition or a non-nested pipeline contrast",
        ],
        "comparison_semantics_policy": "Describe a score difference as an incremental or conditional feature contribution only when one variant preserves the other variant's inputs and transformations. Otherwise call it a model- or pipeline-performance contrast and name the differing preprocessing.",
        "policy": "Write only implemented or explicitly unavailable details; never infer missing checkpoint, preprocessing, tuning, software metadata, or nested-comparison semantics.",
    }


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
    _write_method_formulas(state.path, manifest)
    formula_manifest = _read_json(state.path / "methods" / "method_formula_manifest.json", {})
    figure_code_trace = _read_json(state.path / "results" / "figure_code_trace.json", {})
    if not figure_code_trace:
        figure_code_trace = _read_json(state.path / "results" / "figure_plugin_trace_report.json", {})
    method_blueprint = _read_json(state.path / "methods" / "method_blueprint.json", {})
    plugin_binding_plan = _read_json(state.path / "research_plan" / "plugin_binding_plan.json", {})
    method_bindings = [
        item for item in plugin_binding_plan.get("bindings") or []
        if isinstance(item, dict) and item.get("kind") == "method" and item.get("state") in {"covered", "covered_project_local"}
    ]
    if method_blueprint and "method_code_plan" not in analysis_manifest:
        analysis_manifest["method_code_plan"] = method_blueprint.get("method_code_plan") or {}
    family_summary = _method_family_text(requirements)
    analysis_steps = _strip_forbidden_paths(_analysis_steps_text(requirements, observations, analysis_manifest))
    binding_families = [str(item.get("requirement_id") or "").split(":")[-1].replace("_", " ") for item in method_bindings]
    if binding_families:
        analysis_steps = _strip_forbidden_paths(
            analysis_steps + " The implemented analysis uses declared method roles for " + ", ".join(dict.fromkeys(binding_families)) + "."
        )
    data_role = _strip_forbidden_paths(_data_role_text(manifest, analysis_manifest))
    code_trace_summary = _strip_forbidden_paths(_method_code_trace_text(analysis_manifest, formula_manifest, figure_code_trace))
    verification_summary = _strip_forbidden_paths(_metrics_text(manifest, requirements))
    claim_boundary = _clean_sentence(feasibility.get("supported_claim_level"))
    if claim_boundary:
        claim_boundary = "Interpretation is bounded by current data support: " + claim_boundary + "."
    else:
        claim_boundary = "Interpretation remains aligned with the available data and validated empirical outputs."
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
        "method_plugin_bindings": method_bindings,
        "method_code_manifest": analysis_manifest,
        "formula_manifest": formula_manifest if isinstance(formula_manifest, dict) else {},
        "figure_code_trace": figure_code_trace if isinstance(figure_code_trace, dict) else {},
        "reproducibility_contract": _method_reproducibility_contract(state.path),
        "narrative_summary": narrative_summary,
        "forbidden_in_manuscript": ["local filesystem paths", "execution commands", "manifest field dumps", "raw output file lists"],
    }
    try:
        context["resolved_result_evidence"] = resolve_result_evidence(state.path)
    except ResultEvidenceError:
        context["resolved_result_evidence"] = {}
    context["scientific_evidence_registry"] = build_scientific_evidence_registry(state.path)
    context["writing_brief"] = build_method_writing_brief(state.path, context)
    context_path = state.path / "methods" / "method_writing_context.json"
    _write_json(context_path, context)
    write_html_report(state.path / "methods" / "method_writing_context.html", _render_method_context_md(context), title="Method Writing Context")
    update_stage_status(state.path, "methods_writing", "draft")
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
    brief = context.get("writing_brief") if isinstance(context.get("writing_brief"), dict) else {}
    stage_briefs = brief.get("stage_briefs") if isinstance(brief.get("stage_briefs"), list) else []
    stage_goals = [
        _drop_internal_method_sentences(item.get("writing_goal"))
        for item in stage_briefs[:6]
        if isinstance(item, dict) and item.get("writing_goal")
    ]
    data_role_raw = _drop_internal_method_sentences(context.get("data_role", ""))
    analysis_steps_raw = _drop_internal_method_sentences(context.get("analysis_steps", ""))
    verification_raw = _drop_internal_method_sentences(context.get("verification_summary", ""))
    code_trace_raw = _drop_internal_method_sentences(context.get("code_trace_summary", ""))
    boundary_raw = _drop_internal_method_sentences(context.get("claim_boundary", ""))
    family_raw = _drop_internal_method_sentences(context.get("method_family_summary", ""))
    formula_entries = _latex_formula_entries(context)
    section_profile = _section_profile_for_methods(context, formula_entries)
    step_tokens = _formula_step_tokens(formula_entries)
    project_path = context.get("project_path")
    citation_paragraphs: list[str] = []
    if project_path:
        existing = "\n\n".join([family_raw, data_role_raw, analysis_steps_raw, verification_raw, boundary_raw])
        citation_paragraphs = _method_citation_paragraphs(Path(str(project_path)), existing)

    introduction = _safe_latex_text(
        " ".join(
            part for part in [
                family_raw,
                data_role_raw,
                section_profile["bridge"],
            ] if part
        )
    )
    stage_sentence = " ".join(stage_goals[:3])
    design = _safe_latex_text(
        " ".join(
            part for part in [
                analysis_steps_raw,
                stage_sentence,
                "Data construction, feature representation, model fitting, and validation are therefore treated as linked parts of the same empirical test rather than as separate bookkeeping steps.",
            ] if part
        )
    )
    trace = _safe_latex_text(code_trace_raw) if code_trace_raw else ""
    model_formula_block = _render_formula_block(
        formula_entries,
        only_steps={"temporal", "sequence", "feature", "prediction", "optimization", "model", "softmax", "classifier", "loss"},
    )
    validation_formula_block = _render_formula_block(
        formula_entries,
        only_steps={"validation", "metric", "ablation", "classification", "association", "pearson", "correlation", "auc"},
    )
    if not model_formula_block and formula_entries:
        split = max(1, len(formula_entries) // 2)
        model_formula_block = _render_formula_block(formula_entries[:split])
    if not validation_formula_block and len(formula_entries) > 1:
        split = max(1, len(formula_entries) // 2)
        validation_formula_block = _render_formula_block(formula_entries[split:])
    if model_formula_block:
        model_formula_block = "\n\n" + model_formula_block
    if validation_formula_block:
        validation_formula_block = "\n\n" + validation_formula_block
    citation_block = ""
    if citation_paragraphs:
        citation_block = "\n\n" + "\n\n".join(citation_paragraphs)
    representation_sentence = "Sequence or temporal representations are defined explicitly because the ordering, cadence, and masking of observations affect the information available to the model."
    if "sequence" not in step_tokens:
        representation_sentence = "Feature construction is described before model fitting so that the input variables and claim boundary remain clear."
    if stage_goals:
        representation_sentence += " " + " ".join(stage_goals[3:5])
    validation_sentence = "Validation uses the verified outputs and declared metrics to determine whether the fitted model supports the planned empirical comparison."
    if stage_goals[5:]:
        validation_sentence += " " + " ".join(stage_goals[5:])
    if boundary_raw:
        validation_sentence += " " + boundary_raw
    if verification_raw:
        validation_sentence += " " + verification_raw
    return (
        "\\section{Methods}\n"
        f"{introduction}\n\n"
        f"\\subsection{{{section_profile['design']}}}\n"
        f"{design} {trace}\n\n"
        f"\\subsection{{{section_profile['model']}}}\n"
        f"{_safe_latex_text(representation_sentence)}{model_formula_block}{citation_block}\n\n"
        f"\\subsection{{{section_profile['validation']}}}\n"
        f"{_safe_latex_text(validation_sentence.replace('verified outputs and declared metrics', 'held-out evaluation outputs and model metrics'))}{validation_formula_block}\n"
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
    from .manuscript_revision import assert_writer_may_replace_section
    assert_writer_may_replace_section(state.path, "methods")
    ensure_registry_consistent(state.path)
    manifest = _validate_successful_manifest(state.path)
    context = build_method_writing_context(state.path)
    methods_dir = state.path / "methods"
    output_path = methods_dir / "methods.tex"
    fallback = _render_methods_tex(state.metadata, manifest, context)
    try:
        composition = select_validated_section_draft(state.path, "methods", fallback)
    except SectionCompositionError as exc:
        raise MethodsGateError(str(exc)) from exc
    output_path.write_text(str(composition["text"]), encoding="utf-8")
    update_stage_status(state.path, "methods_writing", "draft")
    _set_methods_writing_manifest(state.path)
    return {
        "status": "written",
        "project_path": str(state.path),
        "methods": str(output_path),
        "run_manifest": str(methods_dir / "run_manifest.yaml"),
        "outputs": METHOD_OUTPUTS,
    }
