"""Single read-only governance decision for evidence and manuscript release."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any, Literal

from .artifact_scope import collect_artifact_scope
from .artifact_identity import canonical_json
from .change_impact import artifact_role_for_path
from .evidence_binding import inspect_evidence_bindings
from .manuscript_scientific_surface import extract_manuscript_surface
from .passport import project_root
from .revision_cycle import load_active_revision_cycle
from .scientific_baseline import read_active_baseline_state
from .stale_sync import detect_artifact_drift


GOVERNANCE_SCHEMA = "dpl.evidence_governance_report.v1"
CheckOutcome = Literal["passed", "failed", "not_evaluated", "error", "not_applicable"]
EXPECTED_GOVERNANCE_CHECKERS = {
    "DG-01": "baseline",
    "DG-02": "drift",
    "DG-03": "scope",
    "DG-04": "bindings",
    "DG-05": "surface",
    "DG-06": "impact",
    "DG-07": "eligibility",
    "DG-08": "cycle",
    "DG-09": "ownership",
    "DG-10": "integrity",
    "DG-11": "self_test",
    "DG-12": "execution",
}


@dataclass(frozen=True)
class GovernanceCheckResult:
    rule_id: str
    outcome: CheckOutcome
    scope_digest: str
    input_digest: str
    finding_ids: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    summary_zh: str = ""
    summary_en: str = ""


@dataclass(frozen=True)
class ActionEligibility:
    allow_edit: bool
    allow_preview: bool
    allow_promote: bool
    allow_close: bool
    allow_release: bool
    blocking_finding_ids: tuple[str, ...] = ()


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def load_governance_policy() -> dict[str, Any]:
    path = files("draftpaper_cli").joinpath("resources/policies/evidence_governance_v1.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("rules"), list):
        raise ValueError("Packaged evidence governance policy is invalid.")
    return payload


def _policy_registry_is_complete(policy: dict[str, Any]) -> bool:
    rules = policy.get("rules")
    if not isinstance(rules, list):
        return False
    registered = {
        str(item.get("rule_id") or ""): str(item.get("checker") or "")
        for item in rules
        if isinstance(item, dict)
    }
    return len(rules) == len(EXPECTED_GOVERNANCE_CHECKERS) and registered == EXPECTED_GOVERNANCE_CHECKERS


def _result_set_is_complete(results: list[GovernanceCheckResult]) -> bool:
    expected_ids = {f"DG-{index:02d}" for index in range(1, 12)}
    emitted_ids = [result.rule_id for result in results]
    return len(emitted_ids) == len(expected_ids) and set(emitted_ids) == expected_ids


def _action_eligibility_for(
    results: list[GovernanceCheckResult],
    *,
    baseline_ok: bool,
    scope_ok: bool,
    cycle: dict[str, Any] | None,
    cycle_ok: bool,
) -> ActionEligibility:
    blocking = tuple(
        finding_id
        for result in results
        if result.outcome in {"failed", "error", "not_evaluated"}
        for finding_id in (result.finding_ids or (result.rule_id,))
    )
    strict_blocking = tuple(result.rule_id for result in results if result.outcome not in {"passed", "not_applicable"})
    release_ok = not strict_blocking and baseline_ok and scope_ok and (
        not cycle or cycle.get("reconciliation_status") == "reconciled"
    )
    return ActionEligibility(
        allow_edit=True,
        allow_preview=True,
        allow_promote=not blocking,
        allow_close=not blocking and cycle_ok,
        allow_release=release_ok,
        blocking_finding_ids=blocking,
    )


def _guard_governance_html_target(root: Path, output: str, surface: dict[str, Any]) -> Path:
    target = Path(output).expanduser().resolve()
    protected = {
        (root / str(item.get("path"))).resolve()
        for item in surface.get("artifacts") or []
        if isinstance(item, dict) and item.get("path")
    }
    if target in protected:
        raise ValueError("Governance HTML output cannot overwrite an author-owned manuscript source.")
    return target


def _surface_sources_are_intact(root: Path, surface: dict[str, Any]) -> tuple[bool, list[tuple[str, str]]]:
    if surface.get("status") != "passed":
        return False, [("surface", "surface_not_readable")]
    root_resolved = root.resolve()
    findings: list[tuple[str, str]] = []
    for item in surface.get("artifacts") or []:
        if not isinstance(item, dict) or not item.get("path"):
            findings.append(("surface", "source_identity_missing"))
            continue
        relative = Path(str(item["path"]))
        if relative.is_absolute() or ".." in relative.parts:
            findings.append((str(item["path"]), "source_path_outside_project"))
            continue
        source = (root / relative).resolve()
        try:
            source.relative_to(root_resolved)
        except ValueError:
            findings.append((str(item["path"]), "source_path_outside_project"))
            continue
        try:
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
        except OSError:
            findings.append((str(item["path"]), "source_unreadable"))
            continue
        if digest != item.get("source_sha256"):
            findings.append((str(item["path"]), "source_identity_mismatch"))
    return not findings, findings


def _finding_id(rule_id: str, object_id: str, reason: str) -> str:
    return f"{rule_id.lower()}-{_hash({'object': object_id, 'reason': reason})[:16]}"


def _result(
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
    findings = findings or []
    refs = refs or []
    finding_ids = tuple(_finding_id(rule_id, object_id, reason) for object_id, reason in findings)
    return GovernanceCheckResult(
        rule_id=rule_id,
        outcome=outcome,
        scope_digest=scope_digest,
        input_digest=_hash(input_value),
        finding_ids=finding_ids,
        evidence_refs=tuple(refs),
        summary_zh=summary_zh,
        summary_en=summary_en,
    )


def _serialize(result: GovernanceCheckResult) -> dict[str, Any]:
    return asdict(result) | {
        "finding_ids": list(result.finding_ids),
        "evidence_refs": list(result.evidence_refs),
    }


def evaluate_governance(
    project: str | Path,
    purpose: str = "preview",
    candidate_id: str | None = None,
    expected_baseline_id: str | None = None,
    html_output: str | None = None,
    language: str = "zh-CN",
    self_test_report: str | None = None,
) -> dict[str, Any]:
    """Evaluate governance without changing the project or advancing state."""
    if purpose not in {"preview", "final", "audit"}:
        raise ValueError("Governance purpose must be preview, final, or audit.")
    root = project_root(project)
    policy = load_governance_policy()
    baseline = read_active_baseline_state(root)
    scope = collect_artifact_scope(root, candidate_id=candidate_id)
    drift = detect_artifact_drift(root)
    bindings = inspect_evidence_bindings(root)
    surface = extract_manuscript_surface(root, candidate_id=candidate_id)
    cycle = load_active_revision_cycle(root)
    scope_digest = str(scope.get("scope_digest") or _hash(scope))
    results: list[GovernanceCheckResult] = []

    baseline_ok = baseline.get("status") == "valid" and (
        not expected_baseline_id or baseline.get("baseline", {}).get("baseline_id") == expected_baseline_id
    )
    results.append(_result(
        "DG-01", "passed" if baseline_ok else "not_evaluated" if baseline.get("status") == "not_initialized" else "failed",
        scope_digest=scope_digest, input_value=baseline,
        summary_zh="活动科学基线有效且比较身份固定。" if baseline_ok else f"科学基线状态为 {baseline.get('status')}，不能把它当作可信历史。",
        summary_en="The active scientific baseline is valid and fixed." if baseline_ok else f"The scientific baseline is {baseline.get('status')}; it cannot be treated as trusted history.",
        findings=[] if baseline_ok else [(str(baseline.get("status")), str(baseline.get("reason") or "baseline_invalid"))],
        refs=[str(baseline.get("pointer_path") or "")],
    ))
    drift_ok = not drift.get("requires_reconciliation")
    results.append(_result(
        "DG-02", "passed" if drift_ok else "failed", scope_digest=scope_digest, input_value=drift,
        summary_zh="候选变化仍然可由固定基线解释。" if drift_ok else "发现尚未对账的工作区变化，不能让修复操作把它吸收掉。",
        summary_en="Workspace state is explainable against the fixed baseline." if drift_ok else "Unreconciled workspace changes remain and cannot be absorbed by a repair operation.",
        findings=[] if drift_ok else [(str(item.get("path")), str(item.get("drift_kind"))) for item in (drift.get("changed_artifacts") or []) + (drift.get("added_artifacts") or []) + (drift.get("missing_artifacts") or [])],
    ))
    scope_ok = scope.get("status") == "passed"
    results.append(_result(
        "DG-03", "passed" if scope_ok else "failed", scope_digest=scope_digest, input_value=scope,
        summary_zh=f"预期 {scope.get('expected_count', 0)} 项对象，已核验 {scope.get('checked_count', 0)} 项。" if scope_ok else f"覆盖不完整：仍有 {scope.get('missing_count', 0)} 项对象未核验。",
        summary_en=f"Checked {scope.get('checked_count', 0)} of {scope.get('expected_count', 0)} expected objects." if scope_ok else f"Coverage is incomplete: {scope.get('missing_count', 0)} objects were not checked.",
        findings=[] if scope_ok else [(str(item.get("path") or item.get("locator")), str(item.get("reason"))) for item in scope.get("missing") or []],
    ))
    binding_ok = bindings.get("status") == "ready"
    binding_outcome: CheckOutcome = "passed" if binding_ok else "not_evaluated" if bindings.get("registry_status") == "missing" else "failed"
    results.append(_result(
        "DG-04", binding_outcome, scope_digest=scope_digest, input_value=bindings,
        summary_zh="证据绑定记录可读取且来源未漂移。" if binding_ok else "证据绑定尚未达到可认证状态。",
        summary_en="Evidence bindings are readable and their sources have not drifted." if binding_ok else "Evidence bindings are not yet certifiable.",
        findings=[] if binding_ok else [(str(item.get("receipt_id") or "registry"), str(item.get("reason") or "binding_incomplete")) for item in bindings.get("stale_receipts") or []],
        refs=[str(bindings.get("registry_path") or "")],
    ))
    surface_changed = [item for item in drift.get("changed_artifacts") or [] if artifact_role_for_path(str(item.get("path")))[0] in {"manuscript_source", "section_prose", "citation_repair"}]
    surface_outcome: CheckOutcome = "passed" if not any(item.get("semantic_changed") for item in surface_changed) else "failed"
    results.append(_result(
        "DG-05", surface_outcome, scope_digest=scope_digest, input_value=surface,
        summary_zh="未发现未处理的正文科学语义变化。" if surface_outcome == "passed" else "正文存在需要重新核验的科学语义变化。",
        summary_en="No unreviewed manuscript semantic change was detected." if surface_outcome == "passed" else "The manuscript contains a scientific semantic change requiring review.",
        findings=[] if surface_outcome == "passed" else [(str(item.get("path")), "manuscript_semantic_drift") for item in surface_changed],
        refs=[str(item.get("path")) for item in surface_changed],
    ))
    impact_ok = all(item.get("affected_stages") or item.get("drift_kind") in {"byte_only_drift", "unresolved_artifact"} for item in (drift.get("changed_artifacts") or []))
    results.append(_result(
        "DG-06", "passed" if impact_ok else "failed", scope_digest=scope_digest, input_value=drift.get("changed_artifacts"),
        summary_zh="变化影响范围具有依赖依据。" if impact_ok else "存在无法解释影响范围的变化。",
        summary_en="Change impact is backed by dependency classification." if impact_ok else "Some changes have no defensible dependency impact.",
    ))
    cycle_ok = not cycle or cycle.get("status") != "open" or cycle.get("reconciliation_status") == "reconciled"
    results.append(_result("DG-08", "passed" if cycle_ok else "failed", scope_digest=scope_digest, input_value=cycle or {}, summary_zh="确认对象与当前周期一致。" if cycle_ok else "当前修订周期仍有未完成对账。", summary_en="Confirmation identity matches the current cycle." if cycle_ok else "The current revision cycle still has unreconciled work."))
    ownership_ok, ownership_findings = _surface_sources_are_intact(root, surface)
    results.append(_result(
        "DG-09",
        "passed" if ownership_ok else "failed",
        scope_digest=scope_digest,
        input_value=surface.get("artifacts"),
        summary_zh="作者稿件来源均在项目内可读，内容身份与审计快照一致。" if ownership_ok else "作者稿件来源缺失、越界或在读取后发生变化。",
        summary_en="Author manuscript sources are readable in-project and match the audit snapshot." if ownership_ok else "An author manuscript source is missing, outside the project, or changed after inspection.",
        findings=ownership_findings,
        refs=[str(item.get("path")) for item in surface.get("artifacts") or [] if isinstance(item, dict) and item.get("path")],
    ))
    integrity_ok = baseline.get("status") == "valid" and scope_ok and not any(result.outcome == "error" for result in results)
    results.append(_result("DG-10", "passed" if integrity_ok else "failed", scope_digest=scope_digest, input_value={"baseline": baseline, "scope": scope}, summary_zh="没有把异常或漏检伪装成通过。" if integrity_ok else "存在完整性异常或漏检。", summary_en="No error or omission was disguised as a pass." if integrity_ok else "An integrity error or omission remains."))
    self_test = {}
    if self_test_report:
        try:
            self_test = json.loads(Path(self_test_report).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            self_test = {"status": "error"}
    self_test_ok = self_test.get("status") == "passed"
    results.append(_result(
        "DG-11", "passed" if self_test_ok else "error" if self_test_report else "not_evaluated",
        scope_digest=scope_digest, input_value=self_test or policy,
        summary_zh="治理自检的正常/反向用例均通过。" if self_test_ok else "需要运行治理自检入口验证正反用例。",
        summary_en="Positive and negative governance controls passed." if self_test_ok else "The governance self-test entry must verify positive and negative controls.",
        refs=[str(Path(self_test_report).resolve())] if self_test_report else [],
    ))
    provisional_eligibility = _action_eligibility_for(
        results,
        baseline_ok=baseline_ok,
        scope_ok=scope_ok,
        cycle=cycle,
        cycle_ok=cycle_ok,
    )
    eligibility_separated = provisional_eligibility.allow_edit and provisional_eligibility.allow_preview and (
        (
            bool(provisional_eligibility.blocking_finding_ids)
            and not provisional_eligibility.allow_promote
            and not provisional_eligibility.allow_close
            and not provisional_eligibility.allow_release
        )
        or (
            not provisional_eligibility.blocking_finding_ids
            and provisional_eligibility.allow_promote
            and provisional_eligibility.allow_close
            and provisional_eligibility.allow_release
        )
    )
    results.append(_result(
        "DG-07",
        "passed" if eligibility_separated else "failed",
        scope_digest=scope_digest,
        input_value=asdict(provisional_eligibility),
        summary_zh="编辑与预览可继续，晋升和发布资格按证据状态单独门控。" if eligibility_separated else "编辑、预览与证据晋升资格未正确分离。",
        summary_en="Editing and preview remain available while promotion and release follow evidence state." if eligibility_separated else "Editing, preview, and evidence promotion are not correctly separated.",
        findings=[] if eligibility_separated else [("action_eligibility", "permission_separation_invalid")],
    ))

    policy_ok = _policy_registry_is_complete(policy)
    check_set_ok = _result_set_is_complete(results)
    registry_findings = []
    if not policy_ok:
        registry_findings.append(("policy", "rule_registry_incomplete_or_ambiguous"))
    if not check_set_ok:
        registry_findings.append(("checks", "required_rule_result_missing_duplicate_or_unknown"))
    results.append(_result(
        "DG-12",
        "passed" if policy_ok and check_set_ok else "failed",
        scope_digest=scope_digest,
        input_value={"policy": policy, "emitted_rule_ids": [item.rule_id for item in results]},
        summary_zh="规则登记完整，且每条必需规则均产生唯一检查结果。" if policy_ok and check_set_ok else "规则登记或实际检查结果不完整，禁止按缺失项放行。",
        summary_en="The registry is complete and every required rule emitted exactly one result." if policy_ok and check_set_ok else "The registry or emitted rule results are incomplete; missing checks cannot pass.",
        findings=registry_findings,
    ))

    results.sort(key=lambda item: item.rule_id)
    eligibility = _action_eligibility_for(
        results,
        baseline_ok=baseline_ok,
        scope_ok=scope_ok,
        cycle=cycle,
        cycle_ok=cycle_ok,
    )
    report = {
        "schema_version": GOVERNANCE_SCHEMA,
        "policy_id": policy.get("policy_id"),
        "project_path": str(root),
        "purpose": purpose,
        "candidate_id": candidate_id,
        "baseline": baseline,
        "scope": scope,
        "drift": drift,
        "bindings": bindings,
        "manuscript_surface": surface,
        "revision_cycle": cycle,
        "checks": [_serialize(result) for result in results],
        "action_eligibility": asdict(eligibility) | {"blocking_finding_ids": list(eligibility.blocking_finding_ids)},
    }
    report["report_sha256"] = _hash(report)
    if html_output:
        from .governance_report import write_governance_html

        safe_target = _guard_governance_html_target(root, html_output, surface)
        report["human_review_html"] = write_governance_html(report, safe_target, language=language)
    return report


__all__ = ["ActionEligibility", "CheckOutcome", "GovernanceCheckResult", "GOVERNANCE_SCHEMA", "evaluate_governance", "load_governance_policy"]
