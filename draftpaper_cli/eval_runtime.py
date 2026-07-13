"""Privacy-preserving local capture, software baseline, replay, and regression gate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .command_registry import COMMAND_SPECS
from .passport import read_jsonl, utc_now
from .project_state import load_project


EVAL_ROOT = "quality_checks/eval"
PRIVATE_CONTENT_PREFIXES = (
    "introduction/", "data/raw/", "data/processed/", "methods/src/", "results/figures/",
    "discussion/", "latex/", "references/literature_summaries/",
)
VOLATILE_CAPTURE_PATHS = {
    "project_passport.yaml", "artifact_ledger.jsonl", "checkpoint_ledger.jsonl",
    "integrity_ledger.jsonl", "transaction_ledger.jsonl",
}


class EvalRuntimeError(RuntimeError):
    """Raised when a capture, replay, or gate artifact is invalid."""


def _read(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvalRuntimeError(f"Invalid eval artifact {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise EvalRuntimeError(f"Eval artifact must be an object: {path}")
    return payload


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _schema_signature(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    result: dict[str, Any] = {"suffix": suffix, "size_class": "empty" if path.stat().st_size == 0 else "nonempty"}
    if suffix in {".json", ".yaml", ".yml"}:
        try:
            if suffix == ".json":
                payload = json.loads(path.read_text(encoding="utf-8-sig"))
            else:
                import yaml
                payload = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
            if isinstance(payload, dict):
                result["top_level_keys"] = sorted(str(key) for key in payload)
            elif isinstance(payload, list):
                result["container"] = "list"
        except Exception:
            result["parse_status"] = "invalid"
    return result


def _artifact_topology(root: Path) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or ".git" in path.parts:
            continue
        relative = path.relative_to(root).as_posix()
        stable_hash = not (relative in VOLATILE_CAPTURE_PATHS or relative.startswith(EVAL_ROOT + "/"))
        rows.append({
            "path": relative,
            "sha256": _sha(path) if stable_hash else None,
            "schema": _schema_signature(path),
            "content_captured": False,
            "stable_hash_contract": stable_hash,
            "privacy_class": "private_or_scientific" if relative.startswith(PRIVATE_CONTENT_PREFIXES) else "structural",
        })
    return rows


def _route_decisions(root: Path) -> list[dict[str, Any]]:
    rows = []
    for relative in (
        "research_plan/discipline_contract.json",
        "research_plan/research_capability_contract.json",
        "research_plan/plugin_sufficiency_report.json",
        "research_plan/plugin_binding_plan.json",
        "results/result_evidence_resolution.json",
    ):
        path = root / relative
        if not path.is_file():
            continue
        payload = _read(path)
        rows.append({
            "artifact": relative,
            "status": payload.get("status") or payload.get("decision"),
            "selected_disciplines": payload.get("discipline_modules") or payload.get("secondary_disciplines") or [],
            "schema_version": payload.get("schema_version"),
        })
    return rows


def capture_eval(project: str | Path, case: str) -> dict[str, Any]:
    state = load_project(project)
    topology = _artifact_topology(state.path)
    transactions = read_jsonl(state.path / "transaction_ledger.jsonl")
    capture = {
        "schema_version": "dpl.eval_capture.v1",
        "capture_kind": "software_regression_only",
        "case_id": str(case),
        "created_at": utc_now(),
        "local_project_locator": str(state.path),
        "project_id_hash": hashlib.sha256(str(state.metadata.get("project_id")).encode()).hexdigest(),
        "stage_state": {
            name: {"status": item.get("status"), "stale": bool(item.get("stale"))}
            for name, item in (state.metadata.get("stages") or {}).items()
            if isinstance(item, dict)
        },
        "artifact_topology": topology,
        "command_sequence": [item.get("command") for item in transactions if item.get("command")],
        "route_decisions": _route_decisions(state.path),
        "expected_invariants": {
            "registered_command_count": len(COMMAND_SPECS),
            "artifact_count": len(topology),
            "stale_stages": sorted(name for name, item in (state.metadata.get("stages") or {}).items() if isinstance(item, dict) and item.get("stale")),
        },
        "redaction_report": {
            "raw_data_captured": False,
            "manuscript_text_captured": False,
            "credentials_captured": False,
            "server_addresses_captured": False,
            "full_prompts_captured": False,
            "artifact_content_captured": False,
        },
    }
    target = state.path / EVAL_ROOT / "captures" / f"{case}.json"
    _write(target, capture)
    return {"status": "captured", "capture": str(target.relative_to(state.path)).replace("\\", "/"), "artifact_count": len(topology), "redaction_report": capture["redaction_report"]}


def baseline_eval(capture: str | Path, output: str | Path | None = None) -> dict[str, Any]:
    source = Path(capture).expanduser().resolve()
    payload = _read(source)
    if payload.get("capture_kind") != "software_regression_only":
        raise EvalRuntimeError("Only privacy-preserving software regression captures can become baselines.")
    topology = [
        {"path": item.get("path"), "sha256": item.get("sha256"), "schema": item.get("schema"), "privacy_class": item.get("privacy_class")}
        for item in payload.get("artifact_topology") or []
        if isinstance(item, dict)
    ]
    baseline = {
        "schema_version": "dpl.eval_baseline.v1",
        "baseline_kind": "software_regression_invariants",
        "case_id": payload.get("case_id"),
        "created_at": utc_now(),
        "source_capture_sha256": _sha(source),
        "stage_state": payload.get("stage_state") or {},
        "artifact_topology": topology,
        "route_decisions": payload.get("route_decisions") or [],
        "expected_invariants": payload.get("expected_invariants") or {},
        "manuscript_baseline_prohibited": True,
        "private_locator_removed": True,
    }
    target = Path(output).expanduser().resolve() if output else source.with_name(source.stem + ".baseline.json")
    _write(target, baseline)
    return {"status": "baselined", "baseline": str(target), "baseline_kind": baseline["baseline_kind"]}


def replay_eval(project: str | Path, baseline: str | Path) -> dict[str, Any]:
    state = load_project(project)
    source = Path(baseline).expanduser().resolve()
    expected = _read(source)
    if expected.get("baseline_kind") != "software_regression_invariants":
        raise EvalRuntimeError("Replay requires a software regression baseline, not a manuscript baseline.")
    current_topology = _artifact_topology(state.path)
    expected_paths = {str(item.get("path")): item for item in expected.get("artifact_topology") or [] if isinstance(item, dict)}
    current_paths = {str(item.get("path")): item for item in current_topology}
    missing = sorted(set(expected_paths) - set(current_paths))
    schema_changes = sorted(
        path for path in set(expected_paths) & set(current_paths)
        if expected_paths[path].get("schema") != current_paths[path].get("schema")
    )
    content_hash_changes = sorted(
        path for path in set(expected_paths) & set(current_paths)
        if expected_paths[path].get("sha256") and expected_paths[path].get("sha256") != current_paths[path].get("sha256")
    )
    expected_commands = int((expected.get("expected_invariants") or {}).get("registered_command_count") or 0)
    command_count_matches = not expected_commands or expected_commands == len(COMMAND_SPECS)
    report = {
        "schema_version": "dpl.eval_replay.v1",
        "case_id": expected.get("case_id"),
        "generated_at": utc_now(),
        "status": "passed" if not missing and not schema_changes and not content_hash_changes and command_count_matches else "failed",
        "missing_artifacts": missing,
        "schema_changes": schema_changes,
        "content_hash_changes": content_hash_changes,
        "registered_command_count": len(COMMAND_SPECS),
        "registered_command_count_matches": command_count_matches,
        "content_comparison_performed": False,
        "manuscript_quality_comparison_performed": False,
    }
    target = state.path / EVAL_ROOT / "replays" / f"{expected.get('case_id') or 'case'}.json"
    _write(target, report)
    return {**report, "report": str(target.relative_to(state.path)).replace("\\", "/")}


def gate_eval(report: str | Path) -> dict[str, Any]:
    payload = _read(Path(report).expanduser().resolve())
    passed = payload.get("status") == "passed" and not payload.get("missing_artifacts") and not payload.get("schema_changes") and not payload.get("content_hash_changes")
    return {
        "status": "passed" if passed else "failed",
        "case_id": payload.get("case_id"),
        "structural_regression": "passed" if passed else "failed",
        "scientific_semantic_correctness": "not_claimed_by_structural_replay",
        "manuscript_quality_comparison_performed": False,
    }


def run_eval_command(
    action: str,
    *,
    project: str | Path | None = None,
    case: str | None = None,
    capture: str | Path | None = None,
    baseline: str | Path | None = None,
    report: str | Path | None = None,
    output: str | Path | None = None,
) -> dict[str, Any]:
    if action == "capture":
        if not project or not case:
            raise EvalRuntimeError("eval capture requires --project and --case.")
        return capture_eval(project, case)
    if action == "baseline":
        if not capture:
            raise EvalRuntimeError("eval baseline requires --capture.")
        return baseline_eval(capture, output)
    if action == "replay":
        if not project or not baseline:
            raise EvalRuntimeError("eval replay requires --project and --baseline.")
        return replay_eval(project, baseline)
    if action == "gate":
        if not report:
            raise EvalRuntimeError("eval gate requires --report.")
        return gate_eval(report)
    raise EvalRuntimeError(f"Unsupported eval action: {action}")
