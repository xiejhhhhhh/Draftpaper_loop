from __future__ import annotations

from pathlib import Path

import pytest

from draftpaper_cli import revision_transaction
from draftpaper_cli.latex_assembly import _copy_sections, _read_sections
from draftpaper_cli.manuscript_artifacts import SECTION_CANONICAL_ARTIFACTS
from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.project_state import load_project


def _paper_project(tmp_path: Path) -> Path:
    project = create_project(root=tmp_path, idea="Atomic manuscript revision", field="astronomy").path
    for section, relative in SECTION_CANONICAL_ARTIFACTS.items():
        path = project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"Old {section}.\n", encoding="utf-8")
    derived = project / "latex" / "sections" / "methods.tex"
    derived.parent.mkdir(parents=True, exist_ok=True)
    derived.write_text("Old derived methods.\n", encoding="utf-8")
    return project


def _install_passing_revision_mocks(monkeypatch: pytest.MonkeyPatch) -> None:
    def submit(project: Path, section: str, source: Path) -> dict[str, object]:
        text = Path(source).read_text(encoding="utf-8")
        candidate = Path(project) / "writing" / "candidates" / f"{section}.tex"
        draft = Path(project) / "writing" / "drafts" / f"{section}.tex"
        candidate.parent.mkdir(parents=True, exist_ok=True)
        draft.parent.mkdir(parents=True, exist_ok=True)
        candidate.write_text(text, encoding="utf-8")
        draft.write_text(text, encoding="utf-8")
        return {"decision": "pass", "candidate_hash": "test"}

    monkeypatch.setattr(revision_transaction, "submit_section_draft", submit)
    monkeypatch.setattr(
        revision_transaction,
        "prepare_scientific_editor",
        lambda project, section, source: {"decision": "pass", "source_hash": "test"},
    )
    monkeypatch.setattr(
        revision_transaction,
        "accept_section_draft",
        lambda project, section: {"decision": "accepted", "formal_release_eligible": True},
    )


def test_revision_installs_canonical_source_and_survives_assembly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = _paper_project(tmp_path)
    source = tmp_path / "revised_methods.tex"
    source.write_text("Revised canonical methods.\n", encoding="utf-8")
    _install_passing_revision_mocks(monkeypatch)

    result = revision_transaction.apply_section_revision(
        project, "methods", source, change_class="citation_local"
    )

    assert result["decision"] == "committed"
    assert result["canonical_artifact"] == "methods/methods.tex"
    assert (project / "methods" / "methods.tex").read_text(encoding="utf-8") == "Revised canonical methods.\n"
    assert (project / "latex" / "sections" / "methods.tex").read_text(encoding="utf-8") == "Old derived methods.\n"
    state = load_project(project)
    assert state.metadata["stages"]["latex"]["stale"] is True
    assert state.metadata["stages"]["quality_checks"]["stale"] is True
    assert state.metadata["stages"]["methods_writing"]["stale"] is True

    _copy_sections(project, _read_sections(project))
    assert (project / "latex" / "sections" / "methods.tex").read_text(encoding="utf-8") == "Revised canonical methods.\n"


def test_revision_rolls_back_canonical_candidate_and_state_on_late_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _paper_project(tmp_path)
    source = tmp_path / "revised_methods.tex"
    source.write_text("Revision that must roll back.\n", encoding="utf-8")
    _install_passing_revision_mocks(monkeypatch)
    before_project = (project / "project.json").read_bytes()
    real_record = revision_transaction.record_artifact_change

    def fail_after_stale(*args, **kwargs):
        real_record(*args, **kwargs)
        raise RuntimeError("injected receipt failure")

    monkeypatch.setattr(revision_transaction, "record_artifact_change", fail_after_stale)

    with pytest.raises(RuntimeError, match="injected receipt failure"):
        revision_transaction.apply_section_revision(
            project, "methods", source, change_class="citation_local"
        )

    assert (project / "methods" / "methods.tex").read_text(encoding="utf-8") == "Old methods.\n"
    assert not (project / "writing" / "candidates" / "methods.tex").exists()
    assert (project / "project.json").read_bytes() == before_project
    assert load_project(project).metadata["stages"]["latex"]["stale"] is False


def test_editor_repair_does_not_stale_or_replace_canonical_section(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _paper_project(tmp_path)
    source = tmp_path / "revised_methods.tex"
    source.write_text("Candidate needing repair.\n", encoding="utf-8")
    _install_passing_revision_mocks(monkeypatch)
    monkeypatch.setattr(
        revision_transaction,
        "prepare_scientific_editor",
        lambda project, section, source: {"decision": "revise", "tasks": [{"kind": "repair"}]},
    )

    result = revision_transaction.apply_section_revision(project, "methods", source)

    assert result["decision"] == "editor_repair_required"
    assert (project / "methods" / "methods.tex").read_text(encoding="utf-8") == "Old methods.\n"
    assert (project / "writing" / "candidates" / "methods.tex").is_file()
    assert load_project(project).metadata["stages"]["latex"]["stale"] is False


def test_change_classifier_compares_citation_keys_not_surrounding_prose() -> None:
    before = "Earlier prose \\citep{Alpha2020}."
    after = "Narrower prose with the same source \\citep{Alpha2020}."
    changed_citation = "Narrower prose \\citep{Beta2021}."

    assert revision_transaction._classify(before, after, None) == "prose_only"
    assert revision_transaction._classify(before, changed_citation, None) == "citation_change"
