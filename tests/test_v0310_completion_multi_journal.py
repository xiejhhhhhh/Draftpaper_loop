from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml
from pypdf import PdfReader

from draftpaper_cli.manuscript_completion import (
    COMPLETION_SCHEMA,
    apply_manuscript_completion,
    preview_manuscript_completion,
)
from draftpaper_cli.manuscript_revision import build_manuscript_source_map
from draftpaper_cli.project_scaffold import create_project


JOURNAL_CASES = (
    (
        "general-article",
        "General Academic Journal",
        "article",
        {
            "authors": [{"id": "a1", "name": "Alice Example", "affiliations": ["i1"]}],
            "affiliations": [{"id": "i1", "name": "General Institute"}],
        },
    ),
    (
        "aas-frontmatter",
        "AAS Journals",
        "aastex701",
        {
            "authors": [
                {"id": "a1", "name": "Alice Example", "affiliations": ["i1"], "orcid": "0000-0001-2345-6789"},
                {"id": "a2", "name": "Bob Example", "affiliations": ["i1", "i2"], "email": "bob@example.edu"},
            ],
            "affiliations": [
                {"id": "i1", "name": "Astronomy Institute"},
                {"id": "i2", "name": "Survey Centre"},
            ],
            "funding": [{"funder": "Science Council", "award_id": "SC-1"}],
        },
    ),
    (
        "mnras-frontmatter",
        "MNRAS",
        "mnras",
        {
            "authors": [
                {"id": "a1", "name": "Alice Example", "affiliations": ["i1"], "corresponding": True},
                {"id": "a2", "name": "Bob Example", "affiliations": ["i2"]},
            ],
            "affiliations": [
                {"id": "i1", "name": "Institute One"},
                {"id": "i2", "name": "Institute Two"},
            ],
            "corresponding_author": "Alice Example",
            "email": "alice@example.edu",
            "repository_links": ["https://example.org/code"],
        },
    ),
)


def _main_tex(*, aas_stub: bool) -> str:
    stubs = ""
    if aas_stub:
        stubs = (
            "\\providecommand{\\shorttitle}[1]{}\n"
            "\\providecommand{\\keywords}[1]{}\n"
            "\\providecommand{\\affiliation}[1]{}\n"
            "\\providecommand{\\email}[1]{}\n"
            "\\providecommand{\\orcid}[1]{}\n"
            "\\newenvironment{acknowledgments}{\\section*{Acknowledgments}}{}\n"
        )
    return (
        "\\documentclass{article}\n"
        "\\usepackage[T1]{fontenc}\n"
        "\\usepackage{hyperref}\n"
        + stubs
        + "\\title{Original title}\n\\author{}\n"
        "\\begin{document}\n\\maketitle\n"
        "\\input{sections/introduction.tex}\n"
        "\\input{sections/data.tex}\n"
        "\\input{sections/methods.tex}\n"
        "\\input{sections/results.tex}\n"
        "\\input{sections/discussion.tex}\n"
        "\\end{document}\n"
    )


def _project(tmp_path: Path, journal: str, documentclass: str) -> Path:
    project = create_project(
        root=tmp_path,
        idea="R",
        field="astronomy",
        target_journal=journal,
    ).path
    for section in ("introduction", "data", "methods", "results", "discussion"):
        text = f"\\section{{{section.title()}}}\n\nInitial {section} paragraph.\n"
        canonical = project / section / f"{section}.tex"
        canonical.parent.mkdir(parents=True, exist_ok=True)
        canonical.write_text(text, encoding="utf-8")
        projection = project / "latex" / "sections" / f"{section}.tex"
        projection.parent.mkdir(parents=True, exist_ok=True)
        projection.write_text(text, encoding="utf-8")
    (project / "latex" / "main.tex").write_text(
        _main_tex(aas_stub=documentclass == "aastex701"),
        encoding="utf-8",
    )
    profile = project / "journal_profile" / "journal_profile.json"
    profile.parent.mkdir(parents=True, exist_ok=True)
    profile.write_text(
        json.dumps(
            {
                "target_journal": journal,
                "documentclass": documentclass,
                "rules": {"requires_keywords": True},
            }
        ),
        encoding="utf-8",
    )
    build_manuscript_source_map(project)
    return project


def _packet(project: Path, journal: str, metadata_case: dict[str, object]) -> Path:
    source_map = json.loads((project / "latex" / "manuscript_source_map.json").read_text(encoding="utf-8"))
    targets = [
        row
        for row in source_map["paragraphs"]
        if row["section"] in {"methods", "discussion"} and "\\section" not in row["context_excerpt"]
    ]
    metadata = {
        "title": f"Completed {journal} manuscript",
        "short_title": "Completion regression",
        "abstract": "This candidate verifies a bounded final-author completion workflow.",
        "keywords": ["research workflow", "reproducibility"],
        "acknowledgments": "We thank the independent reviewers.",
        "data_availability": "Data are available from the named archive.",
        "code_availability": "Code is available from the named repository.",
        **metadata_case,
    }
    revisions = []
    for index, target in enumerate(targets, start=1):
        revisions.append(
            {
                "revision_key": f"revision-{index}",
                "target": {
                    "paragraph_id": target["paragraph_id"],
                    "expected_sha256": target["before_hash"],
                },
                "operation": "insert_after",
                "mode": "exact_text",
                "content": f"Author-confirmed addition {index}.",
                "change_class": "prose_only",
            }
        )
    payload = {
        "schema_version": COMPLETION_SCHEMA,
        "project_id": json.loads((project / "project.json").read_text(encoding="utf-8"))["project_id"],
        "target_journal": journal,
        "metadata": metadata,
        "custom_references": [],
        "section_revisions": revisions,
    }
    path = project / "writing" / "author_input" / "manuscript_completion.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


@pytest.mark.parametrize(("case_id", "journal", "documentclass", "metadata"), JOURNAL_CASES)
def test_three_journal_completion_overlays_compile_real_pdf_and_apply(
    tmp_path: Path,
    case_id: str,
    journal: str,
    documentclass: str,
    metadata: dict[str, object],
) -> None:
    if not (shutil.which("xelatex") or shutil.which("pdflatex")):
        pytest.skip("A local LaTeX engine is required for the v0.31.0 PDF regression.")
    project = _project(tmp_path, journal, documentclass)
    packet = _packet(project, journal, metadata)

    preview = preview_manuscript_completion(project, packet)

    assert preview["status"] == "ready_for_human_review"
    preview_pdf = project / str(preview["preview_pdf"])
    assert preview_pdf.stat().st_size > 500
    assert len(PdfReader(str(preview_pdf)).pages) >= 1
    applied = apply_manuscript_completion(project, preview["packet_id"], preview["packet_hash"])
    assert applied["status"] == "applied"
    for index in (1, 2):
        section = "methods" if index == 1 else "discussion"
        assert f"Author-confirmed addition {index}." in (project / section / f"{section}.tex").read_text(encoding="utf-8")
