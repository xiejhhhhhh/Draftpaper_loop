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
from ..figure_contracts import collect_figure_contract_issues
from ..result_evidence import ResultEvidenceError, resolve_result_evidence
from ..writing_brief import METHOD_WRITING_BRIEF_HTML, METHOD_WRITING_BRIEF_JSON, build_method_writing_brief
from ..write_set_guard import BoundaryViolation, resolve_confined_path

from .common import (
    MethodsGateError,
    SHELL_EXECUTABLE_NAMES,
    SHELL_OPERATOR_TOKENS,
    VERIFY_LOG_LIMIT,
    _ensure_method_plan,
    _manifest_list,
    _method_code_manifest,
    _missing_declared_outputs,
    _project_relative_path,
    _read_json,
    _read_manifest,
    _validate_project_paths,
    _write_manifest,
)

from .formulas import (
    _write_method_formulas,
)

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


def _validate_verify_argv(
    project_path: Path,
    argv: list[str],
    *,
    allow_inline_runner: bool,
    allow_system_binary: bool = False,
) -> tuple[list[str], str]:
    """Validate a formal project runner and return normalized argv plus mode."""
    normalized = _normalize_verify_argv(argv)
    executable = Path(normalized[0]).expanduser()
    executable_name = executable.name.lower()
    if executable_name in SHELL_EXECUTABLE_NAMES:
        raise MethodsGateError("Method verification executable is an interactive shell runner.")
    if executable.resolve() == Path(sys.executable).resolve():
        if len(normalized) >= 2 and normalized[1] == "-c":
            if not allow_inline_runner:
                raise MethodsGateError("Inline method verification code is not allowed for formal project runners.")
            return normalized, "inline_compatibility_runner"
        if len(normalized) < 2:
            raise MethodsGateError("Python method verification must name a project-local runner script.")
        script = _project_relative_path(project_path, normalized[1])
        if script.suffix.lower() != ".py" or not script.is_file():
            raise MethodsGateError("Method verification executable must be a project-local Python script.")
        return normalized, "project_local_python_runner"
    try:
        resolved_executable = resolve_confined_path(project_path, executable, must_exist=True)
        execution_mode = "project_local_executable"
    except BoundaryViolation as exc:
        if not allow_system_binary:
            raise MethodsGateError(
                "Method verification executable must be inside the project; use --allow-system-binary for an explicit external executable."
            ) from exc
        located = shutil.which(str(executable)) if not executable.is_absolute() else str(executable)
        if not located:
            raise MethodsGateError("Explicit system binary could not be resolved.") from exc
        try:
            resolved_executable = Path(located).expanduser().resolve(strict=True)
        except OSError as path_exc:
            raise MethodsGateError("Explicit system binary does not exist.") from path_exc
        execution_mode = "explicit_system_binary"
    except OSError as exc:
        raise MethodsGateError("Method verification executable does not exist.") from exc
    if not os.access(resolved_executable, os.X_OK):
        raise MethodsGateError("Method verification executable is not runnable.")
    normalized[0] = str(resolved_executable)
    return normalized, execution_mode


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
    *,
    allow_system_binary: bool = False,
) -> tuple[list[str], str, str, list[str], list[str], dict[str, Any]]:
    manifest = _method_code_manifest(project_path)
    command_source = "cli_override" if command else "method_code_manifest"
    allow_inline_runner = bool(manifest.get("allow_inline_runner"))
    if command:
        resolved_argv = _split_legacy_command(command)
        resolved_argv, execution_mode = _validate_verify_argv(
            project_path,
            resolved_argv,
            allow_inline_runner=False,
            allow_system_binary=allow_system_binary,
        )
        execution_mode = f"cli_override_{execution_mode}"
    elif isinstance(manifest.get("verify_command_argv"), list):
        resolved_argv = _normalize_verify_argv(manifest.get("verify_command_argv") or [])
        resolved_argv, execution_mode = _validate_verify_argv(project_path, resolved_argv, allow_inline_runner=allow_inline_runner)
    else:
        legacy_command = str(manifest.get("verify_command") or manifest.get("command") or "").strip()
        if legacy_command:
            resolved_argv = _split_legacy_command(legacy_command)
            command_source = "method_code_manifest_legacy_string"
            resolved_argv, execution_mode = _validate_verify_argv(project_path, resolved_argv, allow_inline_runner=allow_inline_runner)
        else:
            inferred = _infer_verify_command_argv(project_path, manifest)
            if not inferred:
                raise MethodsGateError(
                    "No safe method verification command was found. Add methods/method_code_manifest.json verify_command_argv, "
                    "or provide a project runner such as methods/scripts/run_analysis.py."
                )
            resolved_argv, command_source, migration_note = inferred
            resolved_argv, execution_mode = _validate_verify_argv(project_path, resolved_argv, allow_inline_runner=False)
            manifest.setdefault("migration_note", migration_note)
    if not resolved_argv:
        raise MethodsGateError(
            "No method verification command was provided. Pass --command or generate methods/method_code_manifest.json with verify_command_argv."
        )
    resolved_outputs = _validate_project_paths(
        project_path,
        output_files if output_files else _manifest_list(manifest, "declared_outputs", "output_files"),
        role="output",
    )
    resolved_inputs = _validate_project_paths(
        project_path,
        input_data if input_data else _manifest_list(manifest, "input_data", "input_files"),
        role="input",
    )
    selected_input = manifest.get("selected_input_data")
    if selected_input and str(selected_input) not in resolved_inputs:
        resolved_inputs.extend(_validate_project_paths(project_path, [str(selected_input)], role="input"))
    manifest["execution_mode"] = execution_mode
    return resolved_argv, _command_display(resolved_argv), command_source, resolved_outputs, resolved_inputs, manifest


