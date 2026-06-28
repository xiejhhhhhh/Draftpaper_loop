# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

from typing import Any

from .base import issue_payload


def discover(context: dict[str, Any], discipline_profile: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        issue_payload(
            code="medicine_ethics_privacy_audit",
            title="Verify ethics, consent, and de-identification boundaries",
            severity="blocking",
            target_stage="data",
            rationale="Clinical manuscripts need explicit ethics approval, consent or waiver status, and privacy-preserving data handling before patient-level claims.",
            actions=["record IRB/ethics statement or waiver", "verify de-identification", "state data access restrictions"],
            requires_user_confirmation=True,
            confirmation_question="Can the user provide ethics approval, waiver, or de-identification documentation?",
            evidence=["medicine review engine"],
        ),
        issue_payload(
            code="medicine_cohort_definition_audit",
            title="Clarify cohort inclusion, index date, outcome, and follow-up",
            severity="blocking",
            target_stage="data",
            rationale="Clinical reviewers expect cohort construction to define eligibility, index date, exposure, outcome, censoring, and follow-up.",
            actions=["write inclusion/exclusion criteria", "define index date", "define follow-up and censoring"],
            evidence=["medicine review engine"],
        ),
        issue_payload(
            code="medicine_validation_calibration_audit",
            title="Check missingness, calibration, and validation boundary",
            severity="major",
            target_stage="methods",
            rationale="Clinical prediction or effect-estimation claims need missingness handling, calibration, and internal/external validation boundaries.",
            actions=["summarize missingness mechanism", "add calibration if prediction is involved", "state validation cohort boundary"],
            evidence=["medicine review engine"],
        ),
    ]
