from __future__ import annotations

import json
from pathlib import Path

from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.runtime_handshake import RUNTIME_LOCK, check_runtime_for_command, session_preflight


def test_session_preflight_initializes_and_detects_runtime_mismatch(tmp_path: Path) -> None:
    project = create_project(root=tmp_path, idea="Runtime handshake test", field="machine learning").path
    first = session_preflight(project)
    assert first["status"] == "initialized"
    assert (project / RUNTIME_LOCK).is_file()

    lock = json.loads((project / RUNTIME_LOCK).read_text(encoding="utf-8"))
    lock["command_registry_sha256"] = "old-runtime"
    (project / RUNTIME_LOCK).write_text(json.dumps(lock), encoding="utf-8")
    guard = check_runtime_for_command(project, "generate-analysis-code")
    assert guard["status"] == "blocked"
    assert any(item["field"] == "command_registry_sha256" for item in guard["mismatches"])
    second = session_preflight(project)
    assert second["status"] == "blocked"
    assert (project / RUNTIME_LOCK).read_text(encoding="utf-8").find("old-runtime") >= 0
