from __future__ import annotations

from types import SimpleNamespace

import pytest

from draftpaper_cli import core_evidence, data_feasibility, methods, result_validity
from draftpaper_cli.command_contracts import build_command_contracts
from draftpaper_cli.command_registry import COMMAND_SPECS, dispatch_registered_command
from draftpaper_cli.journal_profile import JournalProfileError, _fetch_text
from draftpaper_cli.mcp import service
from draftpaper_cli.plugin_candidates import PluginCandidateError, _read_registry_json
from draftpaper_cli.write_set_guard import BoundaryViolation, resolve_confined_path


HARD_GATE_NAMES = {
    "assess-core-evidence",
    "assess-data-quality",
    "assess-result-validity",
    "verify-methods",
}


def test_p0_hard_gates_have_handlers_and_non_success_exit_policies() -> None:
    for name in HARD_GATE_NAMES:
        spec = COMMAND_SPECS[name]
        assert spec.handler_module
        assert spec.handler_name
    assert spec.exit_policy in {"decision_pass", "quality_pass", "status_success"}


def test_command_contracts_report_no_p0_hard_gate_handler_issue() -> None:
    report = build_command_contracts()
    assert report["status"] == "passed"
    assert not any(
        any(token in issue for token in ("handler", "always_success"))
        and name in HARD_GATE_NAMES
        for name, issue in (item.split(":", 1) for item in report["issues"])
    )


@pytest.mark.parametrize(
    ("command", "module", "function", "payload", "expected_code"),
    [
        ("assess-core-evidence", core_evidence, "assess_core_evidence", {"decision": "blocked"}, 1),
        ("assess-result-validity", result_validity, "assess_result_validity", {"decision": "revise_required"}, 1),
        ("assess-data-quality", data_feasibility, "assess_data_quality", {"decision": "revise_required"}, 1),
        ("verify-methods", methods, "verify_methods", {"decision": "blocked"}, 1),
    ],
)
def test_p0_hard_gate_dispatch_returns_nonzero_for_nonpassing_payload(
    monkeypatch: pytest.MonkeyPatch,
    command: str,
    module: object,
    function: str,
    payload: dict[str, str],
    expected_code: int,
) -> None:
    monkeypatch.setattr(module, function, lambda **_kwargs: payload)
    args = SimpleNamespace(
        command=command,
        project="fixture",
        required_column=[],
        max_missing_ratio=0.2,
        primary_metric=None,
        minimum_value=None,
        method_command=None,
        output=None,
        input=None,
    )
    result, exit_code = dispatch_registered_command(args)
    assert result == payload
    assert exit_code == expected_code


def test_mcp_denies_private_locator_artifacts(tmp_path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    private = project / "data" / "external_data_locators.private.json"
    private.parent.mkdir()
    private.write_text('{"source_root":"C:/private"}', encoding="utf-8")

    result = service.artifact_get(str(project), "data/external_data_locators.private.json")

    assert result["status"] == "forbidden_artifact"
    assert result["reason_code"] == "private_locator"
    assert "C:/private" not in str(result)


def test_mcp_denies_private_json_and_credential_names(tmp_path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    for relative in ("review/report.private.json", "data/credentials.json"):
        path = project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")

        result = service.artifact_get(str(project), relative)

        assert result["status"] == "forbidden_artifact"


def test_completion_content_path_cannot_escape_root(tmp_path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    outside = tmp_path / "outside.tex"
    outside.write_text("private text", encoding="utf-8")

    with pytest.raises(BoundaryViolation):
        resolve_confined_path(root, "../outside.tex", must_exist=True)


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/metadata",
    "http://169.254.169.254/latest/meta-data",
    "file:///etc/passwd",
    "data:text/plain,secret",
])
def test_journal_fetch_rejects_unsafe_urls(url: str) -> None:
    with pytest.raises(JournalProfileError):
        _fetch_text(url)


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/registry.json",
    "file:///etc/passwd",
    "data:application/json,{}",
])
def test_skill_registry_rejects_unsafe_urls(url: str) -> None:
    with pytest.raises(PluginCandidateError):
        _read_registry_json(url)
