from __future__ import annotations

from draftpaper_cli.command_registry import COMMAND_SPECS
from draftpaper_cli.protected_action_policy import (
    HUMAN_CHECKPOINT_POLICIES,
    audit_human_checkpoint_policy,
    build_operation_effect_fingerprint,
)


def test_all_historical_human_checkpoint_commands_have_explicit_decision_policies() -> None:
    audit = audit_human_checkpoint_policy(COMMAND_SPECS)

    assert audit["status"] == "passed"
    assert audit["historical_human_checkpoint_count"] == 28
    assert {row["command"] for row in audit["rows"] if row["explicit"]} == set(HUMAN_CHECKPOINT_POLICIES)


def test_confirm_literature_corpus_has_its_own_explicit_human_policy() -> None:
    policy = HUMAN_CHECKPOINT_POLICIES["confirm-literature-corpus"]

    assert policy == {
        "decision_family": "literature_corpus",
        "packet_policy": "compact",
        "risk_resolver": "literature_corpus_identity",
        "receipt_contract": "literature_confirmation_receipt",
        "delegation_policy": "human_only",
        "default_risk": "C2",
    }


def test_checkpoint_build_and_resume_consume_receipts_without_new_human_decisions() -> None:
    checkpoint = COMMAND_SPECS["checkpoint"]
    resume = COMMAND_SPECS["resume"]

    assert checkpoint.decision_family == "notification"
    assert checkpoint.packet_policy == "none"
    assert checkpoint.confirmation_policy == "packet_build"
    assert resume.decision_family == "notification"
    assert resume.packet_policy == "none"
    assert resume.receipt_contract == "existing_receipt"


def test_operation_effect_fingerprint_is_stable_for_the_same_declared_effect() -> None:
    first = build_operation_effect_fingerprint(
        "quarantine-orphan-literature",
        {"active_work_count": 2, "paths": ["references/fulltext/a.pdf", "references/fulltext/b.pdf"]},
    )
    second = build_operation_effect_fingerprint(
        "quarantine-orphan-literature",
        {"active_work_count": 2, "paths": ["references/fulltext/a.pdf", "references/fulltext/b.pdf"]},
    )

    assert first["schema_version"] == "dpl.operation_effect_fingerprint.v1"
    assert first["operation_effect_sha256"] == second["operation_effect_sha256"]
