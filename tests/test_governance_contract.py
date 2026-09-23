from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

import draftpaper_cli.governance_contract as governance_contract
from draftpaper_cli.governance_contract import evaluate_governance, load_governance_policy
from draftpaper_cli.governance_report import write_governance_html
from draftpaper_cli.mcp import service
from draftpaper_cli.orchestrator import status_project
from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.revision_cycle import RevisionCycleError, begin_revision_cycle, commit_revision_candidate
from draftpaper_cli.scientific_baseline import create_scientific_baseline


def test_policy_has_twelve_stable_rules() -> None:
    policy = load_governance_policy()
    assert [item["rule_id"] for item in policy["rules"]] == [f"DG-{index:02d}" for index in range(1, 13)]


def test_governance_is_read_only_and_blocks_unverified_release(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="governance", field="astronomy").path
    create_scientific_baseline(project)
    before = sorted(path.relative_to(project).as_posix() for path in project.rglob("*") if path.is_file())
    report = evaluate_governance(project, purpose="final")
    after = sorted(path.relative_to(project).as_posix() for path in project.rglob("*") if path.is_file())
    assert before == after
    assert report["schema_version"] == "dpl.evidence_governance_report.v1"
    assert report["action_eligibility"]["allow_release"] is False


def test_governance_html_cannot_overwrite_author_owned_manuscript(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="protected manuscript", field="astronomy").path
    manuscript = project / "latex" / "main.tex"
    manuscript.parent.mkdir(parents=True, exist_ok=True)
    manuscript.write_text("\\begin{document}Author text.\\end{document}\n", encoding="utf-8")
    create_scientific_baseline(project)
    original = manuscript.read_bytes()

    with pytest.raises(ValueError, match="author-owned manuscript"):
        evaluate_governance(project, purpose="audit", html_output=str(manuscript))

    assert manuscript.read_bytes() == original


