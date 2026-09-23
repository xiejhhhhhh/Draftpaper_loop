"""Run positive and negative governance controls outside the pytest suite."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

import draftpaper_cli.governance_contract as governance_contract  # noqa: E402
from draftpaper_cli.governance_contract import (  # noqa: E402
    CheckOutcome,
    EXPECTED_GOVERNANCE_CHECKERS,
    GovernanceCheckResult,
    _policy_registry_is_complete,
    evaluate_governance,
    load_governance_policy,
)
from draftpaper_cli.passport import refresh_project_passport  # noqa: E402
from draftpaper_cli.project_scaffold import create_project  # noqa: E402
from draftpaper_cli.revision_cycle import RevisionCycleError, begin_revision_cycle, close_revision_cycle  # noqa: E402
from draftpaper_cli.scientific_baseline import ACTIVE_POINTER, ScientificBaselineError, create_scientific_baseline  # noqa: E402


def run_controls() -> dict[str, object]:
    controls: list[dict[str, object]] = []
    policy = load_governance_policy()
    controls.append({"id": "policy_rule_registry", "status": "passed" if _policy_registry_is_complete(policy) else "failed"})
    with tempfile.TemporaryDirectory(prefix="draftpaper-governance-") as temp:
        project = create_project(root=Path(temp) / "project", idea="governance controls", field="generic").path
        create_scientific_baseline(project)
        method = project / "methods" / "control.py"
        method.parent.mkdir(parents=True, exist_ok=True)
        method.write_text("value = 1\n", encoding="utf-8")
        refresh_project_passport(project, event="governance_control")
        begin_revision_cycle(project, mode="author_edit")
        method.write_text("value = 2\n", encoding="utf-8")
        report = evaluate_governance(project, purpose="final")
        controls.append({"id": "drift_negative_control", "status": "passed" if not report["action_eligibility"]["allow_release"] else "failed"})
        checks_by_id = {str(item.get("rule_id")): item for item in report.get("checks") or [] if isinstance(item, dict)}
        expected_ids = {f"DG-{index:02d}" for index in range(1, 13)}
        control_facts = {
            "complete_rule_ids": set(checks_by_id) == expected_ids,
            "drift_rule_failed": checks_by_id.get("DG-02", {}).get("outcome") == "failed",
            "editing_allowed": report["action_eligibility"]["allow_edit"] is True,
            "preview_allowed": report["action_eligibility"]["allow_preview"] is True,
            "promotion_denied": report["action_eligibility"]["allow_promote"] is False,
            "close_denied": report["action_eligibility"]["allow_close"] is False,
            "release_denied": report["action_eligibility"]["allow_release"] is False,
        }
        controls.append({
            "id": "complete_rule_results_and_permission_separation",
            "status": "passed" if all(control_facts.values()) else "failed",
            "details": control_facts,
        })
        reported_rules = {str(item.get("rule_id")) for item in report.get("checks") or [] if isinstance(item, dict)}
        controls.extend(
            {
                "id": f"{item.get('rule_id')}_entrypoint_control",
                "status": "passed" if (
                    str(item.get("rule_id")) in reported_rules
                    and EXPECTED_GOVERNANCE_CHECKERS.get(str(item.get("rule_id"))) == item.get("checker")
                ) else "failed",
            }
            for item in policy.get("rules") or []
        )
        try:
            close_revision_cycle(project, decision_receipt_id="governance-control")
        except RevisionCycleError:
            controls.append({"id": "close_gate_negative_control", "status": "passed"})
        else:
            controls.append({"id": "close_gate_negative_control", "status": "failed"})
        original_result = governance_contract._result

        def omit_scope_result(
            rule_id: str,
            outcome: CheckOutcome,
            *,
            scope_digest: str,
            input_value: Any,
            summary_zh: str,
            summary_en: str,
            findings: list[tuple[str, str]] | None = None,
            refs: list[str] | None = None,
        ) -> GovernanceCheckResult:
            return original_result(
                "DG-99" if rule_id == "DG-03" else rule_id,
                outcome,
                scope_digest=scope_digest,
                input_value=input_value,
                summary_zh=summary_zh,
                summary_en=summary_en,
                findings=findings,
                refs=refs,
            )

        governance_contract._result = omit_scope_result  # type: ignore[assignment]
        try:
            mutated_report = evaluate_governance(project, purpose="final")
        finally:
            governance_contract._result = original_result
        mutated_checks = {str(item.get("rule_id")): item for item in mutated_report.get("checks") or [] if isinstance(item, dict)}
        controls.append({
            "id": "missing_checker_result_mutation_control",
            "status": "passed" if (
                mutated_checks.get("DG-12", {}).get("outcome") == "failed"
                and mutated_report["action_eligibility"]["allow_release"] is False
            ) else "failed",
        })
        corrupt_project = create_project(root=Path(temp) / "corrupt-project", idea="corrupt baseline", field="generic").path
        create_scientific_baseline(corrupt_project)
        pointer = corrupt_project / ACTIVE_POINTER
        pointer.write_text("{broken", encoding="utf-8")
        try:
            begin_revision_cycle(corrupt_project, mode="author_edit")
        except ScientificBaselineError:
            controls.append({"id": "corrupt_baseline_negative_control", "status": "passed"})
        else:
            controls.append({"id": "corrupt_baseline_negative_control", "status": "failed"})
    return {
        "schema_version": "dpl.evidence_governance_self_test.v1",
        "status": "passed" if all(item["status"] == "passed" for item in controls) else "failed",
        "controls": controls,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    report = run_controls()
    if args.output:
        target = Path(args.output).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
