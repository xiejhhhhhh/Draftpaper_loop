from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from draftpaper_cli.cli import build_parser
from draftpaper_cli.command_registry import command_spec
from draftpaper_cli.manuscript_completion import (
    COMPLETION_SCHEMA,
    ManuscriptCompletionError,
    parse_manuscript_completion_packet,
    resolve_manuscript_revision_target,
)
from draftpaper_cli.manuscript_revision import (
    ManuscriptRevisionError,
    build_manuscript_source_map,
    preview_manuscript_revision,
)
from draftpaper_cli.project_scaffold import create_project


def _project(tmp_path: Path) -> Path:
    project = create_project(
        root=tmp_path,
        idea="Completion locator test",
        field="machine learning",
        target_journal="Test Journal",
    ).path
    sections = {
        "introduction": "\\section{Introduction}\n\nIntroduction paragraph.\n",
        "data": "\\section{Data}\n\nData paragraph.\n",
        "methods": "\\section{Methods}\n\nMethods paragraph.\n\nRepeated paragraph.\n\nRepeated paragraph.\n",
        "results": "\\section{Results}\n\nResult paragraph.\n",
        "discussion": "\\section{Discussion}\n\nDiscussion paragraph.\n",
    }
    for section, text in sections.items():
        path = project / section / f"{section}.tex"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    build_manuscript_source_map(project)
    return project


def _row(project: Path, *, section: str, excerpt: str) -> dict[str, object]:
    source_map = json.loads((project / "latex" / "manuscript_source_map.json").read_text(encoding="utf-8"))
    return next(
        row
        for row in source_map["paragraphs"]
        if row["section"] == section and excerpt.lower() in row["context_excerpt"]
    )


def test_locator_reanchors_after_line_drift_when_id_hash_and_text_still_agree(tmp_path: Path) -> None:
    project = _project(tmp_path)
    original = _row(project, section="methods", excerpt="Methods paragraph")
    methods = project / "methods" / "methods.tex"
    methods.write_text(
        methods.read_text(encoding="utf-8").replace("\\section{Methods}\n\n", "\\section{Methods}\n\nNew opening paragraph.\n\n"),
        encoding="utf-8",
    )
    build_manuscript_source_map(project)

    resolution = resolve_manuscript_revision_target(
        project,
        {
            "section": "methods",
            "paragraph_id": original["paragraph_id"],
            "expected_sha256": original["before_hash"],
            "expected_text": "Methods paragraph.",
            "line_start_hint": original["line_start"],
            "line_end_hint": original["line_end"],
        },
    )

    assert resolution["status"] == "resolved"
    assert resolution["paragraph_id"] == original["paragraph_id"]
    assert resolution["line_drift"] is True
    assert resolution["line_start"] > original["line_start"]


def test_locator_rejects_stale_hash_and_ambiguous_expected_text(tmp_path: Path) -> None:
    project = _project(tmp_path)
    methods = _row(project, section="methods", excerpt="Methods paragraph")

    with pytest.raises(ManuscriptCompletionError, match="stale_target"):
        resolve_manuscript_revision_target(
            project,
            {
                "paragraph_id": methods["paragraph_id"],
                "expected_sha256": "0" * 64,
            },
        )
    with pytest.raises(ManuscriptCompletionError, match="ambiguous_target"):
        resolve_manuscript_revision_target(
            project,
            {"section": "methods", "expected_text": "Repeated paragraph."},
        )

    second = resolve_manuscript_revision_target(
        project,
        {"section": "methods", "expected_text": "Repeated paragraph.", "occurrence": 2},
    )
    assert second["status"] == "resolved"
    assert second["matched_by"] == ["expected_text", "occurrence"]


def test_locator_rejects_line_only_target(tmp_path: Path) -> None:
    project = _project(tmp_path)
    with pytest.raises(ManuscriptCompletionError, match="stable locator"):
        resolve_manuscript_revision_target(
            project,
            {"section": "methods", "line_start_hint": 3, "line_end_hint": 3},
        )


