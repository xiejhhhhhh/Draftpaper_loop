from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from draftpaper_cli.claim_contract import apply_result_downgrade
from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.result_rescue import prepare_result_rescue
from draftpaper_cli.result_support import assess_result_support


def _prepare_failed_checkpoint(tmp_path):
    project = create_project(root=tmp_path, idea="Transactional Result Support", field="machine learning").path
    (project / "results" / "result_validity_report.json").write_text(
        json.dumps({"decision": "pass", "evidence_strength": "meets_threshold"}), encoding="utf-8"
    )
    (project / "results" / "result_manifest.yaml").write_text(
        json.dumps({"figures": [], "tables": []}), encoding="utf-8"
    )
    (project / "research_plan" / "claim_contract.json").write_text(
        json.dumps({"claims": [{
            "claim_id": "claim-model-improvement",
            "planned_claim": "The proposed model improves performance over the baseline.",
            "active_claim": "The proposed model improves performance over the baseline.",
            "active_strength": "strong",
        }]}),
        encoding="utf-8",
    )
    (project / "methods" / "run_manifest.yaml").write_text(
        json.dumps({
            "status": "success",
            "run_id": "run-current",
            "metrics": {"baseline_f1": 0.9, "proposed_f1": 0.8},
        }),
        encoding="utf-8",
    )
    assessed = assess_result_support(project)
    assert assessed["decision"] == "route_decision_required"
    return project, assessed["checkpoint_sha256"]


def test_downgrade_rolls_back_contract_freeze_stale_state_when_receipt_marker_fails(tmp_path, monkeypatch) -> None:
    import draftpaper_cli.claim_contract as module

    project, checkpoint_hash = _prepare_failed_checkpoint(tmp_path)
    before = {
        "project": (project / "project.json").read_bytes(),
        "contract": (project / "research_plan" / "claim_contract.json").read_bytes(),
        "support": (project / "results" / "result_support_checkpoint.json").read_bytes(),
    }

    def fail_receipt(*_args, **_kwargs):
        raise RuntimeError("injected route receipt failure")

    monkeypatch.setattr(module, "bind_result_route_receipt", fail_receipt)

    with pytest.raises(RuntimeError, match="injected route receipt failure"):
        apply_result_downgrade(project, checkpoint_hash=checkpoint_hash)

    assert (project / "project.json").read_bytes() == before["project"]
    assert (project / "research_plan" / "claim_contract.json").read_bytes() == before["contract"]
    assert (project / "results" / "result_support_checkpoint.json").read_bytes() == before["support"]
    assert not (project / "research_plan" / "claim_downgrade_decision.json").exists()
    assert not (project / "results" / "result_evidence_freeze.json").exists()
    assert list((project / "results" / "evidence_snapshots").glob("result_freeze_*.json")) == []


def test_rescue_rolls_back_snapshot_plan_and_stale_state_when_receipt_marker_fails(tmp_path, monkeypatch) -> None:
    import draftpaper_cli.result_rescue as module

    project, checkpoint_hash = _prepare_failed_checkpoint(tmp_path)
    promoted = project / "results" / "promoted_evidence_snapshot.json"
    promoted.write_text(json.dumps({"snapshot_id": "snapshot-current", "artifacts": {}}), encoding="utf-8")
    # The promoted snapshot is a Result Support input boundary only after a fresh assessment.
    assessed = assess_result_support(project)
    checkpoint_hash = assessed["checkpoint_sha256"]
    before = {
        "project": (project / "project.json").read_bytes(),
        "support": (project / "results" / "result_support_checkpoint.json").read_bytes(),
        "snapshot": promoted.read_bytes(),
    }

    def fail_receipt(*_args, **_kwargs):
        raise RuntimeError("injected route receipt failure")

    monkeypatch.setattr(module, "bind_result_route_receipt", fail_receipt)

    with pytest.raises(RuntimeError, match="injected route receipt failure"):
        prepare_result_rescue(project, checkpoint_hash=checkpoint_hash)

    assert (project / "project.json").read_bytes() == before["project"]
    assert (project / "results" / "result_support_checkpoint.json").read_bytes() == before["support"]
    assert promoted.read_bytes() == before["snapshot"]
    assert not (project / "review" / "result_rescue_plan.json").exists()
    assert not (project / "results" / "evidence_snapshot_reopen_report.json").exists()
    assert not (project / "results" / "evidence_snapshots" / "snapshot-current.json").exists()


def test_concurrent_same_route_selection_is_serialized_and_idempotent(tmp_path) -> None:
    project, checkpoint_hash = _prepare_failed_checkpoint(tmp_path)

    def apply_once(_index):
        return apply_result_downgrade(project, checkpoint_hash=checkpoint_hash)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(apply_once, range(2)))

    assert sorted(item["status"] for item in results) == ["already_applied", "applied"]
    support = json.loads((project / "results" / "result_support_checkpoint.json").read_text(encoding="utf-8"))
    contract = json.loads((project / "research_plan" / "claim_contract.json").read_text(encoding="utf-8"))
    assert support["selected_route"] == "downgrade_research_claim"
    assert support["route_receipt"]["status"] == "applied"
    assert contract["claims"][0]["pre_downgrade_claim"] == "The proposed model improves performance over the baseline."


def test_checkpoint_reassessment_waits_for_inflight_route_transaction(tmp_path, monkeypatch) -> None:
    import draftpaper_cli.claim_contract as module

    project, checkpoint_hash = _prepare_failed_checkpoint(tmp_path)
    entered = threading.Event()
    release = threading.Event()
    real_preflight = module.result_route_preflight

    def paused_preflight(*args, **kwargs):
        result = real_preflight(*args, **kwargs)
        entered.set()
        assert release.wait(timeout=5)
        return result

    monkeypatch.setattr(module, "result_route_preflight", paused_preflight)
    with ThreadPoolExecutor(max_workers=2) as executor:
        route_future = executor.submit(apply_result_downgrade, project, checkpoint_hash=checkpoint_hash)
        assert entered.wait(timeout=5)
        assess_future = executor.submit(assess_result_support, project)
        time.sleep(0.2)
        assert assess_future.done() is False
        release.set()
        assert route_future.result(timeout=10)["status"] == "applied"
        reassessed = assess_future.result(timeout=10)

    assert reassessed["decision"] == "pass"
