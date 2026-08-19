from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

import pytest

from draftpaper_cli.literature_integrity import (
    audit_literature_integrity,
    parse_literature_index,
    quarantine_orphan_literature_artifacts,
    rollback_orphan_literature_quarantine,
)
from draftpaper_cli.literature_merge import rebuild_literature_index
from draftpaper_cli.literature_migration import apply_literature_migration, build_literature_migration_preview
from draftpaper_cli.project_scaffold import create_project


DEFAULT_PROJECT = Path(r"C:\Draftpaper_commercial\projects\EuclidxDESI")


def _real_project() -> Path | None:
    candidate = Path(os.environ.get("DPL_EUCLIDXDESI_PROJECT", str(DEFAULT_PROJECT))).expanduser()
    return candidate if candidate.is_dir() else None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): _sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


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
    source_fulltext = source_references / "fulltext"
    if source_fulltext.is_dir():
        target_fulltext = target_references / "fulltext"
        target_fulltext.mkdir(parents=True, exist_ok=True)
        # Keep the real JSON payloads but use short harness names so the test
        # remains runnable on Windows installations without long-path support.
        for index, source_file in enumerate(sorted(source_fulltext.glob("*.json")), start=1):
            shutil.copy2(source_file, target_fulltext / f"{index:03d}.json")


@pytest.mark.skipif(_real_project() is None, reason="EuclidxDESI real-project regression input is not available")
def test_real_euclidxdesi_index_is_migrated_without_loss_or_orphan_reentry(tmp_path: Path) -> None:
    source = _real_project()
    assert source is not None
    source_index = source / "references" / "literature_summaries" / "index.html"
    parsed = parse_literature_index(source_index)
    assert parsed["status"] == "parsed"
    assert parsed["rows"]
    source_index_hash = _sha256(source_index)

    project = create_project(root=tmp_path / "p", idea="E", field="a").path
    _copy_real_literature_inputs(source, project)
    copied_fulltext_hashes = _file_hashes(project / "references" / "fulltext")

    preview = build_literature_migration_preview(project)
    assert preview["index_row_count"] == len(parsed["rows"])
    assert preview["proposed_item_count"] == len(parsed["rows"])
    preview_payload = json.loads((project / "references" / "literature_migration_preview.json").read_text(encoding="utf-8"))
    assert len(set(preview_payload["work_ids"])) == len(parsed["rows"])
    assert all(preview_payload["work_ids"])

    applied = apply_literature_migration(project, packet_hash=preview["packet_hash"])
    assert applied["status"] == "applied"
    migrated_items = json.loads((project / "references" / "literature_items.json").read_text(encoding="utf-8"))
    assert len(migrated_items) == len(parsed["rows"])
    assert all(item.get("work_id") == item.get("canonical_work_id") for item in migrated_items)

    integrity = audit_literature_integrity(project)
    assert integrity["active_work_count"] == len(parsed["rows"])
    orphan_count = integrity["orphan_count"]
    quarantined = quarantine_orphan_literature_artifacts(project)
    assert quarantined["moved_count"] == orphan_count
    rolled_back = rollback_orphan_literature_quarantine(project)
    assert rolled_back["restored_count"] == orphan_count
    assert _file_hashes(project / "references" / "fulltext") == copied_fulltext_hashes

    rebuild_literature_index(project)
    first_summary_hashes = _file_hashes(project / "references" / "literature_summaries")
    rebuild_literature_index(project)
    second_summary_hashes = _file_hashes(project / "references" / "literature_summaries")
    assert first_summary_hashes == second_summary_hashes
    assert _sha256(source_index) == source_index_hash

    output_index = project / "references" / "literature_summaries" / "index.html"
    output = parse_literature_index(output_index)
    assert output["status"] == "parsed"
    assert len(output["rows"]) == len(parsed["rows"])
    header_names = [value.casefold() for value in output["headers"]]
    assert "github/zenodo code sources" in header_names
    assert "identity status" in header_names
    assert "citation eligibility" in header_names
    assert "context" in header_names
    assert all(len(row) == len(output["headers"]) for row in output["rows"])
    html = output_index.read_text(encoding="utf-8")
    assert 'data-locale-button="zh-CN"' in html
    assert 'data-locale-button="en"' in html
    assert '"zh-CN"' in html and '"en"' in html
    assert len(list((project / "references" / "literature_summaries").glob("*.html"))) == len(parsed["rows"]) + 1