def test_batch_packet_resolves_multiple_sections_against_one_source_revision(tmp_path: Path) -> None:
    project = _project(tmp_path)
    methods = _row(project, section="methods", excerpt="Methods paragraph")
    results = _row(project, section="results", excerpt="Result paragraph")
    input_dir = project / "writing" / "author_input"
    snippets = input_dir / "snippets"
    snippets.mkdir(parents=True)
    (snippets / "methods-note.tex").write_text("User-authored method note.", encoding="utf-8")
    packet = {
        "schema_version": COMPLETION_SCHEMA,
        "project_id": json.loads((project / "project.json").read_text(encoding="utf-8"))["project_id"],
        "target_journal": "Test Journal",
        "metadata": {},
        "custom_references": [
            {
                "citation_key": "Example2026",
                "title": "Example",
                "authors": ["A. Example"],
                "year": 2026,
                "evidence_notes": "Supports a bounded comparison.",
            }
        ],
        "section_revisions": [
            {
                "revision_key": "methods-note",
                "target": {
                    "paragraph_id": methods["paragraph_id"],
                    "expected_sha256": methods["before_hash"],
                },
                "operation": "insert_after",
                "mode": "exact_text",
                "content_file": "snippets/methods-note.tex",
            },
            {
                "revision_key": "results-instruction",
                "target": {
                    "paragraph_id": results["paragraph_id"],
                    "expected_text": "Result paragraph.",
                },
                "operation": "replace",
                "mode": "instruction_to_codex",
                "instruction": "Clarify the uncertainty without changing the reported result.",
            },
        ],
    }
    packet_path = input_dir / "completion.yaml"
    packet_path.write_text(yaml.safe_dump(packet, sort_keys=False), encoding="utf-8")

    parsed = parse_manuscript_completion_packet(project, packet_path)

    assert parsed["status"] == "resolved"
    assert parsed["project_revision"] == json.loads((project / "project.json").read_text(encoding="utf-8"))["state_revision"]
    assert len(parsed["resolved_revisions"]) == 2
    assert len(parsed["source_map_sha256"]) == 64
    assert parsed["resolved_revisions"][0]["content"] == "User-authored method note."
    assert parsed["custom_references"][0]["citation_key"] == "Example2026"


def test_batch_packet_rejects_duplicate_targets_as_one_conflict(tmp_path: Path) -> None:
    project = _project(tmp_path)
    methods = _row(project, section="methods", excerpt="Methods paragraph")
    project_id = json.loads((project / "project.json").read_text(encoding="utf-8"))["project_id"]
    revision = {
        "target": {"paragraph_id": methods["paragraph_id"], "expected_sha256": methods["before_hash"]},
        "operation": "insert_after",
        "mode": "exact_text",
        "content": "A note.",
    }
    packet = {
        "schema_version": COMPLETION_SCHEMA,
        "project_id": project_id,
        "target_journal": "Test Journal",
        "metadata": {},
        "custom_references": [],
        "section_revisions": [
            {"revision_key": "first", **revision},
            {"revision_key": "second", **revision},
        ],
    }
    packet_path = project / "writing" / "conflict.yaml"
    packet_path.parent.mkdir(parents=True, exist_ok=True)
    packet_path.write_text(yaml.safe_dump(packet, sort_keys=False), encoding="utf-8")

    with pytest.raises(ManuscriptCompletionError, match="conflicting_target"):
        parse_manuscript_completion_packet(project, packet_path)


def test_revise_parser_exposes_expected_text_hash_occurrence_and_confines_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _project(tmp_path)
    methods = _row(project, section="methods", excerpt="Methods paragraph")
    parser = build_parser()
    args = parser.parse_args(
        [
            "revise",
            "--project",
            str(project),
            "--paragraph",
            str(methods["paragraph_id"]),
            "--expect-text",
            "Methods paragraph.",
            "--expect-sha256",
            str(methods["before_hash"]),
            "--occurrence",
            "1",
            "--instruction",
            "Add a bounded note.",
        ]
    )
    assert args.expect_text == "Methods paragraph."
    assert args.expect_sha256 == methods["before_hash"]
    assert args.occurrence == 1
    spec = command_spec("revise")
    assert spec is not None
    assert {binding[0] for binding in spec.argument_bindings} >= {
        "expected_text",
        "expected_text_file",
        "expected_sha256",
        "occurrence",
    }

    outside = tmp_path / "outside.tex"
    outside.write_text("Outside content.", encoding="utf-8")
    monkeypatch.setattr("draftpaper_cli.manuscript_revision._validated_evidence_snapshot_id", lambda _root: "snapshot")
    with pytest.raises(ManuscriptRevisionError, match="project directory"):
        preview_manuscript_revision(
            project,
            "Replace content.",
            paragraph=str(methods["paragraph_id"]),
            content_file=outside,
            mode="exact_text",
        )
