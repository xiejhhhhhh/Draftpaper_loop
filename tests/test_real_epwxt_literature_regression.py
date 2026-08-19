from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from draftpaper_cli.literature_integrity import audit_literature_integrity
from draftpaper_cli.literature_merge import rebuild_literature_index
from draftpaper_cli.literature_migration import apply_literature_migration, build_literature_migration_preview
from draftpaper_cli.project_scaffold import create_project


DEFAULT_PROJECT = Path(r"C:\Draftpaper_commercial\projects\ep-wxt-agn-xrb-source-population-genera_a6fbde7c")


def _real_project() -> Path | None:
    candidate = Path(os.environ.get("DPL_EPWXT_PROJECT", str(DEFAULT_PROJECT))).expanduser()
    return candidate if candidate.is_dir() else None


def _copy_real_literature_inputs(source: Path, target: Path) -> None:
    source_references = source / "references"
    target_references = target / "references"
    target_references.mkdir(parents=True, exist_ok=True)
    for name in ("literature_items.json", "search_queries.json", "code_sources.json"):
        source_file = source_references / name
        if source_file.is_file():
            shutil.copy2(source_file, target_references / name)
    source_summaries = source_references / "literature_summaries"
    if source_summaries.is_dir():
        shutil.copytree(source_summaries, target_references / "literature_summaries", dirs_exist_ok=True)


@pytest.mark.skipif(_real_project() is None, reason="EP/WXT real-project regression input is not available")
def test_real_epwxt_migration_preserves_22_works_10_parses_and_scores(tmp_path: Path) -> None:
    source = _real_project()
    assert source is not None
    source_items = json.loads((source / "references" / "literature_items.json").read_text(encoding="utf-8-sig"))
    assert isinstance(source_items, list)
    assert len(source_items) == 22
    assert sum(bool(item.get("document_parses")) for item in source_items) == 10

    project = create_project(root=tmp_path / "projects", idea="EP WXT migration", field="astronomy").path
    _copy_real_literature_inputs(source, project)
    preview = build_literature_migration_preview(project)
    assert preview["proposed_item_count"] == 22
    assert len(set(json.loads((project / "references" / "literature_migration_preview.json").read_text(encoding="utf-8"))["work_ids"])) == 22

    applied = apply_literature_migration(project, packet_hash=preview["packet_hash"])
    assert applied["status"] == "applied"
    migrated = json.loads((project / "references" / "literature_items.json").read_text(encoding="utf-8"))
    assert len(migrated) == 22
    assert all(item.get("work_id") == item.get("canonical_work_id") and item.get("work_id") for item in migrated)
    assert sum(bool(item.get("document_parses")) for item in migrated) == 10
    assert all(item.get(field) is not None for item in migrated for field in ("citation_weight", "relevance_score", "journal_score"))

    integrity = audit_literature_integrity(project)
    assert integrity["active_work_count"] == 22
    assert integrity["snapshot_binding"]["status"] == "passed"
    assert integrity["status"] == "passed"

    first = rebuild_literature_index(project)
    second = rebuild_literature_index(project)
    assert first["snapshot_hash"] == second["snapshot_hash"]
    assert audit_literature_integrity(project)["snapshot_binding"]["status"] == "passed"
