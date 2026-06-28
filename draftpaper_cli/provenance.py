# Copyright (c) 2026 xiejhhhhhh
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

from copy import deepcopy
from typing import Any


PROJECT_PROVENANCE: dict[str, str] = {
    "name": "Draftpaper-loop",
    "author": "xiejhhhhhh",
    "repository": "https://github.com/xiejhhhhhh/Draftpaper_loop",
    "license": "Source-Available Non-Commercial",
    "commercial_contact": "xiejinhui22@mails.ucas.ac.cn",
    "sponsorship_note": "Sponsorship or donation supports project maintenance but does not grant commercial use rights.",
}

DPL_SCHEMAS: dict[str, str] = {
    "schema_family": "dpl",
    "project": "dpl.project.v1",
    "project_passport": "dpl.project_passport.v1",
    "stage_manifest": "dpl.stage_manifest.v1",
    "citation_evidence": "dpl.citation_evidence.v1",
    "evidence_registry": "dpl.evidence_registry.v1",
    "claim_trace": "dpl.claim_trace.v1",
    "run_manifest": "dpl.run_manifest.v1",
    "result_manifest": "dpl.result_manifest.v1",
    "artifact_hash": "dpl.artifact_hash.v1",
    "loop_event": "dpl.loop_event.v1",
    "discipline_profile": "dpl.discipline_profile.v1",
    "manuscript_projection": "dpl.manuscript_projection.v1",
}


def generated_by_block(*, schema_version: str | None = None) -> dict[str, str]:
    block = deepcopy(PROJECT_PROVENANCE)
    block["schema_family"] = DPL_SCHEMAS["schema_family"]
    if schema_version:
        block["schema_version"] = schema_version
    return block


def dpl_block(**schemas: str) -> dict[str, str]:
    block = {"schema_family": DPL_SCHEMAS["schema_family"]}
    block.update(schemas)
    return block


def attach_dpl_metadata(payload: dict[str, Any], *, schema_key: str, schema_field: str | None = None) -> dict[str, Any]:
    enriched = dict(payload)
    field = schema_field or f"{schema_key}_schema"
    schema_version = DPL_SCHEMAS[schema_key]
    enriched.setdefault("dpl", dpl_block(**{field: schema_version}))
    enriched.setdefault("generated_by", generated_by_block(schema_version=schema_version))
    return enriched