def _write_process_log(log_dir: Path, name: str, text: str) -> dict[str, Any]:
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / name
    safe_text = str(redact_sensitive(text or ""))
    path.write_text(safe_text, encoding="utf-8", errors="replace")
    return {
        "path": str(path.relative_to(log_dir.parents[1])),
        "characters": len(safe_text),
        "truncated_in_manifest": len(safe_text) > VERIFY_LOG_LIMIT,
        "excerpt": safe_text[-VERIFY_LOG_LIMIT:],
    }


def _structured_stdout_payload(stdout: str) -> dict[str, Any]:
    """Return the final structured method payload without trusting free-form logs."""
    text = str(stdout or "").strip()
    if not text:
        return {}
    candidates = [text]
    candidates.extend(line.strip() for line in reversed(text.splitlines()) if line.strip())
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def _reported_output_files(project_path: Path, payload: dict[str, Any]) -> list[str]:
    """Accept only existing project-local files explicitly reported by a successful run."""
    if str(payload.get("status") or "").strip().lower() not in {"success", "passed", "complete", "completed"}:
        return []
    outputs = payload.get("outputs")
    if not isinstance(outputs, list):
        return []
    reported: list[str] = []
    for item in outputs:
        relative = str(item or "").strip().replace("\\", "/")
        if not relative:
            continue
        try:
            path = _project_relative_path(project_path, relative)
        except MethodsGateError:
            continue
        if path.is_file() and relative not in reported:
            reported.append(relative)
    return reported


