from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pypdf import PdfWriter

from draftpaper_cli import literature_merge
from draftpaper_cli.literature_integrity import (
    audit_literature_integrity,
    quarantine_orphan_literature_artifacts,
    rollback_orphan_literature_quarantine,
)
from draftpaper_cli.literature_merge import build_literature_merge_preview, apply_literature_merge
from draftpaper_cli.literature_migration import (
    apply_literature_migration,
    build_literature_migration_preview,
    rollback_literature_migration,
)
from draftpaper_cli.literature_sources import parse_registered_literature_documents, register_literature_source
from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.references import write_reference_outputs


def _legacy_index() -> str:
    return """<!doctype html>
<html><body><table>
<thead><tr><th>#</th><th>Title</th><th>Citation key</th><th>Source categories</th><th>PDF/parser</th><th>Citation weight</th><th>Relevance</th><th>Journal authority</th></tr></thead>
<tbody>
<tr><td>1</td><td><a href=\"01_alpha.html\">Alpha paper</a></td><td>Alpha2024</td><td>manual</td><td>quick_read</td><td>0</td><td>0</td><td>0</td></tr>
<tr><td>2</td><td><a href=\"02_beta.html\">Beta paper</a></td><td>Beta2023</td><td>zotero</td><td>not_parsed</td><td>0</td><td>0</td><td>0</td></tr>
</tbody></table></body></html>"""


def test_legacy_index_migration_is_previewed_hash_bound_and_rollbackable(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "projects", idea="Legacy index", field="science").path
    summary_dir = project / "references" / "literature_summaries"
    summary_dir.mkdir(parents=True, exist_ok=True)
    (summary_dir / "index.html").write_text(_legacy_index(), encoding="utf-8")
    old_items = [
        {"title": "Alpha paper", "authors": ["A. Author"], "year": "2024", "bibtex_key": "Alpha2024", "citation_weight": 0.0, "relevance_score": 0.0, "journal_score": 0.0, "score_status": {"citation_weight": "computed", "relevance_score": "computed", "journal_score": "computed"}},
        {"title": "Beta paper", "authors": ["B. Author"], "year": "2023", "bibtex_key": "Beta2023", "citation_weight": 0.0, "relevance_score": 0.0, "journal_score": 0.0, "score_status": {"citation_weight": "computed", "relevance_score": "computed", "journal_score": "computed"}},
    ]
    (project / "references" / "literature_items.json").write_text(json.dumps(old_items), encoding="utf-8")

    preview = build_literature_migration_preview(project)

    assert preview["index_row_count"] == 2
    assert preview["proposed_item_count"] == 2
    assert preview["legacy_zero_ambiguous_count"] == 2
    assert preview["packet_hash"].startswith("sha256:")
    applied = apply_literature_migration(project, packet_hash=preview["packet_hash"])
    assert applied["status"] == "applied"
    migrated = json.loads((project / "references" / "literature_items.json").read_text(encoding="utf-8"))
    assert all(item["citation_weight"] is None for item in migrated)
    assert all(item["score_status"]["citation_weight"] == "legacy_zero_ambiguous" for item in migrated)

    rolled_back = rollback_literature_migration(project)

    assert rolled_back["status"] == "rolled_back"
    restored = json.loads((project / "references" / "literature_items.json").read_text(encoding="utf-8"))
    assert [item["citation_weight"] for item in restored] == [0.0, 0.0]


def test_orphan_quarantine_has_hash_checked_rollback(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "projects", idea="Orphan test", field="science").path
    write_reference_outputs(
        project,
        [{"title": "Active source", "authors": ["Author"], "year": "2024", "doi": "10.1000/active", "abstract": "Active evidence."}],
        query="Orphan test",
    )
    fulltext = project / "references" / "fulltext"
    fulltext.mkdir(parents=True, exist_ok=True)
    orphan = fulltext / "foreign.json"
    orphan.write_text(json.dumps({"doi": "10.1000/foreign", "title": "Foreign source"}), encoding="utf-8")
    audit = audit_literature_integrity(project)
    assert audit["orphan_count"] == 1

    moved = quarantine_orphan_literature_artifacts(project)

    assert moved["moved_count"] == 1
    assert not orphan.exists()
    restored = rollback_orphan_literature_quarantine(project)
    assert restored["status"] == "rolled_back"
    assert orphan.is_file()


def test_merge_transaction_restores_reference_tree_on_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = create_project(root=tmp_path / "projects", idea="Merge transaction", field="science").path
    write_reference_outputs(
        project,
        [{"title": "Baseline source", "authors": ["Author"], "year": "2024", "doi": "10.1000/baseline", "abstract": "Baseline evidence."}],
        query="Merge transaction",
    )
    references = project / "references"
    before = {name: (references / name).read_bytes() for name in ("literature_items.json", "literature_snapshot.json", "library.bib")}
    preview = build_literature_merge_preview(
        project,
        incoming=[{"title": "Incoming source", "authors": ["Author"], "year": "2025", "doi": "10.1000/incoming", "abstract": "Incoming evidence."}],
    )

    def fail_registry(*_args, **_kwargs):
        raise RuntimeError("injected registry failure")

    monkeypatch.setattr(literature_merge, "write_literature_registry", fail_registry)
    with pytest.raises(RuntimeError, match="injected registry failure"):
        apply_literature_merge(project, packet_hash=preview["packet_hash"])

    assert {name: (references / name).read_bytes() for name in before} == before
    receipt = json.loads((references / "literature_merge_receipt.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "rolled_back"


def test_registered_pdf_batch_reuses_pypdf_cache(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "projects", idea="PDF batch", field="science").path
    source_root = tmp_path / "pdfs"
    source_root.mkdir()
    pdf = source_root / "source.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with pdf.open("wb") as handle:
        writer.write(handle)
    file_id = hashlib.sha256(pdf.read_bytes()).hexdigest()
    register_literature_source(project, source_type="local_folder", path=source_root)
    write_reference_outputs(
        project,
        [{
            "title": "Local source",
            "authors": ["Author"],
            "year": "2024",
            "doi": "10.1000/local",
            "abstract": "Local PDF evidence.",
            "source": "local_folder",
            "source_type": "local_import",
            "reference_origin": "local_import",
            "retained": True,
            "local_file_id": file_id,
            "pdf_path": str(pdf),
        }],
        query="PDF batch",
    )

    first = parse_registered_literature_documents(project, use_mineru=False)
    second = parse_registered_literature_documents(project, use_mineru=False)

    assert first["document_count"] == 1
    assert second["document_count"] == 1
    report = json.loads((project / "references" / "document_parse_batch_report.json").read_text(encoding="utf-8"))
    assert report["results"][0]["cache_hit"] is True
    assert report["status_counts"].get("cached") == 1
