from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from draftpaper_cli.orchestrator import status_project
from draftpaper_cli.passport import refresh_project_passport
from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.scientific_baseline import create_scientific_baseline
from draftpaper_cli.revision_cycle import (
    apply_revision_reconciliation,
    begin_revision_cycle,
    close_revision_cycle,
    load_active_revision_cycle,
    prepare_revision_reconciliation,
    RevisionCycleError,
    set_revision_mode,
)


def test_author_edit_mode_pauses_upstream_without_clearing_stale_facts(tmp_path: Path) -> None:
    project = create_project(root=tmp_path, idea="Deferred revision", field="astronomy").path
    target = project / "methods" / "methods.tex"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("def run():\n    return 1\n", encoding="utf-8")
    refresh_project_passport(project, event="register_revision_fixture")
    cycle = begin_revision_cycle(project, reason="syntax repair", mode="author_edit")
    assert cycle["revision_cycle"]["mode"] == "author_edit"
    target.write_text(target.read_text(encoding="utf-8") + "\nCandidate wording.\n", encoding="utf-8")

    status = status_project(project)
    assert status["pipeline_state"] == "author_edit_paused"
    assert status["automatic_upstream"] is False
    assert status["awaiting_checkpoint"] is None
    assert status["workflow_gate"] == "revision_reconciliation_pending"
    assert status["release_eligible"] is False
    assert status["next_action"]["command"] == "prepare-revision-reconciliation"

    prepared = prepare_revision_reconciliation(project)
    assert prepared["release_eligible"] is False
    assert Path(prepared["summary_html"]).is_file()
    assert prepared["draft_generation"] if "draft_generation" in prepared else prepared["generation"]


def test_reconciliation_preview_provides_bilingual_human_readable_paths(tmp_path: Path) -> None:
    project = create_project(root=tmp_path, idea="Bilingual reconciliation", field="astronomy").path
    target = project / "methods" / "run_analysis.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("def run():\n    return 1\n", encoding="utf-8")
    refresh_project_passport(project, event="register_bilingual_fixture")
    begin_revision_cycle(project, reason="bilingual review", mode="author_edit")
    target.write_text("def run():\n    return 2\n", encoding="utf-8")

    prepared = prepare_revision_reconciliation(project)
    zh = Path(prepared["summary_html.zh-CN"])
    en = Path(prepared["summary_html.en"])
    assert zh.is_file()
    assert en.is_file()
    assert prepared["human_review"]["zh-CN"] == str(zh.resolve())
    assert prepared["human_review"]["en"] == str(en.resolve())
    for path in (zh, en):
        content = path.read_text(encoding="utf-8")
        assert prepared["reconciliation_id"] in content
        assert "methods/run_analysis.py" in content
        assert "release_eligible" in content
        assert "reconciliation pending" in content.lower()
        assert "Candidate artifacts observed" in content or "本候选版本发现的产物" in content
        assert "What this generation contains" in content or "本候选版本包含的内容" in content


def test_scientific_change_cannot_be_marked_reconciled_by_mode_switch(tmp_path: Path) -> None:
    project = create_project(root=tmp_path, idea="Deferred evidence", field="astronomy").path
    target = project / "methods" / "run_analysis.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("def run():\n    return 1\n", encoding="utf-8")
    refresh_project_passport(project, event="register_revision_fixture")
    begin_revision_cycle(project, reason="author edit", mode="author_edit")
    target.write_text("def run():\n    return 2\n", encoding="utf-8")
    prepared = prepare_revision_reconciliation(project)
    packet = Path(prepared["reconciliation_path"]).read_text(encoding="utf-8")
    import json

    packet_payload = json.loads(packet)
    result = apply_revision_reconciliation(
        project,
        reconciliation_id=prepared["reconciliation_id"],
        packet_hash=packet_payload["packet_sha256"],
    )
    assert result["status"] == "awaiting_scientific_decision"
    assert result["release_eligible"] is False
    assert load_active_revision_cycle(project)["reconciliation_status"] == "awaiting_decision"


def test_switching_back_to_live_preserves_pending_reconciliation(tmp_path: Path) -> None:
    project = create_project(root=tmp_path, idea="Mode switch", field="astronomy").path
    target = project / "methods" / "run_analysis.py"
    target.write_text("def run():\n    return 1\n", encoding="utf-8")
    refresh_project_passport(project, event="register_mode_switch_fixture")
    begin_revision_cycle(project, mode="author_edit")
    target.write_text("def run():\n    return 2\n", encoding="utf-8")
    prepared = prepare_revision_reconciliation(project)
    assert prepared["reconciliation_status"] == "awaiting_decision"
    switched = set_revision_mode(project, mode="live")
    assert switched["automatic_upstream"] is True
    assert load_active_revision_cycle(project)["reconciliation_status"] == "awaiting_decision"


