from __future__ import annotations

import json
from pathlib import Path

from draftpaper_cli.command_registry import COMMAND_SPECS
from draftpaper_cli.jobs import submit_job, wait_for_job
from draftpaper_cli.mcp import service
from draftpaper_cli.mcp_install import mcp_doctor
from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.workflow_trace import audit_workflow_runtime, begin_workflow_trace, finish_workflow_trace


def test_thin_mcp_surface_and_protected_actions() -> None:
    names = service.public_tool_names()
    assert 8 <= len(names) <= 12
    assert all("shell" not in name and "write_file" not in name and "sql" not in name for name in names)
    protected = service.plan_command("checkpoint")
    assert protected["status"] == "protected"
    assert protected["mcp_allowed"] is False
    doctor = mcp_doctor()
    assert doctor["checks"]["tool_count_in_range"] is True
    assert doctor["checks"]["protected_commands_excluded"] is True


def test_mcp_artifact_reader_is_confined_truncated_and_selective(tmp_path: Path) -> None:
    project = create_project(root=tmp_path, idea="MCP artifact", field="engineering").path
    target = project / "review" / "summary.json"
    target.write_text(json.dumps({"rows": list(range(100)), "secret": "visible scientific label"}), encoding="utf-8")
    result = service.artifact_get(str(project), "review/summary.json", "rows", max_items=3)
    assert result["status"] == "read"
    assert result["content"] == [0, 1, 2]
    assert result["truncated"] is True
    escaped = service.artifact_get(str(project), "../outside.json")
    assert escaped["status"] == "boundary_violation"


def test_execute_science_requires_command_hash_capability_token(tmp_path: Path) -> None:
    project = create_project(root=tmp_path, idea="MCP capability", field="engineering").path
    denied = service.execute_command(str(project), "verify-methods", "{}", confirm_science_execution=True)
    assert denied["status"] == "confirmation_required"
    plan = service.plan_command("verify-methods", str(project), "{}")
    assert plan["confirmation_token"]
    executed = service.execute_command(
        str(project),
        "verify-methods",
        "{}",
        capability_token=plan["confirmation_token"],
    )
    assert executed["status"] in {"completed", "non_passing"}


def test_mcp_rejects_non_project_path_arguments_before_execution(tmp_path: Path) -> None:
    project = create_project(root=tmp_path, idea="MCP path", field="engineering").path
    outside = tmp_path / "outside.tex"
    outside.write_text("outside", encoding="utf-8")
    result = service.execute_command(
        str(project),
        "submit-section-draft",
        json.dumps({"section": "methods", "input": str(outside)}),
    )
    assert result["status"] == "boundary_violation"
    assert result["argument"] == "input"


def test_runtime_trace_separates_process_science_and_transaction(tmp_path: Path) -> None:
    project = create_project(root=tmp_path, idea="Trace", field="engineering").path
    trace = begin_workflow_trace(project, "verify-methods", {"project": str(project)})
    finish_workflow_trace(project, trace, process_status="completed", command_exit_code=1, transaction_status="committed", scientific_decision="failed", failure_class="scientific_gate")
    report = audit_workflow_runtime(project)
    assert report["command_count"] == 1
    row = json.loads((project / "workflow_trace.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert row["process_status"] == "completed"
    assert row["scientific_decision"] == "failed"
    assert row["transaction_status"] == "committed"


def test_persistent_job_survives_submitter_and_records_scientific_result(tmp_path: Path) -> None:
    project = create_project(root=tmp_path, idea="Durable job", field="engineering").path
    submitted = submit_job(project, "validate-project", json.dumps({}), "validate-project-once", timeout_seconds=30)
    assert submitted["status"] == "submitted"
    final = wait_for_job(project, submitted["job_id"], timeout_seconds=45)
    assert final["wait_status"] == "terminal"
    job = final["job"]
    assert job["status"] == "completed"
    assert job["process_status"] == "completed"
    assert job["scientific_decision"]
