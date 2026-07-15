from __future__ import annotations

import json
from pathlib import Path

from draftpaper_cli.bibliography import (
    BibliographyError,
    build_reference_registry,
    inspect_reference_duplicates,
    render_reference_proof,
    resolve_reference_version,
    validate_bibliography,
)
from draftpaper_cli.latex_assembly import _render_main, _write_pdf_manifest
from draftpaper_cli.project_scaffold import create_project


def _project(tmp_path: Path) -> Path:
    project = create_project(root=tmp_path, idea="Bibliography contract", field="astronomy", target_journal="APJS").path
    (project / "journal_profile" / "journal_profile.json").write_text(
        json.dumps({"target_journal": "APJS", "documentclass": "aastex701", "bibliography_style": "aasjournalv7"}),
        encoding="utf-8",
    )
    (project / "references" / "library.bib").write_text(
        """@article{Published2024,
  author = {Garc{\\'i}a, Ana and Smith, J.},
  title = {{Time2Vec} and {X-rays}: a {GECAM} study},
  year = {2024},
  journal = {The Astrophysical Journal Supplement Series},
  volume = {271},
  number = {2},
  pages = {42},
  doi = {https://doi.org/10.1234/EXAMPLE.42},
  url = {http://www.semanticscholar.org/paper/example}
}

@misc{Preprint2024,
  author = {Garc{\\'i}a, Ana and Smith, J.},
  title = {Time2Vec and X-rays: a GECAM study},
  year = {2024},
  eprint = {2401.01234},
  archivePrefix = {arXiv},
  primaryClass = {astro-ph.HE},
  url = {https://arxiv.org/abs/2401.01234}
}
""",
        encoding="utf-8",
    )
    return project


def test_registry_parses_nested_bibtex_and_requires_version_confirmation(tmp_path: Path) -> None:
    project = _project(tmp_path)

    result = build_reference_registry(project)
    registry = json.loads((project / "references" / "reference_registry.json").read_text(encoding="utf-8"))
    duplicate = inspect_reference_duplicates(project)

    assert result["version_confirmation_required"] is True
    assert registry["record_count"] == 2
    published = next(item for item in registry["records"] if item["citation_key"] == "Published2024")
    assert published["doi_normalized"] == "10.1234/example.42"
    assert published["canonical_url"] == "https://doi.org/10.1234/example.42"
    assert "{Time2Vec}" in published["title_bibtex_protected"]
    assert published["structured_authors"][0]["family"] == "Garc{\\'i}a"
    assert duplicate["status"] == "confirmation_required"
    assert duplicate["duplicate_work_count"] == 1


def test_explicit_version_resolution_renders_only_confirmed_citable_work(tmp_path: Path) -> None:
    project = _project(tmp_path)
    build_reference_registry(project)
    registry = json.loads((project / "references" / "reference_registry.json").read_text(encoding="utf-8"))
    work_id = registry["records"][0]["canonical_work_id"]

    resolved = resolve_reference_version(project, work_id, "Published2024")
    bib = (project / "references" / "library.bib").read_text(encoding="utf-8")
    duplicate = inspect_reference_duplicates(project)
    quality = validate_bibliography(project)
    proof = render_reference_proof(project)

    assert resolved["rendered_reference_count"] == 1
    assert "@article{Published2024" in bib
    assert "Preprint2024" not in bib
    assert duplicate["status"] == "passed"
    assert quality["status"] == "passed"
    assert proof["status"] == "written"
    html = (project / "quality_checks" / "reference_proof.html").read_text(encoding="utf-8")
    assert 'href="https://doi.org/10.1234/example.42"' in html


def test_journal_profile_overrides_hardcoded_template_bibliography_style(tmp_path: Path) -> None:
    project = _project(tmp_path)
    for section in ("introduction", "data", "methods", "results", "discussion"):
        target = project / section / f"{section}.tex"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"\\section{{{section.title()}}}\nTest prose.\n", encoding="utf-8")
    template = project / "latex" / "template" / "main.tex"
    template.write_text(
        "\\documentclass{aastex701}\n\\begin{document}\n%%DRAFTPAPER_SECTIONS%%\n"
        "\\bibliographystyle{aasjournal}\n\\bibliography{library}\n\\end{document}\n",
        encoding="utf-8",
    )
    metadata = json.loads((project / "project.json").read_text(encoding="utf-8"))

    rendered = _render_main(project, metadata)

    assert rendered.count("\\bibliographystyle{") == 1
    assert "\\bibliographystyle{aasjournalv7}" in rendered
    assert "\\bibliographystyle{aasjournal}" not in rendered
    assert rendered.index("\\bibliographystyle{aasjournalv7}") < rendered.index("\\bibliography{library}")


