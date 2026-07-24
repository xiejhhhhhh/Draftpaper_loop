"""Authoritative public capabilities exposed to optional extensions."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from .contracts import HostCapabilities


HOST_CAPABILITIES = (
    "artifact.read_by_role",
    "artifact.resolve_selector",
    "extension.failure_isolation",
    "extension.learning_slot",
    "extension.read_scoped_token",
    "workflow.event.artifact_invalidated",
    "workflow.event.checkpoint_confirmed",
    "workflow.event.checkpoint_opened",
    "workflow.event.manuscript_finalized",
    "workflow.event.review_completed",
    "workflow.event.stage_committed",
)


def _core_version() -> str:
    try:
        return version("draftpaper-cli")
    except PackageNotFoundError:
        return "0.33.1"


def build_host_capabilities(*, core_version: str | None = None) -> HostCapabilities:
    return HostCapabilities(
        core_version=core_version or _core_version(),
        abi_family="dpl.extension",
        abi_versions=("1.0",),
        stage_taxonomy_version="1.0",
        artifact_schema_families={
            "artifact_dependency_dag": ("v2",),
            "evidence_snapshot": ("v1",),
            "figure_manifest": ("v2",),
            "research_plan": ("v2", "v3"),
            "stage_receipt": ("v1",),
        },
        capabilities=HOST_CAPABILITIES,
    )