def test_unreconciled_candidate_cannot_close_but_can_be_rejected(tmp_path: Path) -> None:
    project = create_project(root=tmp_path, idea="Close gate", field="astronomy").path
    target = project / "methods" / "run_analysis.py"
    target.write_text("def run():\n    return 1\n", encoding="utf-8")
    refresh_project_passport(project, event="register_revision_fixture")
    begin_revision_cycle(project, reason="scientific edit", mode="author_edit")
    target.write_text("def run():\n    return 2\n", encoding="utf-8")
    prepared = prepare_revision_reconciliation(project)
    assert prepared["reconciliation_status"] == "awaiting_decision"

    with pytest.raises(RevisionCycleError, match="unreconciled"):
        close_revision_cycle(project, decision_receipt_id="premature-close")

    rejected = close_revision_cycle(project, decision_receipt_id="reject-candidate", status="rejected")
    assert rejected["status"] == "rejected"
    assert load_active_revision_cycle(project)["candidate_baseline_id"] is None


def test_reconciled_author_edit_cannot_bypass_candidate_commit_via_legacy_close(tmp_path: Path) -> None:
    project = create_project(root=tmp_path, idea="Author-edit close bypass", field="astronomy").path
    create_scientific_baseline(project)
    begin_revision_cycle(project, mode="author_edit")
    prepared = prepare_revision_reconciliation(project)
    packet = json.loads(Path(prepared["reconciliation_path"]).read_text(encoding="utf-8"))
    apply_revision_reconciliation(
        project,
        reconciliation_id=prepared["reconciliation_id"],
        packet_hash=packet["packet_sha256"],
    )

    with pytest.raises(RevisionCycleError, match="commit-revision-candidate"):
        close_revision_cycle(project, decision_receipt_id="unverified", status="closed")


def test_old_reconciliation_packet_cannot_apply_after_candidate_changes(tmp_path: Path) -> None:
    project = create_project(root=tmp_path, idea="Candidate generation", field="astronomy").path
    target = project / "methods" / "run_analysis.py"
    target.write_text("def run():\n    return 1\n", encoding="utf-8")
    refresh_project_passport(project, event="register_revision_fixture")
    begin_revision_cycle(project, reason="deferred edit", mode="author_edit")
    target.write_text("def run():\n    return 2\n", encoding="utf-8")
    prepared = prepare_revision_reconciliation(project)
    packet = json.loads(Path(prepared["reconciliation_path"]).read_text(encoding="utf-8"))

    target.write_text("def run():\n    return 3\n", encoding="utf-8")
    with pytest.raises(RevisionCycleError, match="candidate"):
        apply_revision_reconciliation(
            project,
            reconciliation_id=prepared["reconciliation_id"],
            packet_hash=packet["packet_sha256"],
        )


def test_author_edit_allows_scoped_agent_edits_after_external_drift(tmp_path: Path) -> None:
    project = create_project(root=tmp_path, idea="Agent deferred editing", field="astronomy").path
    target = project / "methods" / "methods.tex"
    target.write_text("Initial method text.\n", encoding="utf-8")
    refresh_project_passport(project, event="register_agent_edit_fixture")
    begin_revision_cycle(project, reason="deferred author edit", mode="author_edit")

    # Simulate an editor save that is already outside the managed transaction.
    target.write_text("User-edited method text.\n", encoding="utf-8")
    content_file = project / "candidate_methods.tex"
    content_file.write_text("Agent-edited candidate method text.\n", encoding="utf-8")

    begin = subprocess.run(
        [
            sys.executable,
            "-m",
            "draftpaper_cli.cli",
            "begin-managed-change",
            "--project",
            str(project),
            "--intent",
            "candidate wording refinement",
            "--change-class",
            "prose_only",
            "--path",
            "methods/methods.tex",
            "--content-file",
            str(content_file),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert begin.returncode == 0, begin.stderr
    packet = json.loads(begin.stdout)["packet"]

    applied = subprocess.run(
        [
            sys.executable,
            "-m",
            "draftpaper_cli.cli",
            "apply-managed-change",
            "--project",
            str(project),
            "--packet-id",
            packet["packet_id"],
            "--packet-hash",
            packet["packet_sha256"],
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert applied.returncode == 0, applied.stderr
    assert target.read_text(encoding="utf-8") == "Agent-edited candidate method text.\n"
    status = status_project(project)
    assert status["pipeline_state"] == "author_edit_paused"
    assert status["release_eligible"] is False
    assert status["drift"]["hard_reconciliation_required"] is True
