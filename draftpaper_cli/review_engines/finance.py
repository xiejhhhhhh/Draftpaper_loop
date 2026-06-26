# Copyright (c) 2026 xiejhhhhhh
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

from typing import Any

from .base import context_text, issue_payload


def discover(context: dict[str, Any], discipline_profile: dict[str, Any]) -> list[dict[str, Any]]:
    text = context_text(context)
    gaps = [
        issue_payload(
            code="finance_lookahead_bias_audit",
            title="Audit look-ahead bias and time ordering",
            severity="blocking",
            target_stage="methods",
            rationale="Finance reviewers expect features, portfolio weights, and event windows to use only information available at the decision time.",
            actions=["verify time-ordered feature construction", "separate estimation, event, and evaluation windows", "rerun validation with chronological splits"],
            requires_user_confirmation=True,
            confirmation_question="Can the project provide timestamps sufficient for look-ahead bias auditing?",
            evidence=["finance review engine", "project archive context"],
        ),
        issue_payload(
            code="finance_transaction_cost_sensitivity",
            title="Add transaction-cost and robustness sensitivity",
            severity="major",
            target_stage="result_validity",
            rationale="Backtest and portfolio claims are fragile without transaction-cost, slippage, or robustness checks.",
            actions=["add cost assumptions", "compare gross and net performance", "report sensitivity of Sharpe/drawdown claims"],
            evidence=["finance review engine"],
        ),
    ]
    if any(token in text for token in ("event study", "abnormal return", "car")):
        gaps.append(issue_payload(
            code="finance_event_window_justification",
            title="Justify event and estimation windows",
            severity="major",
            target_stage="method_plan",
            rationale="Event-study claims require defensible event windows, benchmark alignment, and confounding-event handling.",
            actions=["state event window", "state estimation window", "screen overlapping or confounding events"],
            evidence=["event-study signal"],
        ))
    return gaps
