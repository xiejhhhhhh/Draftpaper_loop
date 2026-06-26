# Copyright (c) 2026 xiejhhhhhh
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

from typing import Any

from .base import issue_payload


def discover(context: dict[str, Any], discipline_profile: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        issue_payload(
            code="biology_multiple_testing_fdr_audit",
            title="Check multiple-testing and FDR control",
            severity="blocking",
            target_stage="methods",
            rationale="Biological feature-set analyses need explicit multiple-testing correction before claiming differential features or enriched pathways.",
            actions=["state FDR method", "report adjusted p-values", "avoid uncorrected feature-level claims"],
            evidence=["biology review engine"],
        ),
        issue_payload(
            code="biology_replicate_batch_audit",
            title="Separate biological replicates from batch effects",
            severity="major",
            target_stage="data",
            rationale="Reviewers will question biological claims when replicate structure, batch, donor, plate, or run effects are unclear.",
            actions=["record biological replicate count", "check batch labels", "state whether batch correction is justified"],
            evidence=["biology review engine"],
        ),
        issue_payload(
            code="biology_control_validation_audit",
            title="Clarify controls and validation boundary",
            severity="major",
            target_stage="discussion",
            rationale="Assay and pathway interpretations need controls and a clear boundary between computational evidence and biological validation.",
            actions=["state positive/negative controls", "separate exploratory and validated findings", "avoid overclaiming mechanism"],
            evidence=["biology review engine"],
        ),
    ]
