from __future__ import annotations

import json
from pathlib import Path

from draftpaper_cli.checkpoint_digest import discover_stage_paths
from draftpaper_cli.checkpoint_summary import write_stage_summary
from draftpaper_cli.project_scaffold import create_project


def _write(path: Path, content: str = "fixture\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_stage_discovery_is_owned_and_excludes_history_and_other_stages(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="scope contract", field="generic scientific workflow").path
    _write(project / "data" / "owned_inventory.json", json.dumps({"stage": "data"}))
    _write(project / "methods" / "other_stage.json", json.dumps({"stage": "methods"}))
    _write(project / "review" / "checkpoints" / "old" / "stage_summary.json", json.dumps({"old": True}))
    _write(project / "review" / "independent_review" / "old.json", json.dumps({"old": True}))
    _write(project / ".draftpaper" / "cache.json", json.dumps({"cache": True}))

    paths = discover_stage_paths(project, "data")

    assert "data/owned_inventory.json" in paths
    assert "methods/other_stage.json" not in paths
    assert "review/checkpoints/old/stage_summary.json" not in paths
    assert "review/independent_review/old.json" not in paths
    assert ".draftpaper/cache.json" not in paths


def test_stage_summary_does_not_promote_other_stage_artifact(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="scope summary", field="generic scientific workflow").path
    _write(project / "data" / "data_contract.md", "# data\n")
    _write(project / "methods" / "method_contract.md", "# methods\n")
    report = write_stage_summary(
        project,
        stage="data",
        command="scope-summary",
        payload={"status": "checkpoint_created"},
        before_artifacts=[],
        checkpoint_id="scope-data",
        checkpoint_hash="scope-hash",
        publish_index=False,
    )
    summary = json.loads((project / report["stage_summary_json"]).read_text(encoding="utf-8"))
    paths = {item["project_relative_path"] for item in summary["stage_deliverables"]}

    assert "data/data_contract.md" in paths
    assert "methods/method_contract.md" not in paths
