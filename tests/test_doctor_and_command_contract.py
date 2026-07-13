from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from draftpaper_cli.cli import build_parser
from draftpaper_cli.command_registry import COMMAND_SPECS
from draftpaper_cli.doctor import doctor_project, verify_next_action
from draftpaper_cli.project_scaffold import create_project


def _hash_tree(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_every_cli_parser_has_exactly_one_command_contract() -> None:
    parser = build_parser()
    subparsers = next(action for action in parser._actions if hasattr(action, "choices") and action.choices)
    assert set(subparsers.choices) == set(COMMAND_SPECS)
    assert len(COMMAND_SPECS) >= 170
    assert all(spec.coordinator and spec.formal_stage for spec in COMMAND_SPECS.values())


def test_doctor_detects_source_checkout_loaded_from_another_installation(tmp_path: Path) -> None:
    from draftpaper_cli.doctor import _runtime_source_diagnostics

    checkout = tmp_path / "checkout"
    (checkout / "draftpaper_cli").mkdir(parents=True)
    (checkout / "pyproject.toml").write_text('[project]\nname = "draftpaper-cli"\n', encoding="utf-8")
    installed = tmp_path / "site-packages" / "draftpaper_cli" / "doctor.py"
    installed.parent.mkdir(parents=True)
    installed.write_text("# installed copy\n", encoding="utf-8")

    report = _runtime_source_diagnostics(imported_module_file=installed, working_directory=checkout)

    assert report["source_kind"] == "installed_package"
    assert report["working_checkout_root"] == str(checkout.resolve())
    assert report["source_checkout_mismatch"] is True


def test_doctor_is_deterministic_and_strictly_read_only(tmp_path: Path) -> None:
    project = create_project(root=tmp_path, idea="Doctor determinism", field="engineering").path
    before = _hash_tree(project)

    first = doctor_project(project)
    second = doctor_project(project)

    assert first == second
    assert first["status"] == "passed"
    assert first["next_action_verification"]["status"] == "passed"
    assert _hash_tree(project) == before


def test_doctor_token_budget_uses_latest_writing_packet_per_task(tmp_path: Path) -> None:
    project = create_project(root=tmp_path, idea="Token receipt history", field="engineering").path
    rows = []
    for index in range(10):
        rows.append({
            "task_id": "prepare-section-writing:results",
            "stage": "results",
            "recorded_at": f"2026-07-12T00:{index:02d}:00Z",
            "estimated_input_tokens": 20_000,
        })
    rows.extend([
        {
            "task_id": f"prepare-section-writing:{stage}",
            "stage": stage,
            "recorded_at": "2026-07-13T00:00:00Z",
            "estimated_input_tokens": 5_000,
        }
        for stage in ("results", "introduction", "data", "methods", "discussion")
    ])
    (project / "token_ledger.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )

    report = doctor_project(project)

    assert report["token_ledger"]["lifetime_input_tokens"] == 225_000
    assert report["token_ledger"]["active_manuscript_input_tokens"] == 25_000
    assert not any(item["category"] == "token_budget" for item in report["findings"])


def test_doctor_token_budget_warns_for_current_packets(tmp_path: Path) -> None:
    project = create_project(root=tmp_path, idea="Oversized current packets", field="engineering").path
    rows = [
        {
            "task_id": f"prepare-section-writing:{stage}",
            "stage": stage,
            "recorded_at": "2026-07-13T00:00:00Z",
            "estimated_input_tokens": 16_000,
        }
        for stage in ("results", "introduction", "data", "methods", "discussion")
    ]
    (project / "token_ledger.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )

    report = doctor_project(project)

    assert report["token_ledger"]["active_manuscript_input_tokens"] == 80_000
    assert any(item["category"] == "token_budget" for item in report["findings"])


def test_next_action_verifier_rejects_missing_required_cli_argument(tmp_path: Path) -> None:
    project = create_project(root=tmp_path, idea="Invalid recommendation", field="engineering").path
    fake = {
        "next_action": {
            "command": "checkpoint",
            "cli": f'python -m draftpaper_cli.cli checkpoint --project "{project}"',
            "reason": "test",
        }
    }
    with patch("draftpaper_cli.doctor.status_project", return_value=fake):
        report = verify_next_action(project)
    assert report["status"] == "failed"
    assert "--stage" in report["missing_required_options"]


def test_doctor_cli_and_recover_macro_are_read_only(tmp_path: Path) -> None:
    project = create_project(root=tmp_path, idea="Doctor CLI", field="biology").path
    before = _hash_tree(project)
    doctor = subprocess.run(
        [sys.executable, "-m", "draftpaper_cli.cli", "doctor", "--project", str(project), "--json"],
        check=True,
        capture_output=True,
        text=True,
    )
    recover = subprocess.run(
        [sys.executable, "-m", "draftpaper_cli.cli", "recover", "--project", str(project)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(doctor.stdout)["scope"] == "project"
    assert json.loads(recover.stdout)["status"] == "recovery_plan"
    assert _hash_tree(project) == before


def test_passport_rebase_requires_confirmation_and_matching_project_identity(tmp_path: Path) -> None:
    from draftpaper_cli.workflow_macros import rebase_project_passport

    source = create_project(root=tmp_path / "a", idea="Shared identity", field="medicine").path
    target = create_project(
        root=tmp_path / "b",
        idea="Shared identity",
        field="medicine",
        project_slug_override="copy",
        project_id_override="shared-identity",
    ).path
    source_json = json.loads((source / "project.json").read_text(encoding="utf-8"))
    source_json["project_id"] = "shared-identity"
    (source / "project.json").write_text(json.dumps(source_json), encoding="utf-8")
    from draftpaper_cli.passport import refresh_project_passport

    refresh_project_passport(source, event="test_identity")

    try:
        rebase_project_passport(target, source)
    except ValueError as exc:
        assert "requires --confirm" in str(exc)
    else:
        raise AssertionError("protected rebase unexpectedly ran without confirmation")

    result = rebase_project_passport(target, source, confirm=True)
    assert result["status"] == "rebased"
    assert (target / "passport_rebase_receipt.json").is_file()
