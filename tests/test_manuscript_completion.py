from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from draftpaper_cli.manuscript_completion import (
    ManuscriptCompletionError,
    apply_manuscript_completion,
    manuscript_completion_status,
    prepare_manuscript_completion,
    preview_manuscript_completion,
    rollback_manuscript_completion,
)
from draftpaper_cli.project_scaffold import create_project


@pytest.fixture
def compiled_completion_preview(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep transaction tests independent of an optional local LaTeX install."""

    def fake_build_preview_pdf(
        root: Path,
        packet_dir: Path,
        *,
        candidate_latex: Path,
    ) -> dict[str, str | None]:
        return {
            "status": "passed",
            "pdf": None,
            "engine": "test-fixture",
            "sha256": "test-fixture-pdf-sha256",
        }

    monkeypatch.setattr(
        "draftpaper_cli.manuscript_completion._build_completion_preview_pdf",
        fake_build_preview_pdf,
    )


def _project(tmp_path: Path) -> Path:
    project = create_project(root=tmp_path, idea="Completion test", field="astronomy").path
    sections = {
        "introduction": "\\section{Introduction}\n\nIntroduction paragraph.\n",
        "data": "\\section{Data}\n\nData paragraph.\n",
        "methods": "\\section{Methods}\n\nMethods paragraph.\n",
        "results": "\\section{Results}\n\nResult paragraph with F1=0.82.\n",
        "discussion": "\\section{Discussion}\n\nDiscussion paragraph.\n",
    }
    for section, text in sections.items():
        path = project / section / f"{section}.tex"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    (project / "references" / "library.bib").write_text(
        "@article{Existing2026, author={A. Author}, title={Existing}, year={2026}}\n",
        encoding="utf-8",
    )
    return project


def _packet(project: Path, *, expected_text: str = "Methods paragraph.") -> Path:
    path = project.parent / "completion.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "dpl.manuscript_completion.v1",
                "project_id": json.loads((project / "project.json").read_text(encoding="utf-8"))["project_id"],
                "metadata": {
                    "title": "Completed title",
                    "abstract": "A bounded completion abstract.",
                    "authors": [{"name": "Alice Example", "affiliations": ["inst1"], "corresponding": True}],
                    "affiliations": [{"id": "inst1", "name": "Institute of Tests"}],
                    "acknowledgments": "We thank the survey team.",
                    "data_availability": "Data are available from the archive.",
                    "code_availability": "Code is available from the repository.",
                },
                "custom_references": [
                    {
                        "citation_key": "Custom2026",
                        "title": "A custom source",
                        "authors": ["A. Researcher"],
                        "year": 2026,
                        "journal": "Journal of Tests",
                        "doi": "10.1234/example",
                        "evidence_notes": "Supports the comparison boundary.",
                    }
                ],
                "section_revisions": [
                    {
                        "revision_key": "methods-add-note",
                        "target": {
                            "file": "latex/sections/methods.tex",
                            "section": "methods",
                            "line_start_hint": 1,
                            "line_end_hint": 2,
                            "expected_text": expected_text,
                        },
                        "operation": "insert_after",
                        "mode": "exact_text",
                        "content": "The implementation was independently checked.",
                    }
                ],
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def test_prepare_completion_writes_template_and_missing_report(tmp_path: Path) -> None:
    project = _project(tmp_path)
    result = prepare_manuscript_completion(project)
    assert result["status"] == "template_written"
    assert (project / "writing" / "manuscript_completion" / "template.yaml").is_file()
    report = json.loads((project / "writing" / "manuscript_completion" / "missing_fields.json").read_text(encoding="utf-8"))
    assert "authors" in report["missing_required"]


def test_preview_and_apply_completion_is_batch_transaction(
    tmp_path: Path,
    compiled_completion_preview: None,
) -> None:
    project = _project(tmp_path)
    packet = _packet(project)
    preview = preview_manuscript_completion(project, packet)
    assert preview["status"] == "ready_for_human_review"
    assert preview["resolved_revisions"] == 1
    assert "Completed title" not in (project / "writing" / "manuscript_metadata.yaml").read_text(encoding="utf-8") if (project / "writing" / "manuscript_metadata.yaml").is_file() else True

    applied = apply_manuscript_completion(project, preview["packet_id"], preview["packet_hash"])
    assert applied["status"] == "applied"
    assert "Completed title" in (project / "writing" / "manuscript_metadata.yaml").read_text(encoding="utf-8")
    assert "independently checked" in (project / "methods" / "methods.tex").read_text(encoding="utf-8")
    assert "Custom2026" in (project / "references" / "library.bib").read_text(encoding="utf-8")
    status = manuscript_completion_status(project)
    assert status["status"] == "applied"
    assert (project / "writing" / "manuscript_completion" / "active_completion_manifest.json").is_file()


def test_completion_rejects_line_only_and_stale_content(tmp_path: Path) -> None:
    project = _project(tmp_path)
    path = project.parent / "line_only.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "dpl.manuscript_completion.v1",
                "project_id": json.loads((project / "project.json").read_text(encoding="utf-8"))["project_id"],
                "metadata": {},
                "section_revisions": [{"revision_key": "unsafe", "section": "methods", "line_start": 1, "line_end": 2, "content": "x"}],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    with pytest.raises(ManuscriptCompletionError, match="Unsupported section_revisions.*line_end"):
        preview_manuscript_completion(project, path)

    stale = _packet(project, expected_text="Different paragraph.")
    with pytest.raises(ManuscriptCompletionError, match="expected_text does not match"):
        preview_manuscript_completion(project, stale)


def test_completion_rollback_requires_unchanged_after_hashes(
    tmp_path: Path,
    compiled_completion_preview: None,
) -> None:
    project = _project(tmp_path)
    preview = preview_manuscript_completion(project, _packet(project))
    applied = apply_manuscript_completion(project, preview["packet_id"], preview["packet_hash"])
    (project / "methods" / "methods.tex").write_text(
        (project / "methods" / "methods.tex").read_text(encoding="utf-8") + "Later author edit.\n",
        encoding="utf-8",
    )
    with pytest.raises(ManuscriptCompletionError, match="artifact changed after completion"):
        rollback_manuscript_completion(project, preview["packet_id"])
    assert applied["status"] == "applied"


def test_completion_preserves_scientific_evidence_boundary(tmp_path: Path) -> None:
    project = _project(tmp_path)
    packet = _packet(project)
    payload = yaml.safe_load(packet.read_text(encoding="utf-8"))
    payload["section_revisions"][0]["change_class"] = "scientific_evidence_change"
    packet.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    preview = preview_manuscript_completion(project, packet)
    with pytest.raises(ManuscriptCompletionError, match="Scientific evidence changes"):
        apply_manuscript_completion(project, preview["packet_id"], preview["packet_hash"])
