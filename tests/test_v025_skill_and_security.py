from __future__ import annotations

import json
from pathlib import Path

import pytest

from draftpaper_cli.command_registry import COMMAND_SPECS
from draftpaper_cli.execution_policy import command_allowed_via_mcp, redact_sensitive
from draftpaper_cli.skill_sync import canonical_skill_hash, install_skill, skill_doctor
from draftpaper_cli.write_set_guard import BoundaryViolation, WriteSetGuard, resolve_confined_path


def test_packaged_skill_install_and_hash_doctor(tmp_path: Path) -> None:
    destination = tmp_path / "skill"
    installed = install_skill(destination)
    assert installed["status"] == "installed"
    assert installed["sha256"] == canonical_skill_hash()
    assert skill_doctor(destination)["status"] == "passed"
    (destination / "SKILL.md").write_text("stale", encoding="utf-8")
    report = skill_doctor(destination)
    assert report["status"] == "failed"
    assert report["reason"] == "skill_hash_mismatch"


def test_every_command_has_v2_policy_and_schema() -> None:
    assert COMMAND_SPECS
    for spec in COMMAND_SPECS.values():
        assert spec.risk_level
        assert spec.allowed_read_globs
        assert spec.timeout_seconds > 0
        assert spec.idempotency in {"required", "supported", "none"}
        assert spec.input_schema.get("type") == "object"
        assert spec.output_schema.get("type") == "object"
        if spec.mutates_project:
            assert spec.allowed_write_globs
    protected = COMMAND_SPECS["checkpoint"]
    assert command_allowed_via_mcp(protected)[0] is False


def test_path_confinement_rejects_parent_symlink_and_unc(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    assert resolve_confined_path(root, "data/table.csv") == (root / "data/table.csv").resolve()
    with pytest.raises(BoundaryViolation):
        resolve_confined_path(root, "../escape.txt")
    with pytest.raises(BoundaryViolation):
        resolve_confined_path(root, r"\\server\share\secret")
    link = root / "linked"
    try:
        link.symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        return
    with pytest.raises(BoundaryViolation):
        resolve_confined_path(root, "linked/out.txt")


def test_write_set_guard_preserves_dirty_baseline_and_detects_new_out_of_scope_write(tmp_path: Path) -> None:
    root = tmp_path / "project"
    (root / "data").mkdir(parents=True)
    dirty = root / "notes.txt"
    dirty.write_text("user work", encoding="utf-8")
    guard = WriteSetGuard(root, COMMAND_SPECS["inventory-data"])
    (root / "data" / "inventory.json").write_text("{}", encoding="utf-8")
    assert guard.assess()["status"] == "passed"

    guard = WriteSetGuard(root, COMMAND_SPECS["inventory-data"])
    (root / "methods").mkdir()
    (root / "methods" / "unexpected.py").write_text("pass", encoding="utf-8")
    report = guard.assess()
    assert report["status"] == "boundary_violation"
    assert "methods/unexpected.py" in report["violations"]
    assert dirty.read_text(encoding="utf-8") == "user work"


def test_sensitive_response_redaction() -> None:
    payload = redact_sensitive({
        "api_key": "very-secret",
        "message": r"password=hunter2 at C:\private\paper and user@example.com",
    })
    rendered = json.dumps(payload)
    assert "very-secret" not in rendered
    assert "hunter2" not in rendered
    assert "user@example.com" not in rendered
    assert r"C:\private" not in rendered
