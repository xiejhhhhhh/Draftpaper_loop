from __future__ import annotations

import json

from draftpaper_cli.cli import build_parser
from draftpaper_cli.literature_integrity import audit_literature_integrity
from draftpaper_cli.literature_merge import rebuild_literature_index, repair_literature_identities
from draftpaper_cli.literature_repository import load_literature_registry, write_literature_registry
from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.references import write_reference_outputs


def test_literature_commands_have_parser_contracts() -> None:
    parser = build_parser()
    choices = parser._subparsers._group_actions[0].choices
    assert {
        "audit-literature-integrity",
        "sync-literature-sources",
        "apply-literature-sync",
        "repair-literature-identities",
        "rebuild-literature-index",
        "quarantine-orphan-literature",
    } <= set(choices)


def test_registry_and_identity_repair_are_repeatable(tmp_path) -> None:
    project = create_project(root=tmp_path / "projects", idea="Registry test", field="science").path
    write_reference_outputs(
        project,
        [{"title": "Registry paper", "authors": ["Author"], "year": "2024", "doi": "10.1000/registry", "abstract": "A registry test.", "source": "openalex"}],
        query="Registry test",
    )
    registry = write_literature_registry(project, json.loads((project / "references" / "literature_items.json").read_text(encoding="utf-8")))
    loaded = load_literature_registry(project)
    preview = repair_literature_identities(project)
    rebuilt = rebuild_literature_index(project)

    assert registry["record_count"] == 1
    assert loaded["schema_version"] == "dpl.literature_work_registry.v3"
    assert loaded["records"][0]["work_id"] == "doi:10.1000/registry"
    assert preview["status"] == "preview"
    assert rebuilt["status"] == "rebuilt"
    assert (project / "references" / "literature_summaries" / "index.html").is_file()


def test_integrity_audit_reports_unmatched_fulltext_without_mutating_source(tmp_path) -> None:
    project = create_project(root=tmp_path / "projects", idea="Identity test", field="science").path
    write_reference_outputs(
        project,
        [{"title": "Active paper", "authors": ["Author"], "year": "2024", "doi": "10.1000/active", "abstract": "An active source.", "source": "openalex"}],
        query="Identity test",
    )
    fulltext = project / "references" / "fulltext"
    fulltext.mkdir(parents=True)
    orphan = fulltext / "foreign.json"
    orphan.write_text(json.dumps({"doi": "10.1000/foreign", "title": "Foreign source"}), encoding="utf-8")

    report = audit_literature_integrity(project)

    assert report["status"] == "review_required"
    assert report["orphan_count"] == 1
    assert orphan.is_file()
    payload = json.loads((project / "references" / "literature_integrity_report.json").read_text(encoding="utf-8"))
    assert payload["orphan_artifacts"][0]["status"] == "foreign_project_suspected"