def test_governance_missing_rule_result_blocks_release(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = create_project(root=tmp_path / "project", idea="missing rule result", field="astronomy").path
    create_scientific_baseline(project)
    original_result = governance_contract._result

    def omit_scope_result(rule_id: str, *args: object, **kwargs: object) -> object:
        if rule_id == "DG-03":
            rule_id = "DG-99"
        return original_result(rule_id, *args, **kwargs)

    monkeypatch.setattr(governance_contract, "_result", omit_scope_result)
    report = evaluate_governance(project, purpose="final")

    checks = {item["rule_id"]: item for item in report["checks"]}
    assert checks["DG-12"]["outcome"] == "failed"
    assert report["action_eligibility"]["allow_release"] is False


def test_governance_checker_mapping_cannot_be_weakened(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = create_project(root=tmp_path / "project", idea="checker mapping", field="astronomy").path
    create_scientific_baseline(project)
    original_loader = governance_contract.load_governance_policy

    def weakened_registry() -> dict[str, object]:
        policy = original_loader()
        rules = [dict(item) for item in policy["rules"]]
        next(item for item in rules if item["rule_id"] == "DG-02")["checker"] = "always_pass"
        return policy | {"rules": rules}

    monkeypatch.setattr(governance_contract, "load_governance_policy", weakened_registry)
    report = evaluate_governance(project, purpose="final")

    checks = {item["rule_id"]: item for item in report["checks"]}
    assert checks["DG-12"]["outcome"] == "failed"
    assert report["action_eligibility"]["allow_release"] is False


def test_strict_commit_rejects_forged_unbound_receipt(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="commit", field="astronomy").path
    create_scientific_baseline(project)
    cycle = begin_revision_cycle(project, mode="author_edit")["revision_cycle"]
    with pytest.raises(RevisionCycleError):
        commit_revision_candidate(
            project,
            candidate_id="missing-candidate",
            expected_baseline_id=cycle["parent_baseline_id"],
            decision_receipt_id="missing",
        )
    receipt = project / "review" / "checkpoints" / "checkpoint-1" / "review_decision_receipt.json"
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text('{"receipt_id": "real-receipt", "decision_status": "user_confirmed"}\n', encoding="utf-8")
    with pytest.raises(RevisionCycleError):
        commit_revision_candidate(
            project,
            candidate_id="missing-candidate",
            expected_baseline_id=cycle["parent_baseline_id"],
            decision_receipt_id="real-receipt",
        )


def test_strict_commit_requires_applied_candidate_and_candidate_bound_user_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from draftpaper_cli import review_policy
    from draftpaper_cli.revision_cycle import apply_revision_reconciliation, prepare_revision_reconciliation

    project = create_project(root=tmp_path / "project", idea="commit", field="astronomy").path
    create_scientific_baseline(project)
    cycle = begin_revision_cycle(project, mode="author_edit")["revision_cycle"]
    prepared = prepare_revision_reconciliation(project)
    applied = apply_revision_reconciliation(
        project,
        reconciliation_id=prepared["reconciliation_id"],
        packet_hash=json.loads(Path(prepared["reconciliation_path"]).read_text(encoding="utf-8"))["packet_sha256"],
    )
    assert applied["reconciliation_status"] == "reconciled"
    candidate_packet_hash = json.loads(
        Path(prepared["reconciliation_path"]).read_text(encoding="utf-8")
    )["packet_sha256"]

    checkpoint_dir = project / "review" / "checkpoints" / "checkpoint-1"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    forged_dir = checkpoint_dir / "review_decision_receipts"
    forged_dir.mkdir(parents=True, exist_ok=True)
    forged_id = "forged-receipt"
    (forged_dir / f"{forged_id}.json").write_text(
        json.dumps({
            "schema_version": "dpl.review_decision_receipt.v2",
            "receipt_id": forged_id,
            "checkpoint_hash": "checkpoint-fixture-hash",
            "decision_status": "user_confirmed",
            "actor_type": "user",
            "authority_source": {"policy": "explicit_user_command"},
            "receipt_sha256": "not-a-valid-receipt-hash",
        }),
        encoding="utf-8",
    )
    with pytest.raises(RevisionCycleError, match="decision receipt"):
        commit_revision_candidate(
            project,
            candidate_id=json.loads(Path(prepared["reconciliation_path"]).read_text(encoding="utf-8"))["packet_sha256"],
            expected_baseline_id=cycle["parent_baseline_id"],
            decision_receipt_id=forged_id,
        )

    summary_path = checkpoint_dir / "stage_summary.json"
    summary_path.write_text(
        json.dumps({
            "stage_summary_sha256": "fixture-summary-sha256",
            "stage": "core_evidence",
            "revision_cycle_id": cycle["revision_cycle_id"],
            "revision_candidate_sha256": candidate_packet_hash,
            "baseline_refs": {"active_baseline_id": cycle["parent_baseline_id"]},
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(review_policy, "_checkpoint_summary_path", lambda *_args: summary_path)
    monkeypatch.setattr(
        review_policy,
        "evaluate_checkpoint_authority",
        lambda *_args, **_kwargs: {
            "review_state": "confirmable",
            "policy_sha256": "fixture-policy-sha256",
            "risk_class": "C3",
            "stage": "core_evidence",
            "eligibility_checks": [],
        },
    )
    receipt = review_policy.record_user_checkpoint_confirmation(
        project,
        checkpoint_hash="checkpoint-fixture-hash",
        actor_id="reviewer",
    )["receipt"]
    assert receipt["revision_candidate_sha256"] == candidate_packet_hash

    with pytest.raises(RevisionCycleError, match="candidate ID"):
        commit_revision_candidate(
            project,
            candidate_id=cycle["revision_cycle_id"],
            expected_baseline_id=cycle["parent_baseline_id"],
            decision_receipt_id=receipt["receipt_id"],
        )
    first_candidate = receipt["revision_candidate_sha256"]
    next_prepared = prepare_revision_reconciliation(project)
    apply_revision_reconciliation(
        project,
        reconciliation_id=next_prepared["reconciliation_id"],
        packet_hash=json.loads(Path(next_prepared["reconciliation_path"]).read_text(encoding="utf-8"))["packet_sha256"],
    )
    with pytest.raises(RevisionCycleError, match="candidate"):
        commit_revision_candidate(
            project,
            candidate_id=first_candidate,
            expected_baseline_id=cycle["parent_baseline_id"],
            decision_receipt_id=receipt["receipt_id"],
        )
    latest_candidate_hash = json.loads(
        Path(next_prepared["reconciliation_path"]).read_text(encoding="utf-8")
    )["packet_sha256"]
    summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
    summary_payload["revision_candidate_sha256"] = latest_candidate_hash
    summary_payload["stage_summary_sha256"] = "fixture-summary-sha256-next"
    summary_path.write_text(json.dumps(summary_payload), encoding="utf-8")
    receipt = review_policy.record_user_checkpoint_confirmation(
        project,
        checkpoint_hash="checkpoint-fixture-hash",
        actor_id="reviewer",
    )["receipt"]
    result = commit_revision_candidate(
        project,
        candidate_id=receipt["revision_candidate_sha256"],
        expected_baseline_id=cycle["parent_baseline_id"],
        decision_receipt_id=receipt["receipt_id"],
    )
    assert result["status"] == "committed"
    assert result["release_eligible"] is True


def test_candidate_hash_is_shown_in_bilingual_checkpoint_decision_html(tmp_path: Path) -> None:
    from draftpaper_cli.checkpoint_html import render_checkpoint_html

    project = create_project(root=tmp_path / "project", idea="candidate html", field="astronomy").path
    output_dir = project / "review" / "checkpoints" / "fixture"
    output_dir.mkdir(parents=True, exist_ok=True)
    candidate_hash = "a" * 64
    summary = {
        "schema_version": "dpl.checkpoint_summary.v5",
        "review_state": "confirmable",
        "checkpoint_title_zh": "修订候选确认",
        "checkpoint_title_en": "Revision candidate confirmation",
        "decision_brief": {},
        "revision_candidate_sha256": candidate_hash,
        "confirmation_contract": {"confirmation_command_allowed": False},
    }
    zh_html = render_checkpoint_html(project, output_dir, summary, {}, locale="zh-CN")
    en_html = render_checkpoint_html(project, output_dir, summary, {}, locale="en")
    assert "本次修订候选包 SHA-256" in zh_html
    assert "Revision candidate packet SHA-256" in en_html
    assert zh_html.count(candidate_hash) == 1
    assert en_html.count(candidate_hash) == 1


def test_scientific_candidate_requires_and_consumes_its_exact_user_decision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from draftpaper_cli import review_policy
    from draftpaper_cli.revision_cycle import apply_revision_reconciliation, prepare_revision_reconciliation
    from draftpaper_cli.passport import refresh_project_passport

    project = create_project(root=tmp_path / "project", idea="scientific revision", field="astronomy").path
    method = project / "methods" / "run_analysis.py"
    method.write_text("def statistic():\n    return 0.81\n", encoding="utf-8")
    refresh_project_passport(project, event="register_method_fixture")
    create_scientific_baseline(project)
    cycle = begin_revision_cycle(project, mode="author_edit")["revision_cycle"]
    method.write_text("def statistic():\n    return 0.93\n", encoding="utf-8")

    prepared = prepare_revision_reconciliation(project)
    packet = json.loads(Path(prepared["reconciliation_path"]).read_text(encoding="utf-8"))
    assert prepared["reconciliation_status"] == "awaiting_decision"
    first_apply = apply_revision_reconciliation(
        project,
        reconciliation_id=prepared["reconciliation_id"],
        packet_hash=packet["packet_sha256"],
    )
    assert first_apply["reconciliation_status"] == "awaiting_decision"

    checkpoint_dir = project / "review" / "checkpoints" / "scientific-candidate"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    summary_path = checkpoint_dir / "stage_summary.json"
    summary_path.write_text(
        json.dumps({
            "stage_summary_sha256": "scientific-candidate-summary",
            "stage": "core_evidence",
            "revision_cycle_id": cycle["revision_cycle_id"],
            "revision_candidate_sha256": packet["packet_sha256"],
            "baseline_refs": {"active_baseline_id": cycle["parent_baseline_id"]},
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(review_policy, "_checkpoint_summary_path", lambda *_args: summary_path)
    monkeypatch.setattr(
        review_policy,
        "evaluate_checkpoint_authority",
        lambda *_args, **_kwargs: {
            "review_state": "confirmable",
            "policy_sha256": "fixture-policy-sha256",
            "risk_class": "C3",
            "stage": "core_evidence",
            "eligibility_checks": [],
        },
    )
    decision_receipt = review_policy.record_user_checkpoint_confirmation(
        project,
        checkpoint_hash="scientific-candidate-checkpoint",
        actor_id="reviewer",
    )["receipt"]
    assert decision_receipt["revision_candidate_sha256"] == packet["packet_sha256"]

    applied = apply_revision_reconciliation(
        project,
        reconciliation_id=prepared["reconciliation_id"],
        packet_hash=packet["packet_sha256"],
        decision_receipt_id=decision_receipt["receipt_id"],
    )
    assert applied["reconciliation_status"] == "reconciled"
    committed = commit_revision_candidate(
        project,
        candidate_id=packet["packet_sha256"],
        expected_baseline_id=cycle["parent_baseline_id"],
        decision_receipt_id=decision_receipt["receipt_id"],
    )
    assert committed["status"] == "committed"


def test_governance_html_is_bilingual_and_contains_real_paths(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="html", field="astronomy").path
    create_scientific_baseline(project)
    report = evaluate_governance(project, purpose="audit")
    zh = tmp_path / "governance.zh-CN.html"
    en = tmp_path / "governance.en.html"
    write_governance_html(report, zh, language="zh-CN")
    write_governance_html(report, en, language="en")
    assert "证据治理与论文漂移审计" in zh.read_text(encoding="utf-8")
    assert "Evidence governance and manuscript drift audit" in en.read_text(encoding="utf-8")
    assert str(project) in zh.read_text(encoding="utf-8")


def test_governance_html_renders_false_eligibility_as_an_explicit_denial(tmp_path: Path) -> None:
    report = {
        "purpose": "audit",
        "project_path": "C:/project",
        "baseline": {"status": "valid"},
        "scope": {"checked_count": 2, "expected_count": 3},
        "drift": {},
        "checks": [],
        "action_eligibility": {
            "allow_edit": True,
            "allow_preview": True,
            "allow_promote": False,
            "allow_close": False,
            "allow_release": False,
            "blocking_finding_ids": ["DG-03"],
        },
        "report_sha256": "abc",
    }
    zh = tmp_path / "governance.zh-CN.html"
    en = tmp_path / "governance.en.html"

    write_governance_html(report, zh, language="zh-CN")
    write_governance_html(report, en, language="en")

    zh_html = zh.read_text(encoding="utf-8")
    en_html = en.read_text(encoding="utf-8")
    assert "\u5141\u8bb8\u53d1\u5e03</b>: \u5426" in zh_html
    assert "\u5141\u8bb8\u7ed3\u6848</b>: \u5426" in zh_html
    assert "Allow release</b>: No" in en_html
    assert "Allow close</b>: No" in en_html


def test_status_uses_shared_governance_release_gate(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="status gate", field="astronomy").path
    create_scientific_baseline(project)

    status = status_project(project)

    assert status["governance"]["schema_version"] == "dpl.evidence_governance_report.v1"
    assert status["release_eligible"] is False
    assert status["release_eligible"] is status["governance"]["action_eligibility"]["allow_release"]


def test_cli_and_mcp_governance_return_the_same_scientific_decision(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="entrypoint parity", field="astronomy").path
    create_scientific_baseline(project)
    command = [
        sys.executable,
        "-m",
        "draftpaper_cli.cli",
        "audit-evidence-governance",
        "--project",
        str(project),
        "--purpose",
        "audit",
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr
    cli_payload = json.loads(completed.stdout.splitlines()[-1])

    mcp_result = service.execute_command(
        str(project),
        "audit-evidence-governance",
        json.dumps({"purpose": "audit"}),
    )
    assert mcp_result["status"] == "completed"
    mcp_payload = mcp_result["scientific_result"]
    assert mcp_payload["action_eligibility"]["allow_release"] == cli_payload["action_eligibility"]["allow_release"]
    assert [item["outcome"] for item in mcp_payload["checks"]] == [item["outcome"] for item in cli_payload["checks"]]


def test_mcp_cli_subprocess_pins_the_imported_package_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = create_project(root=tmp_path / "project", idea="package root", field="astronomy").path
    captured: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured["env"] = kwargs["env"]
        return subprocess.CompletedProcess(command, 0, '{"status":"passed"}\n', "")

    monkeypatch.setattr(service.subprocess, "run", fake_run)
    monkeypatch.setenv("DRAFTPAPER_TEST_SECRET", "must-not-be-forwarded")

    result = service.execute_command(str(project), "audit-evidence-governance", json.dumps({"purpose": "audit"}))

    child_env = captured["env"]
    assert isinstance(child_env, dict)
    python_paths = str(child_env.get("PYTHONPATH", "")).split(__import__("os").pathsep)
    assert str(Path(service.__file__).resolve().parents[2]) in python_paths
    assert child_env.get("DRAFTPAPER_TEST_SECRET") is None
    assert result["status"] == "completed"


def test_governance_self_test_runs_from_an_external_working_directory(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[1]
    script = repository / "tools" / "verify_evidence_governance.py"

    completed = subprocess.run(
        [sys.executable, str(script)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["status"] == "passed"
    assert len(report["controls"]) == 18
