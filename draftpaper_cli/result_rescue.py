# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .discipline import infer_discipline_profile
from .discipline_modules import get_discipline_module
from .evidence_snapshot import EvidenceSnapshotMismatch, PROMOTED_EVIDENCE_SNAPSHOT_JSON, reopen_evidence_snapshot
from .html_utils import write_html_report
from .passport import utc_now
from .project_scaffold import _write_json
from .project_state import load_project, mark_stages_stale, update_stage_status
from .scoped_transaction import ScopedProjectTransaction
from .state_kernel import file_lock
from .result_support import (
    RESULT_SUPPORT_ROUTE_LOCK,
    ResultSupportError,
    bind_result_route_receipt,
    result_route_preflight,
)


RESULT_RESCUE_PLAN_JSON = "review/result_rescue_plan.json"
RESULT_RESCUE_PLAN_MD = "review/result_rescue_plan.md"
RESULT_RESCUE_PLAN_HTML = "review/result_rescue_plan.html"

SUPPLEMENT_STALE_STAGES = [
    "data",
    "method_plan",
    "method_feasibility",
    "figure_plan",
    "figure_contracts",
    "code",
    "methods",
    "result_validity",
    "result_support",
    "core_evidence",
    "results",
    "introduction",
    "data_writing",
    "methods_writing",
    "discussion",
    "latex",
    "quality_checks",
]


class ResultRescueError(RuntimeError):
    """Raised when the supplement data/method route cannot be prepared."""


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return default


def _tokens(text: Any) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-Z][a-zA-Z0-9_\-]{2,}", str(text or "").lower())
        if token not in {"the", "and", "for", "with", "from", "this", "that", "claim", "result", "method", "data"}
    }


def _claim_blob(claims: list[dict[str, Any]]) -> str:
    return " ".join(
        " ".join(str(item.get(key) or "") for key in ["claim_id", "planned_claim", "diagnosis", "failure_type"])
        for item in claims
    )


def _rank_by_tokens(items: list[dict[str, Any]], *, text: str, id_key: str) -> list[dict[str, Any]]:
    target = _tokens(text)
    ranked = []
    for item in items:
        blob = json.dumps(item, ensure_ascii=False, sort_keys=True)
        overlap = len(target & _tokens(blob))
        score = overlap + (1 if item.get("maturity") in {"runnable", "mature"} else 0)
        candidate = dict(item)
        candidate["match_score"] = score
        candidate["match_reason"] = "Matched failed-claim terms and discipline plugin metadata."
        ranked.append(candidate)
    ranked.sort(key=lambda value: (value.get("match_score", 0), str(value.get(id_key) or "")), reverse=True)
    return ranked


