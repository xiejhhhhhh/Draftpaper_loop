from __future__ import annotations

import json
from pathlib import Path

import pytest

from draftpaper_cli.latex_assembly import _render_main
from draftpaper_cli.manuscript_revision import (
    ManuscriptRevisionError,
    active_user_locks,
    add_custom_reference,
    apply_manuscript_revision,
    assert_writer_may_replace_section,
    build_manuscript_source_map,
    import_review_findings,
    inspect_revision_preview,
    list_revision_tasks,
    preview_manuscript_revision,
    rollback_manuscript_revision,
    set_manuscript_metadata,
)
from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.project_state import load_project


def _project(tmp_path: Path) -> Path:
    project = create_project(root=tmp_path, idea="Stable author revision", field="astronomy").path
    sections = {
        "introduction": "\\section{Introduction}\nFirst introduction paragraph.\n\nSecond introduction paragraph.\n",
        "data": "\\section{Data}\nData paragraph.\n",
        "methods": "\\section{Methods}\nMethods paragraph.\n",
        "results": "\\section{Results}\nResult F1 was 0.82 in Figure~\\ref{fig:main}.\n",
        "discussion": "\\section{Discussion}\nDiscussion paragraph with \\citep{Existing2026}.\n\nLimitations paragraph.\n",
    }
    for section, text in sections.items():
        canonical = project / section / f"{section}.tex"
        canonical.parent.mkdir(parents=True, exist_ok=True)
        canonical.write_text(text, encoding="utf-8")
    (project / "references" / "library.bib").write_text(
        "@article{Existing2026, author={A. Author}, title={Existing work}, year={2026}}\n",
        encoding="utf-8",
    )
    return project


def test_source_map_supports_paragraph_and_line_targets_and_detects_drift(tmp_path: Path) -> None:
    project = _project(tmp_path)
    report = build_manuscript_source_map(project)
    assert report["paragraph_count"] >= 6
    source_map = json.loads((project / "latex" / "manuscript_source_map.json").read_text(encoding="utf-8"))
    target = next(item for item in source_map["paragraphs"] if item["section"] == "discussion")

    content = tmp_path / "replacement.tex"
    content.write_text("A precise replacement paragraph.\n", encoding="utf-8")
    by_paragraph = preview_manuscript_revision(
        project,
        "Replace this paragraph",
        paragraph=target["paragraph_id"],
        content_file=content,
    )
    assert by_paragraph["status"] == "ready"
    assert "A precise replacement" in inspect_revision_preview(project, by_paragraph["revision_id"])["diff"]

    by_line = preview_manuscript_revision(
        project,
        "Replace by current line anchor",
        at=f"{target['file']}:{target['line_start']}-{target['line_end']}",
        content_file=content,
    )
    assert by_line["status"] == "ready"

    canonical = project / target["canonical_file"]
    canonical.write_text(
        canonical.read_text(encoding="utf-8").replace(
            "\\section{Discussion}\nDiscussion paragraph",
            "\\section{Discussion}\nExternally changed discussion paragraph",
            1,
        ),
        encoding="utf-8",
    )
    with pytest.raises(ManuscriptRevisionError, match="changed after source-map"):
        preview_manuscript_revision(
            project,
            "Stale line request",
            paragraph=target["paragraph_id"],
            content_file=content,
        )


def test_exact_text_is_locked_applied_and_rollback_is_hash_guarded(tmp_path: Path) -> None:
    project = _project(tmp_path)
    build_manuscript_source_map(project)
    source_map = json.loads((project / "latex" / "manuscript_source_map.json").read_text(encoding="utf-8"))
    target = next(item for item in source_map["paragraphs"] if item["section"] == "discussion")
    content = tmp_path / "exact.tex"
    content.write_text("Author-approved exact wording with \\citep{Existing2026}.\n", encoding="utf-8")

    preview = preview_manuscript_revision(
        project,
        "Use exact author wording",
        paragraph=target["paragraph_id"],
        content_file=content,
        mode="exact_text",
        change_class="citation_edit",
    )
    applied = apply_manuscript_revision(project, preview["revision_id"])
    assert applied["status"] == "applied"
    workspace = json.loads((project / "writing" / "revision_workspace.json").read_text(encoding="utf-8"))
    assert workspace["pending_requests"] == []
    assert workspace["requests"][0]["status"] == "applied"
    workspace["requests"][0]["status"] = "ready"
    workspace["pending_requests"] = list(workspace["requests"])
    (project / "writing" / "revision_workspace.json").write_text(json.dumps(workspace), encoding="utf-8")
    build_manuscript_source_map(project)
    workspace = json.loads((project / "writing" / "revision_workspace.json").read_text(encoding="utf-8"))
    assert workspace["pending_requests"] == []
    assert workspace["requests"][0]["status"] == "applied"
    assert content.read_text(encoding="utf-8") in (project / "discussion" / "discussion.tex").read_text(encoding="utf-8")
    assert active_user_locks(project, "discussion")
    assert (project / "citation_audit" / "stale_marker.json").is_file()
    with pytest.raises(ManuscriptRevisionError, match="may not silently replace"):
        assert_writer_may_replace_section(project, "discussion")

    rolled_back = rollback_manuscript_revision(project, preview["revision_id"])
    assert rolled_back["status"] == "rolled_back"
    workspace = json.loads((project / "writing" / "revision_workspace.json").read_text(encoding="utf-8"))
    assert workspace["pending_requests"] == []
    assert workspace["requests"][0]["status"] == "rolled_back"
    assert not active_user_locks(project, "discussion")
    assert "Discussion paragraph" in (project / "discussion" / "discussion.tex").read_text(encoding="utf-8")


