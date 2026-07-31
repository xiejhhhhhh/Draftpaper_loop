from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from draftpaper_cli.literature_coverage import review_literature_coverage
from draftpaper_cli.literature_search import search_literature_for_project
from draftpaper_cli.literature_sources import collect_registered_sources, register_literature_source
from draftpaper_cli.mineru_adapter import parse_literature_document
from draftpaper_cli.project_scaffold import create_project


def _reference(title: str, doi: str, source: str = "openalex") -> dict[str, object]:
    return {
        "title": title,
        "authors": ["Test Author"],
        "year": "2024",
        "doi": doi,
        "abstract": "A dataset method benchmark and limitation study.",
        "publication": "Test Journal",
        "source": source,
    }


def test_search_aggregates_json_zotero_local_and_online_sources() -> None:
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        project = create_project(root=root / "projects", idea="Image classification", field="machine learning").path
        local_file = root / "local.json"
        local_file.write_text(json.dumps([_reference("Local source", "10.1000/local", "local_file")]), encoding="utf-8")
        register_literature_source(project, source_type="structured_file", path=local_file)
        json_file = root / "manual.json"
        json_file.write_text(json.dumps([_reference("Manual source", "10.1000/manual", "manual")]), encoding="utf-8")
        zotero = dict(_reference("Zotero source", "10.1000/zotero", "zotero_collection"), reference_origin="existing_zotero")
        online = _reference("Online source", "10.1000/online", "openalex")
        with patch("draftpaper_cli.literature_search.fetch_zotero_collection_items", return_value=([zotero], {"status": "loaded", "matched_collection": "C", "usable_item_count": 1})), patch(
            "draftpaper_cli.literature_search.search_free_literature", return_value=[]
        ), patch("draftpaper_cli.literature_search.search_provider_router", return_value=([online], {"status": "loaded"})), patch(
            "draftpaper_cli.literature_search.enrich_with_paper_fetch", side_effect=lambda project_path, items: (items, {})
        ):
            search_literature_for_project(project, from_json=json_file, zotero_collection="C", zotero_supplement=False, include_online=True)
        items = json.loads((project / "references" / "literature_items.json").read_text(encoding="utf-8"))
        assert {item["title"] for item in items} == {"Local source", "Manual source", "Zotero source", "Online source"}
        source_categories = {category for item in items for category in item["source_records"][0].get("source_type", "").split("|")}
        assert {"local_import", "manual", "zotero", "online_search"} <= source_categories
        index = (project / "references" / "literature_summaries" / "index.html").read_text(encoding="utf-8")
        assert "online_search" in index
        assert "local_import" in index
        assert "zotero" in index


def test_coverage_report_is_role_based_and_non_destructive() -> None:
    with TemporaryDirectory() as temporary:
        project = create_project(root=Path(temporary) / "projects", idea="A study", field="science").path
        references = project / "references" / "literature_items.json"
        references.write_text(json.dumps([_reference("Data benchmark limitation", "10.1000/a")]), encoding="utf-8")
        report = review_literature_coverage(project)
        assert report["status"] == "review_required"
        assert "data_provenance" in report["gaps"]
        assert (project / "references" / "literature_coverage.md").is_file()


def test_mineru_adapter_falls_back_to_pypdf_without_mineru() -> None:
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        project = create_project(root=root / "projects", idea="PDF parsing", field="science").path
        pdf = root / "paper.pdf"
        pdf.write_bytes(b"%PDF-1.4 test")
        with patch("draftpaper_cli.mineru_adapter.shutil.which", return_value=None), patch("draftpaper_cli.mineru_adapter._extract_pdf_text_from_path", return_value="abstract and references"):
            result = parse_literature_document(project, pdf)
        assert result["status"] == "fallback"
        assert result["receipt"]["parser"] == "pypdf"
        assert result["receipt"]["bibliography_auto_citation"] is False


def test_local_structured_source_keeps_file_metadata_and_identifier_tiers(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "projects", idea="Identity test", field="science").path
    source = tmp_path / "library.json"
    source.write_text(
        json.dumps([{"title": "Same work", "authors": ["A. Author"], "year": 2024, "pmid": "12345"}]),
        encoding="utf-8",
    )
    register_literature_source(project, source_type="structured_file", path=source)
    from draftpaper_cli.literature_sources import collect_registered_sources

    items, report = collect_registered_sources(project)
    assert report["item_count"] == 1
    item = items[0]
    assert item["local_file_id"]
    assert item["local_file_size"] == source.stat().st_size
    assert item["local_logical_path"] == source.name
    assert item["pmid"] == "12345"
    assert item["source_records"][0]["file_id"] == item["local_file_id"]


def test_reference_identity_uses_identifier_then_title_author_year(tmp_path: Path) -> None:
    from draftpaper_cli.references import normalize_reference_items

    merged = normalize_reference_items([
        {"title": "A work", "authors": ["A. Author"], "year": 2024, "arxiv_id": "2401.00001", "source": "arxiv"},
        {"title": "A work", "authors": ["A. Author"], "year": 2024, "arxiv_id": "2401.00001", "source": "zotero_collection", "retained": True},
    ])
    assert len(merged) == 1
    assert merged[0]["retained"] is True
    distinct = normalize_reference_items([
        {"title": "A work", "authors": ["A. Author"], "year": 2024},
        {"title": "A work", "authors": ["B. Author"], "year": 2024},
    ])
    assert len(distinct) == 2


def test_local_pdf_copy_is_hash_addressed_inside_project(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "projects", idea="PDF source", field="science").path
    source_root = tmp_path / "papers"
    source_root.mkdir()
    paper = source_root / "paper.pdf"
    paper.write_bytes(b"%PDF-1.4 not a complete PDF")
    register_literature_source(project, source_type="local_folder", path=source_root, copy_attachments=True)
    items, _ = collect_registered_sources(project)
    assert len(items) == 1
    attachment = project / items[0]["local_attachment_path"]
    assert attachment.is_file()
    assert attachment.read_bytes() == paper.read_bytes()
    assert str(project) not in items[0]["local_logical_path"]