def _data_tasks(project_path: Path, failed_claims: list[dict[str, Any]], connectors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = _rank_by_tokens(connectors, text=_claim_blob(failed_claims), id_key="connector_id")
    tasks = []
    for index, connector in enumerate(ranked[:5], start=1):
        tasks.append({
            "task_id": f"data_supplement_{index}_{connector.get('connector_id')}",
            "task_type": "data_supplement",
            "connector_id": connector.get("connector_id"),
            "display_name": connector.get("display_name"),
            "feasibility_status": connector.get("feasibility_status"),
            "requires_credentials": bool(connector.get("requires_credentials")),
            "missing_packages": connector.get("missing_packages") or [],
            "missing_env_vars": connector.get("missing_env_vars") or [],
            "data_formats": connector.get("data_formats") or [],
            "download_or_access": connector.get("download_or_access") or [],
            "recommendation": "Use this discipline connector to fill missing evidence roles or enlarge the support cohort before regenerating figures.",
            "next_command": f'python -m draftpaper_cli.cli prepare-data-acquisition --project "{project_path}"',
        })
    if not tasks:
        tasks.append({
            "task_id": "data_supplement_generic_claim_evidence",
            "task_type": "data_supplement",
            "connector_id": "generic_user_or_agent_supplied_evidence",
            "display_name": "Generic claim-evidence data supplement",
            "feasibility_status": "requires_user_or_agent_confirmation",
            "requires_credentials": False,
            "missing_packages": [],
            "missing_env_vars": [],
            "data_formats": ["csv", "parquet", "json", "figure/table artifact"],
            "download_or_access": ["Use prepare-data-acquisition, public APIs, local processed artifacts, or user-provided remote outputs to fill the missing evidence roles."],
            "recommendation": "No discipline connector matched the failed claim strongly enough; define the minimal data artifact required to support or reject the claim before rerunning figures.",
            "next_command": f'python -m draftpaper_cli.cli prepare-data-acquisition --project "{project_path}"',
        })
    return tasks


def _method_tasks(project_path: Path, failed_claims: list[dict[str, Any]], templates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = _rank_by_tokens(templates, text=_claim_blob(failed_claims), id_key="template_id")
    tasks = []
    for index, template in enumerate(ranked[:6], start=1):
        tasks.append({
            "task_id": f"method_supplement_{index}_{template.get('template_id')}",
            "task_type": "method_supplement",
            "template_id": template.get("template_id"),
            "display_name": template.get("display_name"),
            "method_family": template.get("method_family"),
            "input_roles": template.get("input_roles") or [],
            "optional_roles": template.get("optional_roles") or [],
            "output_artifacts": template.get("output_artifacts") or [],
            "validation_checks": template.get("validation_checks") or [],
            "maturity": template.get("maturity"),
            "recommendation": "Use or adapt this discipline method template before rerunning result validity and result support.",
            "next_command": f'python -m draftpaper_cli.cli collect-method-plan --project "{project_path}"',
        })
    if not tasks:
        tasks.append({
            "task_id": "method_supplement_generic_claim_test",
            "task_type": "method_supplement",
            "template_id": "generic_claim_test_or_validation_method",
            "display_name": "Generic claim-testing method supplement",
            "method_family": "claim_validation",
            "input_roles": ["claim_evidence_data", "comparison_or_validation_design"],
            "optional_roles": ["baseline", "ablation", "uncertainty_or_sensitivity_check"],
            "output_artifacts": ["validated metrics", "main/supporting figures", "method run manifest"],
            "validation_checks": ["method output answers the failed claim", "metrics use one coherent cohort and unit", "figure contract variables match method outputs"],
            "maturity": "candidate",
            "recommendation": "No discipline method template matched the failed claim strongly enough; ask Codex to design or mine a project-specific method, then generalize it only after the full paper loop runs successfully.",
            "next_command": f'python -m draftpaper_cli.cli collect-method-plan --project "{project_path}"',
        })
    return tasks


def _open_source_search_tasks(profile: dict[str, Any], failed_claims: list[dict[str, Any]], method_tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    discipline = str(profile.get("primary_discipline") or profile.get("discipline") or "default")
    claim_terms = sorted(_tokens(_claim_blob(failed_claims)))[:8]
    template_terms = [str(item.get("method_family") or item.get("template_id") or "") for item in method_tasks[:4]]
    queries = []
    for index, term in enumerate([*template_terms, " ".join(claim_terms[:4])], start=1):
        query = " ".join(part for part in [discipline, term, "research code", "github", "paper"] if part).strip()
        if query and query not in queries:
            queries.append(query)
    return [
        {
            "task_id": f"open_source_code_search_{index}",
            "task_type": "open_source_code_search",
            "discipline": discipline,
            "query": query,
            "policy": "metadata_only_first; inspect structure/docs, generalize templates, validate fixtures before copying any reusable code",
            "recommended_commands": [
                "discover-research-repos",
                "score-research-repos",
                "extract-plugin-candidates",
                "inspect-research-repo",
                "map-repository-workflow",
                "generalize-plugin-candidate",
                "validate-plugin-candidate",
            ],
        }
        for index, query in enumerate(queries[:5], start=1)
    ]


def _render_markdown(plan: dict[str, Any]) -> str:
    lines = [
        "# Result Rescue Plan",
        "",
        f"Route: {plan.get('route')}",
        f"Discipline module: {plan.get('discipline_module')}",
        "",
        "This plan keeps the original research claim target, reopens the data/method/figure evidence chain, and prepares supplement tasks before any manuscript writing continues.",
        "",
        "## Failed Or Partial Claims",
        "",
    ]
    for claim in plan.get("failed_claims") or []:
        lines.append(f"- {claim.get('claim_id')}: {claim.get('failure_type') or claim.get('support_status')}")
        if claim.get("diagnosis"):
            lines.append(f"  - Diagnosis: {claim.get('diagnosis')}")
    lines.extend(["", "## Data Supplement Tasks", ""])
    for task in plan.get("data_supplement_tasks") or []:
        lines.append(f"- {task.get('connector_id')}: {task.get('display_name')} ({task.get('feasibility_status')})")
    lines.extend(["", "## Method Supplement Tasks", ""])
    for task in plan.get("method_supplement_tasks") or []:
        lines.append(f"- {task.get('template_id')}: {task.get('display_name')} ({task.get('maturity')})")
    lines.extend(["", "## Open-source Code Search Tasks", ""])
    for task in plan.get("open_source_code_search_tasks") or []:
        lines.append(f"- {task.get('query')}")
    snapshot_policy = plan.get("evidence_snapshot_policy") or {}
    lines.extend(["", "## Evidence Snapshot Policy", ""])
    lines.append(f"- Route: {snapshot_policy.get('route')}")
    lines.append(f"- Reopen required: {snapshot_policy.get('reopen_required')}")
    if snapshot_policy.get("archived_snapshot"):
        lines.append(f"- Archived snapshot: `{snapshot_policy.get('archived_snapshot')}`")
    lines.extend(["", "## Next Commands", ""])
    for command in plan.get("recommended_next_commands") or []:
        lines.append(f"- `{command}`")
    lines.append("")
    return "\n".join(lines)


def prepare_result_rescue(project: str | Path, *, checkpoint_hash: str | None = None) -> dict[str, Any]:
    """Choose the supplement route and prepare data/method rescue tasks."""
    state = load_project(project)
    project_path = state.path
    checkpoint_path = project_path / "results" / "result_support_checkpoint.json"
    route_lock_target = project_path / RESULT_SUPPORT_ROUTE_LOCK
    transaction_patterns = (
        "project.json",
        "project.yaml",
        "**/stage_manifest.json",
        RESULT_RESCUE_PLAN_JSON,
        RESULT_RESCUE_PLAN_MD,
        RESULT_RESCUE_PLAN_HTML,
        PROMOTED_EVIDENCE_SNAPSHOT_JSON,
        "results/evidence_snapshots/**",
        "results/evidence_snapshot_reopen_report.json",
        "results/result_support_checkpoint.json",
    )
    with file_lock(route_lock_target):
        support = _read_json(checkpoint_path, {})
        if not isinstance(support, dict) or not support:
            raise ResultRescueError("Run assess-result-support before prepare-result-rescue.")
        try:
            preflight = result_route_preflight(
                project_path,
                support,
                route="supplement_data_and_method",
                checkpoint_hash=checkpoint_hash,
            )
        except ResultSupportError as exc:
            raise ResultRescueError(str(exc)) from exc
        if preflight:
            return preflight
        failed_claims = [item for item in support.get("failed_claims") or support.get("claim_assessments") or [] if isinstance(item, dict) and item.get("support_status") in {"not_supported", "partially_supported"}]
        if not failed_claims and support.get("decision") == "pass":
            raise ResultRescueError("Result support already passes; no supplement route is required.")
        with ScopedProjectTransaction(project_path, transaction_patterns) as transaction:
            profile = infer_discipline_profile(project_path, extra_text=_claim_blob(failed_claims))
            module = get_discipline_module(profile)
            hints = module.method_blueprint_hints({"profile": profile, "failed_claims": failed_claims})
            data_tasks = _data_tasks(project_path, failed_claims, list(hints.get("data_acquisition_hints") or []))
            method_tasks = _method_tasks(project_path, failed_claims, list(hints.get("method_template_hints") or []))
            search_tasks = _open_source_search_tasks(profile, failed_claims, method_tasks)
            snapshot_policy: dict[str, Any] = {
                "schema_version": "dpl.result_rescue_snapshot.v1",
                "route": "supplement_data_and_method",
                "policy": "Supplement route reopens the evidence chain; any promoted evidence snapshot must be archived before new data, methods, figures, and manuscript text are produced.",
                "reopen_required": True,
                "archived_snapshot": None,
            }
            if (project_path / PROMOTED_EVIDENCE_SNAPSHOT_JSON).exists():
                try:
                    reopened = reopen_evidence_snapshot(project_path, reason="Result support supplement route selected.")
                    snapshot_policy["archived_snapshot"] = reopened.get("archived_snapshot")
                    snapshot_policy["archived_snapshot_id"] = reopened.get("archived_snapshot_id")
                except EvidenceSnapshotMismatch as exc:
                    snapshot_policy["archive_warning"] = str(exc)
            recommended = [
                f'python -m draftpaper_cli.cli prepare-data-acquisition --project "{project_path}"',
                f'python -m draftpaper_cli.cli collect-method-plan --project "{project_path}"',
                f'python -m draftpaper_cli.cli plan-figures --project "{project_path}"',
                f'python -m draftpaper_cli.cli generate-analysis-code --project "{project_path}"',
                f'python -m draftpaper_cli.cli verify-methods --project "{project_path}"',
                f'python -m draftpaper_cli.cli assess-result-validity --project "{project_path}"',
                f'python -m draftpaper_cli.cli assess-result-support --project "{project_path}"',
            ]
            plan = {
                "status": "prepared",
                "schema_version": "dpl.result_rescue_plan.v2",
                "route": "supplement_data_and_method",
                "generated_at": utc_now(),
                "project_id": state.metadata.get("project_id"),
                "discipline_profile": profile,
                "discipline_module": module.spec.module_id,
                "failed_claims": failed_claims,
                "data_supplement_tasks": data_tasks,
                "method_supplement_tasks": method_tasks,
                "open_source_code_search_tasks": search_tasks,
                "recommended_next_commands": recommended,
                "evidence_snapshot_policy": snapshot_policy,
                "stale_policy": "Supplement route reopens data/method/figure/evidence/manuscript chain because new evidence must be generated and revalidated.",
            }
            review_dir = project_path / "review"
            review_dir.mkdir(parents=True, exist_ok=True)
            _write_json(project_path / RESULT_RESCUE_PLAN_JSON, plan)
            markdown = _render_markdown(plan)
            (project_path / RESULT_RESCUE_PLAN_MD).write_text(markdown, encoding="utf-8")
            write_html_report(project_path / RESULT_RESCUE_PLAN_HTML, markdown, title="Result Rescue Plan")
            support["result_rescue_plan"] = RESULT_RESCUE_PLAN_JSON
            support["requires_user_decision"] = False
            support["decision"] = "supplement_prepared"
            support["evidence_snapshot_policy"] = snapshot_policy
            stale = mark_stages_stale(project_path, SUPPLEMENT_STALE_STAGES)
            update_stage_status(project_path, "result_support", "failed")
            receipt = bind_result_route_receipt(support, route="supplement_data_and_method")
            _write_json(checkpoint_path, support)
            transaction.commit()
    return {
        "status": "prepared",
        "project_path": str(project_path),
        "route": "supplement_data_and_method",
        "result_rescue_plan": str(project_path / RESULT_RESCUE_PLAN_JSON),
        "data_task_count": len(data_tasks),
        "method_task_count": len(method_tasks),
        "open_source_search_task_count": len(search_tasks),
        "stale_stages": stale,
        "recommended_next_commands": recommended,
        "checkpoint_sha256": support["checkpoint_sha256"],
        "route_receipt": receipt,
    }


__all__ = [
    "RESULT_RESCUE_PLAN_JSON",
    "RESULT_RESCUE_PLAN_MD",
    "RESULT_RESCUE_PLAN_HTML",
    "SUPPLEMENT_STALE_STAGES",
    "ResultRescueError",
    "prepare_result_rescue",
]