def test_scientific_change_cannot_be_applied_as_prose_patch(tmp_path: Path) -> None:
    project = _project(tmp_path)
    build_manuscript_source_map(project)
    source_map = json.loads((project / "latex" / "manuscript_source_map.json").read_text(encoding="utf-8"))
    target = next(item for item in source_map["paragraphs"] if item["section"] == "results")
    content = tmp_path / "scientific.tex"
    content.write_text("The replacement run yielded F1=0.91.\n", encoding="utf-8")
    preview = preview_manuscript_revision(
        project,
        "Replace the model run and figure",
        paragraph=target["paragraph_id"],
        content_file=content,
        change_class="scientific_evidence_change",
    )
    with pytest.raises(ManuscriptRevisionError, match="cannot apply a data/method/run/core-figure change"):
        apply_manuscript_revision(project, preview["revision_id"])


def test_metadata_replaces_placeholders_and_default_acknowledgment(tmp_path: Path) -> None:
    project = _project(tmp_path)
    metadata = tmp_path / "metadata.yaml"
    metadata.write_text(
        """title: Evidence-aware morphology analysis
abstract: We test an evidence-aware morphology analysis and report a bounded validation result.
authors:
  - name: Alice Example
    affiliations: [inst1]
    corresponding: true
    email: alice@example.org
affiliations:
  - id: inst1
    name: Institute of Reproducible Science
acknowledgments: We thank the survey teams.
funding: Grant 123.
data_availability: Data are available from the stated archive.
code_availability: Analysis code is archived with the release.
""",
        encoding="utf-8",
    )
    set_manuscript_metadata(project, metadata)
    rendered = _render_main(project, load_project(project).metadata)
    assert "Evidence-aware morphology analysis" in rendered
    assert "We test an evidence-aware morphology analysis" in rendered
    assert "Alice Example" in rendered
    assert "Institute of Reproducible Science" in rendered
    assert "We thank the survey teams" in rendered
    assert "Data Availability" in rendered
    assert "This study used Draftpaper-loop" not in rendered
    assert "placeholder.invalid" not in rendered


def test_custom_reference_and_review_findings_enter_structured_queues(tmp_path: Path) -> None:
    project = _project(tmp_path)
    custom = tmp_path / "reference.json"
    custom.write_text(json.dumps({
        "citation_key": "Custom2025",
        "title": "A custom verified source",
        "authors": ["A. Researcher", "B. Researcher"],
        "year": 2025,
        "journal": "Journal of Tests",
        "doi": "10.1234/example",
        "evidence_notes": "Supports the comparison boundary used in Discussion.",
    }), encoding="utf-8")
    added = add_custom_reference(project, custom)
    assert added["status"] == "added"
    assert "Custom2025" in (project / "references" / "library.bib").read_text(encoding="utf-8")
    registry = json.loads((project / "references" / "reference_registry.json").read_text(encoding="utf-8"))
    assert any(item.get("citation_key") == "Custom2025" for item in registry.get("records") or [])

    aggregate = project / "quality_checks" / "blind_reviews" / "aggregate.json"
    aggregate.parent.mkdir(parents=True, exist_ok=True)
    aggregate.write_text(json.dumps({"revision_queue": [{
        "reviewer": "reviewer_01",
        "finding_id": "reviewer_01:001",
        "severity": "major",
        "locator": "Discussion, paragraph 1",
        "detail": "The comparison boundary is unclear.",
        "required_action": "Narrow the comparison claim.",
    }]}), encoding="utf-8")
    imported = import_review_findings(project)
    listed = list_revision_tasks(project)
    assert imported["task_count"] == 1
    assert listed["task_count"] == 1
    assert listed["tasks"][0]["automatic_apply"] is False
