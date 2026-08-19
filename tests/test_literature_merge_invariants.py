from __future__ import annotations

import json

from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.references import normalize_reference_item, normalize_reference_items, write_reference_outputs


def _online_item() -> dict[str, object]:
    return {
        "title": "A stable multimodal benchmark",
        "authors": ["A. Author"],
        "year": "2024",
        "doi": "10.1000/stable-work",
        "abstract": "A benchmark with methods, data, and validation details.",
        "publication": "Test Journal",
        "source": "openalex",
        "citation_weight": 0.73,
        "relevance_score": 0.81,
        "journal_score": 0.65,
        "score_status": {
            "citation_weight": "computed",
            "relevance_score": "computed",
            "journal_score": "computed",
        },
        "score_provenance": {"policy_id": "dpl.reference_ranking.v1", "context_hash": "sha256:old"},
        "work_id": "doi:10.1000/stable-work",
        "document_parses": [{"input_sha256": "old-pdf", "work_id": "doi:10.1000/stable-work"}],
        "deep_summary": {"read_status": "metadata_abstract_only"},
        "code_source_ids": ["github:example/research"],
    }


def test_normalization_round_trip_preserves_identity_scores_and_extensions() -> None:
    original = _online_item()
    original["plugin_extension"] = {"discipline": "social_science", "role": "background"}

    normalized = normalize_reference_item(original, 0)

    assert normalized["work_id"] == "doi:10.1000/stable-work"
    assert normalized["citation_weight"] == 0.73
    assert normalized["relevance_score"] == 0.81
    assert normalized["journal_score"] == 0.65
    assert normalized["score_provenance"]["policy_id"] == "dpl.reference_ranking.v1"
    assert normalized["document_parses"][0]["input_sha256"] == "old-pdf"
    assert normalized["deep_summary"]["read_status"] == "metadata_abstract_only"
    assert normalized["code_source_ids"] == ["github:example/research"]
    assert normalized["plugin_extension"]["discipline"] == "social_science"


def test_online_and_local_records_merge_by_work_id_without_erasing_scores() -> None:
    online = _online_item()
    local = {
        "title": "A stable multimodal benchmark",
        "authors": ["A. Author"],
        "year": "2024",
        "doi": "10.1000/stable-work",
        "source": "local_folder",
        "source_type": "local_import",
        "reference_origin": "local_import",
        "local_file_id": "sha256:pdf",
        "pdf_read_status": "quick_read",
        "pdf_text_excerpt": "Methods and validation details from the local PDF.",
        "document_parses": [{"input_sha256": "new-pdf", "work_id": "doi:10.1000/stable-work"}],
    }

    merged = normalize_reference_items([online, local])

    assert len(merged) == 1
    assert merged[0]["work_id"] == "doi:10.1000/stable-work"
    assert merged[0]["citation_weight"] == 0.73
    assert merged[0]["relevance_score"] == 0.81
    assert merged[0]["journal_score"] == 0.65
    assert len(merged[0]["source_records"]) >= 2
    assert {row["input_sha256"] for row in merged[0]["document_parses"]} == {"old-pdf", "new-pdf"}


def test_missing_scores_are_not_materialized_as_zero_and_html_exposes_status(tmp_path) -> None:
    project = create_project(root=tmp_path / "projects", idea="A benchmark study", field="science").path
    item = {
        "title": "Curated source with no score yet",
        "authors": ["A. Curator"],
        "year": "2024",
        "doi": "10.1000/not-evaluated",
        "abstract": "A source retained for later evidence review.",
        "source": "manual",
        "reference_origin": "manual",
        "retained": True,
    }

    write_reference_outputs(project, [item], query="A benchmark study")

    stored = json.loads((project / "references" / "literature_items.json").read_text(encoding="utf-8"))[0]
    index = (project / "references" / "literature_summaries" / "index.html").read_text(encoding="utf-8")
    detail = next((project / "references" / "literature_summaries").glob("*.html"))
    detail_html = detail.read_text(encoding="utf-8")

    assert stored["citation_weight"] is None
    assert stored["score_status"]["citation_weight"] == "not_evaluated"
    assert "not evaluated" in index
    assert "not evaluated" in detail_html


def test_incremental_write_preserves_existing_record_and_snapshot(tmp_path) -> None:
    project = create_project(root=tmp_path / "projects", idea="A benchmark study", field="science").path
    write_reference_outputs(project, [_online_item()], query="A benchmark study")
    first_snapshot = json.loads((project / "references" / "literature_snapshot.json").read_text(encoding="utf-8"))
    first_items = json.loads((project / "references" / "literature_items.json").read_text(encoding="utf-8"))
    first_score = next(item["citation_weight"] for item in first_items if item["work_id"] == "doi:10.1000/stable-work")

    local = {
        "title": "A local supplemental method",
        "authors": ["B. Local"],
        "year": "2025",
        "doi": "10.1000/local-method",
        "abstract": "A local PDF supplies a complementary method description.",
        "source": "local_folder",
        "source_type": "local_import",
        "reference_origin": "local_import",
        "retained": True,
        "pdf_text_excerpt": "A local PDF supplies a complementary method description.",
    }
    write_reference_outputs(project, [local], query="A benchmark study")

    items = json.loads((project / "references" / "literature_items.json").read_text(encoding="utf-8"))
    by_work = {item["work_id"]: item for item in items}
    second_snapshot = json.loads((project / "references" / "literature_snapshot.json").read_text(encoding="utf-8"))
    merge_report = json.loads((project / "references" / "literature_merge_report.json").read_text(encoding="utf-8"))

    assert "doi:10.1000/stable-work" in by_work
    assert by_work["doi:10.1000/stable-work"]["citation_weight"] == first_score
    assert "doi:10.1000/local-method" in by_work
    assert second_snapshot["snapshot_hash"] != first_snapshot["snapshot_hash"]
    assert merge_report["baseline_count"] == 1
    assert merge_report["dropped_work_ids"] == []
