"""FastMCP stdio server exposing the transport-neutral Draftpaper service."""

from __future__ import annotations

from typing import Any

from . import service


def create_server():
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError("Draftpaper MCP requires the optional dependency: pip install draftpaper-cli[mcp]") from exc

    server = FastMCP("Draftpaper-loop")

    @server.tool()
    def draftpaper_project_status(project: str) -> dict[str, Any]: return service.project_status(project)

    @server.tool()
    def draftpaper_doctor(project: str | None = None) -> dict[str, Any]: return service.doctor(project)

    @server.tool()
    def draftpaper_next_action(project: str) -> dict[str, Any]: return service.next_action(project)

    @server.tool()
    def draftpaper_plan_command(command: str, project: str | None = None, arguments_json: str | None = None) -> dict[str, Any]:
        return service.plan_command(command, project, arguments_json)

    @server.tool()
    def draftpaper_execute_command(project: str, command: str, arguments_json: str | None = None, confirm_science_execution: bool = False, capability_token: str | None = None) -> dict[str, Any]:
        return service.execute_command(project, command, arguments_json, confirm_science_execution=confirm_science_execution, capability_token=capability_token)

    @server.tool()
    def draftpaper_job_submit(project: str, command: str, arguments_json: str | None = None, idempotency_key: str | None = None, capability_token: str | None = None) -> dict[str, Any]:
        return service.job_submit(project, command, arguments_json, idempotency_key, capability_token)

    @server.tool()
    def draftpaper_job_status(project: str, job_id: str) -> dict[str, Any]: return service.job_get(project, job_id)

    @server.tool()
    def draftpaper_artifact_get(project: str, path: str, selector: str | None = None, max_items: int = 50, max_bytes: int = 131072) -> dict[str, Any]:
        return service.artifact_get(project, path, selector, max_items, max_bytes)

    @server.tool()
    def draftpaper_review_summary(project: str) -> dict[str, Any]: return service.review_summary(project)

    @server.tool()
    def draftpaper_runtime_audit(project: str) -> dict[str, Any]: return service.runtime_audit(project)

    return server


def main() -> None:
    create_server().run(transport="stdio")


if __name__ == "__main__":
    main()
