# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

from typing import Any

from .base import issue_payload


def discover(context: dict[str, Any], discipline_profile: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        issue_payload(
            code="engineering_unit_boundary_condition_audit",
            title="Audit units, calibration, and boundary conditions",
            severity="blocking",
            target_stage="data",
            rationale="Engineering reviewers expect units, calibration state, operating conditions, and simulation/experiment boundary conditions to be explicit.",
            actions=["check unit consistency", "record calibration state", "state boundary and operating conditions"],
            requires_user_confirmation=True,
            confirmation_question="Can the project provide unit, calibration, and boundary-condition metadata?",
            evidence=["engineering review engine"],
        ),
        issue_payload(
            code="engineering_convergence_sensitivity_audit",
            title="Add convergence or sensitivity evidence",
            severity="major",
            target_stage="methods",
            rationale="Simulation, signal-processing, and optimization claims often require mesh, timestep, sampling, or parameter sensitivity checks.",
            actions=["add convergence diagnostics", "vary key parameters", "report whether conclusions are stable"],
            evidence=["engineering review engine"],
        ),
        issue_payload(
            code="engineering_physical_plausibility_audit",
            title="Check physical plausibility of reported patterns",
            severity="major",
            target_stage="result_validity",
            rationale="Engineering results should be checked against known physical constraints or domain expectations before broad claims.",
            actions=["compare against expected ranges", "flag impossible values", "state physical interpretation limits"],
            evidence=["engineering review engine"],
        ),
    ]
