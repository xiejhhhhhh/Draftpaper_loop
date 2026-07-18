from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from draftpaper_cli.evidence_snapshot import manuscript_snapshot
from draftpaper_cli.final_manuscript_confirmation import (
    FinalManuscriptConfirmationError,
    confirm_final_manuscript,
    review_final_manuscript,
)
from draftpaper_cli.project_scaffold import create_project


def _write(path: Path, content: bytes | str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")


def _release_project(tmp_path: Path) -> Path:
    project = create_project(
        root=tmp_path,
        idea="Final release binding",
        field="astronomy",
        target_journal="MNRAS",
    ).path
    metadata = {
        "title": "Final manuscript title",
        "abstract": "A bounded final abstract.",
        "authors": [{"id": "author-1", "name": "Alice Example", "affiliations": ["inst-1"]}],
        "affiliations": [{"id": "inst-1", "name": "Institute"}],
    }
    _write(project / "writing" / "manuscript_metadata.yaml", yaml.safe_dump(metadata, sort_keys=False))
    for section in ("introduction", "data", "methods", "results", "discussion"):
        _write(project / section / f"{section}.tex", f"\\section{{{section.title()}}}\n\nFinal {section} paragraph.\n")
    _write(project / "references" / "library.bib", "@article{Example2026,title={Example},year={2026}}\n")
    _write(project / "latex" / "library.bib", "@article{Example2026,title={Example},year={2026}}\n")
    _write(project / "references" / "reference_registry.json", json.dumps({"status": "passed", "references": ["Example2026"]}))
    _write(project / "latex" / "main.pdf", b"%PDF-1.4\n% final manuscript\n")
    _write(
        project / "writing" / "manuscript_completion" / "active_completion_manifest.json",
        json.dumps(
            {
                "schema_version": "dpl.active_manuscript_completion.v1",
                "status": "applied",
                "packet_id": "packet:final",
                "packet_hash": "a" * 64,
                "applied_at": "2026-07-18T08:00:00+00:00",
            }
        ),
    )
    _write(project / "results" / "promoted_evidence_snapshot.json", json.dumps({"snapshot_id": "evidence-final", "artifacts": {}}))
    _write(project / "results" / "result_manifest.yaml", "schema_version: dpl.result_manifest.v2\nstatus: passed\n")
    _write(project / "results" / "figure_metadata.json", json.dumps({"status": "passed", "figures": []}))
    _write(project / "core_evidence" / "core_evidence_report.json", json.dumps({"decision": "pass"}))
    _write(project / "integrity" / "integrity_report.json", json.dumps({"status": "passed", "decision": "pass"}))
    _write(project / "quality_checks" / "quality_report.json", json.dumps({"status": "passed", "decision": "pass"}))
    _write(
        project / "quality_checks" / "blind_reviews" / "aggregate.json",
        json.dumps({"status": "passed", "decision": "pass", "reviewer_count": 2}),
    )
    _write(project / "quality_checks" / "blind_reviews" / "reviewer_01" / "report.md", "# Blind review 1\n\nPass.\n")
    _write(project / "quality_checks" / "blind_reviews" / "reviewer_02" / "report.md", "# Blind review 2\n\nPass.\n")
    snapshot = manuscript_snapshot(project)
    _write(
        project / "citation_audit" / "final_citation_audit_report.json",
        json.dumps(
            {
                "schema_version": "dpl.citation_audit.v2",
                "status": "passed",
                "generated_at": "2026-07-18T09:00:00+00:00",
                "manuscript_snapshot": snapshot,
            }
        ),
    )
    return project


def test_final_release_packet_binds_completion_evidence_citation_reviews_and_pdf(tmp_path: Path) -> None:
    project = _release_project(tmp_path)

    review = review_final_manuscript(project)

    assert review["status"] == "ready_for_human_review"
    packet = json.loads((project / "review" / "final_manuscript_confirmation_packet.json").read_text(encoding="utf-8"))
    paths = {item["path"] for item in packet["artifacts"]}
    assert {
        "writing/manuscript_completion/active_completion_manifest.json",
        "writing/manuscript_metadata.yaml",
        "methods/methods.tex",
        "references/reference_registry.json",
        "results/promoted_evidence_snapshot.json",
        "results/result_manifest.yaml",
        "results/figure_metadata.json",
        "citation_audit/final_citation_audit_report.json",
        "integrity/integrity_report.json",
        "quality_checks/blind_reviews/reviewer_01/report.md",
        "quality_checks/blind_reviews/reviewer_02/report.md",
        "latex/main.pdf",
    }.issubset(paths)
    assert packet["completion_packet_id"] == "packet:final"
    assert packet["citation_audit_snapshot_id"] == manuscript_snapshot(project)["snapshot_id"]
    confirmed = confirm_final_manuscript(project, release_hash=review["release_hash"])
    assert confirmed["status"] == "approved"


@pytest.mark.parametrize(
    ("path", "mutation", "message"),
    [
        (
            "writing/manuscript_completion/active_completion_manifest.json",
            {"status": "rolled_back"},
            "completion",
        ),
        ("quality_checks/quality_report.json", {"status": "failed", "decision": "blocked"}, "quality"),
        ("integrity/integrity_report.json", {"status": "failed", "decision": "blocked"}, "integrity"),
        ("quality_checks/blind_reviews/aggregate.json", {"status": "failed", "decision": "blocked"}, "review"),
    ],
)
def test_final_review_rejects_non_passing_bound_artifacts(
    tmp_path: Path,
    path: str,
    mutation: dict[str, str],
    message: str,
) -> None:
    project = _release_project(tmp_path)
    target = project / path
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload.update(mutation)
    target.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(FinalManuscriptConfirmationError, match=message):
        review_final_manuscript(project)


def test_final_review_rejects_citation_snapshot_older_than_current_manuscript(tmp_path: Path) -> None:
    project = _release_project(tmp_path)
    methods = project / "methods" / "methods.tex"
    methods.write_text(methods.read_text(encoding="utf-8") + "Later author edit.\n", encoding="utf-8")

    with pytest.raises(FinalManuscriptConfirmationError, match="citation audit"):
        review_final_manuscript(project)


def test_confirmation_rejects_any_release_artifact_drift(tmp_path: Path) -> None:
    project = _release_project(tmp_path)
    review = review_final_manuscript(project)
    metadata = project / "writing" / "manuscript_metadata.yaml"
    metadata.write_text(metadata.read_text(encoding="utf-8") + "funding: Later change\n", encoding="utf-8")

    with pytest.raises(FinalManuscriptConfirmationError, match="release hash"):
        confirm_final_manuscript(project, release_hash=review["release_hash"])


def test_bilingual_completion_guides_exist_and_document_the_hash_guard() -> None:
    root = Path(__file__).resolve().parents[1]
    english = (root / "docs" / "manuscript_completion.md").read_text(encoding="utf-8")
    chinese = (root / "docs" / "manuscript_completion.zh-CN.md").read_text(encoding="utf-8")
    for text in (english, chinese):
        assert "manuscript_completion.yaml" in text
        assert "paragraph_id" in text
        assert "expected_sha256" in text
        assert "preview-manuscript-completion" in text
        assert "apply-manuscript-completion" in text
        assert "rollback-manuscript-completion" in text
