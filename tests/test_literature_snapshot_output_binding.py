from __future__ import annotations

import hashlib
import json
from pathlib import Path

from draftpaper_cli.document_parse_binding import bind_document_parse
from draftpaper_cli.literature_integrity import audit_literature_integrity
from draftpaper_cli.literature_merge import rebuild_literature_index
from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.references import write_reference_outputs


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _write_one(project: Path) -> None:
    write_reference_outputs(
        project,
        [{
            "title": "Snapshot-bound evidence paper",
            "authors": ["A. Author"],
            "year": "2024",
            "doi": "10.1000/snapshot-bound",
            "abstract": "A reproducible methods and data study.",
            "publication": "Test Journal",
            "source": "openalex",
        }],
        query="snapshot-bound evidence",
    )


def test_all_reference_projections_share_one_snapshot_and_manifest_hashes(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "projects", idea="Snapshot binding", field="science").path
    _write_one(project)

    references = project / "references"
    snapshot = json.loads((references / "literature_snapshot.json").read_text(encoding="utf-8"))
    snapshot_hash = snapshot["snapshot_hash"]
    items = json.loads((references / "literature_items.json").read_text(encoding="utf-8"))
    assert items[0]["snapshot_hash"] == snapshot_hash
    assert f"Draftpaper-literature-snapshot: {snapshot_hash}" in (references / "library.bib").read_text(encoding="utf-8")
    assert f"Snapshot hash: `{snapshot_hash}`" in (references / "literature_review_notes.md").read_text(encoding="utf-8")
    assert f'name="draftpaper-snapshot-hash" content="{snapshot_hash}"' in (references / "literature_review_notes.html").read_text(encoding="utf-8")
    html_files = sorted((references / "literature_summaries").glob("*.html"))
    assert html_files
    assert all(f'data-snapshot-hash="{snapshot_hash}"' in path.read_text(encoding="utf-8") for path in html_files)

    evidence_sidecar = json.loads((references / "citation_evidence_snapshot.json").read_text(encoding="utf-8"))
    assert evidence_sidecar["snapshot_hash"] == snapshot_hash
    assert evidence_sidecar["csv_sha256"] == _sha256(references / "citation_evidence.csv")

    for relative in ("literature_work_registry.json", "reference_registry.json", "bibliography_contract.json"):
        payload = json.loads((references / relative).read_text(encoding="utf-8"))
        assert payload["snapshot_hash"] == snapshot_hash

    manifest = json.loads((references / "literature_output_manifest.json").read_text(encoding="utf-8"))
    assert manifest["snapshot_hash"] == snapshot_hash
    corpus = json.loads((references / "literature_teaching_corpus_manifest.json").read_text(encoding="utf-8"))
    assert corpus["snapshot_hash"] == snapshot_hash
    for artifact in manifest["artifacts"]:
        path = project / artifact["path"]
        assert path.is_file()
        assert artifact["sha256"] == _sha256(path)
        assert artifact["snapshot_hash"] == snapshot_hash

    audit = audit_literature_integrity(project)
    assert audit["status"] == "passed"
    assert audit["snapshot_binding"]["status"] == "passed"


def test_output_hash_drift_is_detected_without_rewriting_the_project(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "projects", idea="Snapshot drift", field="science").path
    _write_one(project)
    detail = next(path for path in (project / "references" / "literature_summaries").glob("*.html") if path.name != "index.html")
    detail.write_text(detail.read_text(encoding="utf-8") + "\n<!-- drift -->\n", encoding="utf-8")

    audit = audit_literature_integrity(project)
    assert audit["status"] == "review_required"
    assert any(issue.startswith("output_hash_mismatch:") for issue in audit["snapshot_binding"]["issues"])


def test_parse_bind_and_rebuild_refresh_every_projection_without_snapshot_drift(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "projects", idea="Parse binding", field="science").path
    _write_one(project)
    references = project / "references"
    old_snapshot = json.loads((references / "literature_snapshot.json").read_text(encoding="utf-8"))["snapshot_hash"]
    receipt = {
        "input_sha256": "sha256:document",
        "document_id": "sha256:document",
        "work_id": "doi:10.1000/snapshot-bound",
        "parser": "pypdf",
        "route": "pypdf",
        "status": "parsed",
    }
    result = bind_document_parse(
        project,
        receipt=receipt,
        normalized={"document_id": "sha256:document", "work_id": "doi:10.1000/snapshot-bound", "title": "Snapshot-bound evidence paper"},
        passages=[{"page": 1, "text": "Evidence passage."}],
    )
    assert result["status"] == "bound"
    new_snapshot = json.loads((references / "literature_snapshot.json").read_text(encoding="utf-8"))["snapshot_hash"]
    assert new_snapshot != old_snapshot
    assert audit_literature_integrity(project)["status"] == "passed"

    rebuilt = rebuild_literature_index(project)
    assert rebuilt["status"] == "rebuilt"
    rebuilt_snapshot = json.loads((references / "literature_snapshot.json").read_text(encoding="utf-8"))["snapshot_hash"]
    assert rebuilt_snapshot == new_snapshot
    assert audit_literature_integrity(project)["snapshot_binding"]["status"] == "passed"