def test_bibliography_validation_separates_format_failure_from_citation_support(tmp_path: Path) -> None:
    project = create_project(root=tmp_path, idea="Incomplete metadata", field="medicine", target_journal="Test").path
    (project / "journal_profile" / "journal_profile.json").write_text(
        json.dumps({"documentclass": "article", "bibliography_style": "plainnat"}), encoding="utf-8"
    )
    (project / "references" / "library.bib").write_text(
        "@article{Incomplete,title={A clinical result},author={Doe, A.},year={2025},journal={Journal}}\n",
        encoding="utf-8",
    )

    build_reference_registry(project)
    report = validate_bibliography(project)

    assert report["status"] == "failed"
    assert any(item["kind"] == "missing_publication_locator" for item in report["issues"])
    assert report["citation_support_audit"].startswith("separate:")


def test_continuous_publication_journal_accepts_url_without_volume_or_pages(tmp_path: Path) -> None:
    project = create_project(root=tmp_path, idea="Continuous publication", field="machine learning", target_journal="Test").path
    (project / "journal_profile" / "journal_profile.json").write_text(
        json.dumps({"documentclass": "article", "bibliography_style": "plainnat"}), encoding="utf-8"
    )
    (project / "references" / "library.bib").write_text(
        "@article{Continuous2024,author={Doe, A.},title={A continuous article},year={2024},"
        "journal={Transactions on Machine Learning Research},url={https://openreview.net/forum?id=example}}\n",
        encoding="utf-8",
    )

    build_reference_registry(project)
    report = validate_bibliography(project)

    assert report["status"] == "passed"
    assert not any(item["kind"] == "missing_required_field" for item in report["issues"])


def test_registry_merges_explicit_supplemental_bibliography_with_provenance(tmp_path: Path) -> None:
    project = _project(tmp_path)
    (project / "references" / "supplemental_library.bib").write_text(
        "@article{Comparison2020,author={Doe, Jane},title={Independent comparison},year={2020},"
        "journal={Test Journal},doi={10.1234/comparison},url={https://doi.org/10.1234/comparison}}\n",
        encoding="utf-8",
    )

    result = build_reference_registry(project)
    registry = json.loads((project / "references" / "reference_registry.json").read_text(encoding="utf-8"))
    merge = json.loads((project / "references" / "supplemental_bibliography_merge_report.json").read_text(encoding="utf-8"))

    assert result["record_count"] == 3
    comparison = next(item for item in registry["records"] if item["citation_key"] == "Comparison2020")
    assert "supplemental_library.bib" in comparison["metadata_sources"]
    assert merge["status"] == "passed"
    assert merge["accepted_supplemental_keys"] == ["Comparison2020"]


def test_supplemental_bibliography_rejects_doi_alias_conflict(tmp_path: Path) -> None:
    project = _project(tmp_path)
    (project / "references" / "supplemental_library.bib").write_text(
        "@article{Alias2024,author={Doe, Jane},title={Alias},year={2024},journal={Test},"
        "doi={10.1234/example.42}}\n",
        encoding="utf-8",
    )

    try:
        build_reference_registry(project)
    except BibliographyError as exc:
        assert "Alias2024" in str(exc)
    else:
        raise AssertionError("A DOI alias conflict must not be silently merged.")


def test_compile_manifest_records_profile_tex_aux_and_bbl_style_evidence(tmp_path: Path) -> None:
    project = _project(tmp_path)
    (project / "latex" / "main.tex").write_text(
        "\\documentclass{aastex701}\n\\bibliographystyle{aasjournalv7}\n\\bibliography{library}\n",
        encoding="utf-8",
    )
    (project / "latex" / "main.aux").write_text("\\bibstyle{aasjournalv7}\n", encoding="utf-8")
    (project / "latex" / "main.bbl").write_text("\\begin{thebibliography}{1}\n", encoding="utf-8")

    _write_pdf_manifest(project, {"status": "success"})
    manifest = json.loads((project / "latex" / "pdf_compile_manifest.json").read_text(encoding="utf-8"))

    assert manifest["bibliography"]["profile_style"] == "aasjournalv7"
    assert manifest["bibliography"]["main_tex_styles"] == ["aasjournalv7"]
    assert manifest["bibliography"]["aux_styles"] == ["aasjournalv7"]
    assert manifest["bibliography"]["bbl_sha256"]