def _verified_run_id(command_argv: list[str], outputs: list[str]) -> str:
    seed = json.dumps(
        {"command": command_argv, "outputs": outputs},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _structured_run_evidence(payload: dict[str, Any], *, run_id: str) -> list[dict[str, Any]]:
    """Bind explicit records and common scientific runner facts to one verified run."""
    explicit = payload.get("evidence_records")
    records = [dict(item) for item in explicit or [] if isinstance(item, dict)] if isinstance(explicit, list) else []
    seen = {json.dumps(item, ensure_ascii=False, sort_keys=True, default=str) for item in records}

    def add_record(record: dict[str, Any]) -> None:
        key = json.dumps(record, ensure_ascii=False, sort_keys=True, default=str)
        if key not in seen:
            records.append(record)
            seen.add(key)

    def add_metrics(metrics: Any, *, model_id: str, analysis_variant: str) -> None:
        if not isinstance(metrics, dict):
            return
        for name, value in metrics.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            add_record({
                "entity_role": f"result_metric_{str(name).strip().lower()}",
                "value": value,
                "unit": "score",
                "metric_dimension": "score",
                "cohort_id": "main",
                "sample_unit": "model_evaluation",
                "split": "run_summary",
                "run_id": run_id,
                "model_id": model_id,
                "analysis_variant": analysis_variant,
                "confidence": "verified_structured_run_output",
                "target_sections": ["results", "methods", "discussion"],
            })

    def add_cohort_audit(audit: Any) -> None:
        if not isinstance(audit, dict):
            return

        def walk(value: Any, path: list[str]) -> None:
            if isinstance(value, dict):
                for key, child in value.items():
                    walk(child, [*path, str(key)])
                return
            if isinstance(value, list):
                for index, child in enumerate(value):
                    walk(child, [*path, str(index)])
                return
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return
            role = "cohort_audit_" + "_".join(part.strip().lower() for part in path if part.strip())
            is_count = any(token in role for token in ("count", "total", "size", "support"))
            add_record({
                "entity_role": role,
                "value": value,
                "unit": "count" if is_count else "value",
                "metric_dimension": "count" if is_count else "value",
                "cohort_id": "main",
                "sample_unit": "source",
                "split": "declared_partition" if "split_counts" in role else "all",
                "run_id": run_id,
                "model_id": "not_applicable",
                "analysis_variant": "cohort_audit",
                "confidence": "verified_structured_run_output",
                "target_sections": ["results", "data", "methods", "discussion"],
            })

        walk(audit, [])

    primary_model = str(payload.get("model_id") or payload.get("primary_model_id") or "primary_model")
    add_metrics(payload.get("final_test_metrics"), model_id=primary_model, analysis_variant="primary")
    add_cohort_audit(payload.get("cohort_audit"))
    seed_runs = payload.get("seed_runs")
    if isinstance(seed_runs, list):
        for index, seed_run in enumerate(seed_runs):
            if not isinstance(seed_run, dict):
                continue
            seed = str(seed_run.get("seed") or index)
            model = str(seed_run.get("model_id") or payload.get("model_id") or "model")
            add_metrics(
                seed_run.get("final_test_metrics"),
                model_id=f"{model}_seed_{seed}",
                analysis_variant="multi_seed",
            )
            add_cohort_audit(seed_run.get("cohort_audit"))
    return records


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
    normalized = collect_figure_contract_issues(
        gate_report={
            "decision": "pass" if not issues else "blocked",
            "issues": [
                {"severity": "blocking", "kind": "method_figure_contract", "detail": item}
                for item in issues
            ],
        }
    )
    checks["normalized_issues"] = normalized["issues"]
    return issues, checks


def verify_methods(
    project: str | Path,
    *,
    command: str | None = None,
    output_files: list[str] | None = None,
    input_data: list[str] | None = None,
    allow_system_binary: bool = False,
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
        allow_system_binary=allow_system_binary,
    )

    started_at = utc_now()
    completed = subprocess.run(
        command_argv,
        cwd=state.path,
        shell=False,
        capture_output=True,
        text=True,
        env=sanitized_environment(),
    )
    finished_at = utc_now()
    log_stamp = re.sub(r"[^0-9A-Za-z_-]", "", started_at)[:24] or "latest"
    run_log_dir = methods_dir / "run_logs"
    stdout_log = _write_process_log(run_log_dir, f"verify_methods_{log_stamp}.stdout.txt", completed.stdout)
    stderr_log = _write_process_log(run_log_dir, f"verify_methods_{log_stamp}.stderr.txt", completed.stderr)
    structured_output = _structured_stdout_payload(completed.stdout) if completed.returncode == 0 else {}
    reported_outputs = _reported_output_files(state.path, structured_output)
    declared_outputs = list(dict.fromkeys([*declared_outputs, *reported_outputs]))
    run_id = _verified_run_id(command_argv, declared_outputs)
    run_evidence = _structured_run_evidence(structured_output, run_id=run_id)
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
        "execution_mode": method_code_manifest.get("execution_mode", "legacy_cli_override"),
        "shell_used": False,
        "returncode": completed.returncode,
        "run_id": run_id,
        "input_data": resolved_input_data,
        "output_files": declared_outputs,
        "reported_output_files": reported_outputs,
        "output_artifact_hashes": output_artifact_hashes,
        "method_code_manifest": method_code_manifest,
        "metrics": parsed_metrics,
        "evidence_records": run_evidence,
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
        from ..plugin_execution import record_project_method_run

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
