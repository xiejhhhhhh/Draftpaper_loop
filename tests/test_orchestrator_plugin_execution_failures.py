from __future__ import annotations

import hashlib
import json

import pytest

from draftpaper_cli.orchestrator import _plugin_execution_failures


def _failure(
    event_id: str,
    *,
    requirement_id: str = "method:figure-a:spatial-bootstrap",
    plugin_id: str = "project_local:spatial_bootstrap",
    generated_at: str = "2026-09-20T19:05:21Z",
) -> dict[str, object]:
    return {
        "event_id": event_id,
        "generated_at": generated_at,
        "requirement_id": requirement_id,
        "plugin_id": plugin_id,
        "status": "execution_failed",
    }


def _project_result(
    event_id: str,
    *,
    requirement_id: str = "method:figure-a:spatial-bootstrap",
    plugin_id: str = "project_local:spatial_bootstrap",
    generated_at: str = "2026-09-20T19:16:51Z",
    **overrides: object,
) -> dict[str, object]:
    event: dict[str, object] = {
        "event_id": event_id,
        "generated_at": generated_at,
        "requirement_id": requirement_id,
        "plugin_id": plugin_id,
        "status": "project_executed",
        "scientific_evidence_status": "project_result",
        "validation_level": "project_asset_audited",
        "parameters": {"verification_output_count": 1},
        "output_hashes": {"results/figure.csv": hashlib.sha256(b"verified").hexdigest()},
    }
    event.update(overrides)
    return event


def _append_events(project, relative: str, events: list[dict[str, object]]) -> None:
    path = project / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        for event in events:
            stream.write(json.dumps(event) + "\n")


def test_later_verified_project_result_resolves_failure_for_same_requirement_and_plugin(tmp_path) -> None:
    output = tmp_path / "results" / "figure.csv"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"verified")
    success = _project_result(
        "project-run",
        output_hashes={"results/figure.csv": hashlib.sha256(output.read_bytes()).hexdigest()},
    )
    _append_events(tmp_path, "methods/plugin_execution_ledger.jsonl", [_failure("old-failure"), success])

    assert _plugin_execution_failures(tmp_path) == []


@pytest.mark.parametrize(
    "success_overrides",
    [
        {"requirement_id": "method:figure-b:spatial-bootstrap"},
        {"plugin_id": "project_local:other_plugin"},
    ],
    ids=["different-requirement", "different-plugin"],
)
def test_project_result_for_another_binding_does_not_resolve_failure(tmp_path, success_overrides) -> None:
    failure = _failure("old-failure")
    success = _project_result("unrelated-success", **success_overrides)
    _append_events(tmp_path, "methods/plugin_execution_ledger.jsonl", [failure, success])

    assert _plugin_execution_failures(tmp_path) == [failure]


def test_newer_failure_after_project_result_remains_active(tmp_path) -> None:
    old_failure = _failure("old-failure")
    success = _project_result("project-run")
    new_failure = _failure("new-failure", generated_at="2026-09-20T19:20:00Z")
    _append_events(tmp_path, "methods/plugin_execution_ledger.jsonl", [old_failure, success, new_failure])

    assert _plugin_execution_failures(tmp_path) == [new_failure]


@pytest.mark.parametrize(
    "success_overrides",
    [
        {"status": "fixture_executed", "scientific_evidence_status": "fixture_only_not_project_result"},
        {"scientific_evidence_status": "fixture_only_not_project_result"},
        {"output_hashes": {}},
        {"output_hashes": {"results/figure.csv": "not-a-sha256"}},
        {"validation_level": "fixture_runnable"},
    ],
    ids=["fixture-execution", "non-project-evidence", "no-outputs", "invalid-output-hash", "unvalidated-project-local"],
)
def test_unverified_or_malformed_project_event_does_not_resolve_failure(tmp_path, success_overrides) -> None:
    failure = _failure("old-failure")
    success = _project_result("unverified-success", **success_overrides)
    _append_events(tmp_path, "methods/plugin_execution_ledger.jsonl", [failure, success])

    assert _plugin_execution_failures(tmp_path) == [failure]


def test_success_with_same_timestamp_does_not_supersede_failure(tmp_path) -> None:
    failure = _failure("old-failure", generated_at="2026-09-20T19:05:21Z")
    success = _project_result("same-time-success", generated_at="2026-09-20T19:05:21Z")
    _append_events(tmp_path, "methods/plugin_execution_ledger.jsonl", [failure, success])

    assert _plugin_execution_failures(tmp_path) == [failure]
