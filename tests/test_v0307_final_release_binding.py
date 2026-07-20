from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest
import yaml

from draftpaper_cli.evidence_snapshot import manuscript_snapshot
from draftpaper_cli.final_manuscript_confirmation import (
    FinalManuscriptConfirmationError,
    confirm_final_manuscript,
    review_final_manuscript,
)
from draftpaper_cli.independent_review import SCORE_DIMENSIONS, derive_independent_review_decision
from draftpaper_cli.project_scaffold import create_project


def _write(path: Path, content: bytes | str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")


def _artifact_record(project: Path, relative: str) -> dict[str, object]:
    path = project / relative
    return {
        "path": relative,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "size_bytes": path.stat().st_size,
    }


def _bundle_core(project: Path) -> dict[str, object]:
    return {
        "schema_version": "dpl.independent_review_bundle.v1",
        "project_id_hash": "project-id-hash",
        "submission_anonymized": True,
        "full_manuscript_reviewed": True,
        "real_figures_reviewed": True,
        "baseline_material_prohibited": True,
        "frozen_artifacts": {
            "manuscript": [_artifact_record(project, "latex/main.pdf")],
            "figures": [_artifact_record(project, "results/figures/figure_01.png")],
            "tables": [],
            "references": [_artifact_record(project, "references/library.bib")],
            "evidence": [_artifact_record(project, "results/promoted_evidence_snapshot.json")],
            "reproducibility": [],
        },
        "reviewer_contract": {
            "same_bundle_for_all_reviewers": True,
            "reviewers_cannot_see_other_reports": True,
            "automatic_scores_withheld": True,
            "prior_audits_withheld": True,
        },
        "excluded_reproducibility_files": [],
        "reproducibility_smoke_test": {"decision": "pass"},
        "selected_run_asset_filtering": True,
    }


def _write_bundle_zip(project: Path, manifest: dict[str, object]) -> None:
    _write_complete_frozen_bundle_zip(project, manifest)


def _write_complete_frozen_bundle_zip(
    project: Path,
    manifest: dict[str, object],
    *,
    omitted: set[str] | None = None,
    replacements: dict[str, bytes] | None = None,
) -> None:
    omitted = omitted or set()
    replacements = replacements or {}
    bundle_path = project / str(manifest["bundle_zip"])
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    frozen = manifest["frozen_artifacts"]
    assert isinstance(frozen, dict)
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("bundle_manifest.json", json.dumps(manifest))
        for group in frozen.values():
            if not isinstance(group, list):
                continue
            for record in group:
                member = str(record["path"])
                if member not in omitted:
                    archive.writestr(member, replacements.get(member, (project / member).read_bytes()))


def _rewrite_bundle_member(project: Path, member: str, content: bytes) -> None:
    bundle_path = project / "quality_checks" / "blind_reviews" / "anonymous_submission_bundle.zip"
    with zipfile.ZipFile(bundle_path) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    members[member] = content
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)


def _write_structured_blind_reviews(project: Path) -> str:
    core = _bundle_core(project)
    bundle_hash = hashlib.sha256(json.dumps(core, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    manifest = {
        **core,
        "created_at": "2026-07-18T10:00:00+00:00",
        "bundle_hash": bundle_hash,
        "bundle_hash_semantics": "SHA-256 of the canonical frozen-artifact manifest core; not the ZIP container byte hash.",
        "bundle_zip": "quality_checks/blind_reviews/anonymous_submission_bundle.zip",
    }
    _write(
        project / "quality_checks" / "blind_reviews" / "submission_bundle_manifest.json",
        json.dumps(manifest),
    )
    _write_bundle_zip(project, manifest)
    report_paths = []
    report_sha256 = {}
    reports = []
    for index, recorded_at in ((1, "2026-07-18T11:00:00+00:00"), (2, "2026-07-18T11:05:00+00:00")):
        reviewer = f"reviewer_{index:02d}"
        relative = f"quality_checks/blind_reviews/{reviewer}/report.json"
        report_paths.append(relative)
        report = {
            "schema_version": "dpl.independent_manuscript_review.v1",
            "reviewer_anonymous_id": reviewer,
            "independent_session_provider_id_hash": f"session-{index}",
            "frozen_submission_bundle_hash": bundle_hash,
            "overall_recommendation": "accept_for_revision",
            "scores": {dimension: 0.95 for dimension in SCORE_DIMENSIONS},
            "findings": [
                {
                    "finding_id": f"{reviewer}:001",
                    "severity": "advisory",
                    "locator": "page 1, Results",
                    "detail": "The result summary is grounded in the frozen manuscript.",
                    "required_action": "Retain the current evidence boundary.",
                }
            ],
            "checked_real_figures": True,
            "full_manuscript_reviewed": True,
            "recorded_at": recorded_at,
        }
        reports.append(report)
        _write(
            project / relative,
            json.dumps(report),
        )
        report_sha256[relative] = hashlib.sha256((project / relative).read_bytes()).hexdigest()
    _write(
        project / "quality_checks" / "blind_reviews" / "aggregate.json",
        json.dumps(
            {
                "schema_version": "dpl.independent_review_aggregate.v1",
                "status": "passed",
                "generated_at": "2026-07-18T11:30:00+00:00",
                "frozen_submission_bundle_hash": bundle_hash,
                "reviewer_count": 2,
                "reviewer_reports": report_paths,
                "reviewer_report_sha256": report_sha256,
                **derive_independent_review_decision(reports),
            }
        ),
    )
    return bundle_hash


def _refresh_review_bindings(project: Path) -> None:
    review_root = project / "quality_checks" / "blind_reviews"
    manifest_path = review_root / "submission_bundle_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    generated_fields = {"created_at", "bundle_hash", "bundle_hash_semantics", "bundle_zip"}
    core = {key: value for key, value in manifest.items() if key not in generated_fields}
    bundle_hash = hashlib.sha256(json.dumps(core, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    manifest["bundle_hash"] = bundle_hash
    _write(manifest_path, json.dumps(manifest))
    _write_bundle_zip(project, manifest)

    aggregate_path = review_root / "aggregate.json"
    aggregate = json.loads(aggregate_path.read_text(encoding="utf-8"))
    aggregate["frozen_submission_bundle_hash"] = bundle_hash
    report_sha256 = {}
    for relative in aggregate["reviewer_reports"]:
        report_path = project / relative
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["frozen_submission_bundle_hash"] = bundle_hash
        _write(report_path, json.dumps(report))
        report_sha256[relative] = hashlib.sha256(report_path.read_bytes()).hexdigest()
    aggregate["reviewer_report_sha256"] = report_sha256
    _write(aggregate_path, json.dumps(aggregate))


def _refresh_aggregate_report_hashes(project: Path) -> None:
    aggregate_path = project / "quality_checks" / "blind_reviews" / "aggregate.json"
    aggregate = json.loads(aggregate_path.read_text(encoding="utf-8"))
    aggregate["reviewer_report_sha256"] = {
        relative: hashlib.sha256((project / relative).read_bytes()).hexdigest()
        for relative in aggregate["reviewer_reports"]
    }
    _write(aggregate_path, json.dumps(aggregate))


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
    _write(project / "results" / "figures" / "figure_01.png", b"\x89PNG\r\n\x1a\nfinal-figure")
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
    _write_structured_blind_reviews(project)
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
    assert packet["submission_bundle_hash"]
    assert packet["independent_reviewer_ids"] == ["reviewer_01", "reviewer_02"]
    confirmed = confirm_final_manuscript(project, release_hash=review["release_hash"])
    assert confirmed["status"] == "approved"


def test_final_review_rejects_bare_markdown_and_aggregate_counts(tmp_path: Path) -> None:
    project = _release_project(tmp_path)
    (project / "quality_checks" / "blind_reviews" / "submission_bundle_manifest.json").unlink()
    for reviewer in ("reviewer_01", "reviewer_02"):
        (project / "quality_checks" / "blind_reviews" / reviewer / "report.json").unlink()

    with pytest.raises(FinalManuscriptConfirmationError, match="submission bundle"):
        review_final_manuscript(project)


def test_final_review_recomputes_blocking_status_from_bound_reports(tmp_path: Path) -> None:
    project = _release_project(tmp_path)
    report_path = project / "quality_checks" / "blind_reviews" / "reviewer_01" / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["findings"][0]["severity"] = "critical"
    report["findings"][0]["resolution_status"] = "open"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    _refresh_aggregate_report_hashes(project)

    with pytest.raises(FinalManuscriptConfirmationError, match="recomputed.*blocked"):
        review_final_manuscript(project)


@pytest.mark.parametrize(
    ("field", "mutated_value"),
    [
        ("status", "revision_required"),
        ("release_review_status", "blocked"),
        ("critical_open_count", 1),
        ("major_open_count", 1),
        ("adjudication_required", True),
        ("recommendations", None),
        ("score_means", None),
        ("reviewer_agreement", None),
        ("revision_queue", []),
        ("reviewer_report_sha256", None),
    ],
)
def test_final_review_rejects_any_mutation_of_aggregate_decision_surface(
    tmp_path: Path,
    field: str,
    mutated_value: object,
) -> None:
    project = _release_project(tmp_path)
    aggregate_path = project / "quality_checks" / "blind_reviews" / "aggregate.json"
    aggregate = json.loads(aggregate_path.read_text(encoding="utf-8"))
    if field == "reviewer_report_sha256":
        mutated_value = dict(aggregate[field])
        mutated_value[aggregate["reviewer_reports"][0]] = "0" * 64
    aggregate[field] = mutated_value
    _write(aggregate_path, json.dumps(aggregate))

    with pytest.raises(FinalManuscriptConfirmationError, match="aggregate decision surface"):
        review_final_manuscript(project)


@pytest.mark.parametrize("reviewer_count", ["two", 2.0, True, None])
def test_final_review_reports_malformed_reviewer_count_as_schema_error(
    tmp_path: Path,
    reviewer_count: object,
) -> None:
    project = _release_project(tmp_path)
    aggregate_path = project / "quality_checks" / "blind_reviews" / "aggregate.json"
    aggregate = json.loads(aggregate_path.read_text(encoding="utf-8"))
    aggregate["reviewer_count"] = reviewer_count
    aggregate_path.write_text(json.dumps(aggregate), encoding="utf-8")

    with pytest.raises(FinalManuscriptConfirmationError, match="reviewer_count.*integer"):
        review_final_manuscript(project)


def test_final_review_rejects_missing_declared_bundle_zip(tmp_path: Path) -> None:
    project = _release_project(tmp_path)
    (project / "quality_checks" / "blind_reviews" / "anonymous_submission_bundle.zip").unlink()

    with pytest.raises(FinalManuscriptConfirmationError, match="packet is incomplete|bundle ZIP"):
        review_final_manuscript(project)


def test_final_review_rejects_bundle_zip_without_bound_manifest(tmp_path: Path) -> None:
    project = _release_project(tmp_path)
    bundle_path = project / "quality_checks" / "blind_reviews" / "anonymous_submission_bundle.zip"
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manuscript.pdf", b"%PDF-1.4\n")

    with pytest.raises(FinalManuscriptConfirmationError, match="bundle ZIP.*bundle_manifest.json"):
        review_final_manuscript(project)


@pytest.mark.parametrize(
    ("member", "tampered_payload"),
    [
        ("latex/main.pdf", b"%PDF-1.4\n% tampered manuscript\n"),
        ("results/figures/figure_01.png", b"\x89PNG\r\n\x1a\ntampered-figure"),
    ],
)
def test_final_review_rejects_tampered_bundle_payload_with_unchanged_embedded_manifest(
    tmp_path: Path,
    member: str,
    tampered_payload: bytes,
) -> None:
    project = _release_project(tmp_path)
    _rewrite_bundle_member(project, member, tampered_payload)

    with pytest.raises(FinalManuscriptConfirmationError, match="bundle ZIP payload.*identity"):
        review_final_manuscript(project)


def test_final_review_accepts_zip_with_every_declared_frozen_group(tmp_path: Path) -> None:
    project = _release_project(tmp_path)
    supplement = project / "supplement" / "review_notes.txt"
    _write(supplement, "Frozen supplement.\n")
    manifest_path = project / "quality_checks" / "blind_reviews" / "submission_bundle_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["frozen_artifacts"]["supplement"] = [_artifact_record(project, "supplement/review_notes.txt")]
    _write(manifest_path, json.dumps(manifest))
    _refresh_review_bindings(project)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _write_complete_frozen_bundle_zip(project, manifest)

    result = review_final_manuscript(project)

    assert result["status"] == "ready_for_human_review"


@pytest.mark.parametrize(
    "member",
    ["references/library.bib", "results/promoted_evidence_snapshot.json"],
)
def test_final_review_rejects_omitted_reference_or_evidence_from_complete_frozen_zip(
    tmp_path: Path,
    member: str,
) -> None:
    project = _release_project(tmp_path)
    manifest_path = project / "quality_checks" / "blind_reviews" / "submission_bundle_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _write_complete_frozen_bundle_zip(project, manifest, omitted={member})

    with pytest.raises(FinalManuscriptConfirmationError, match="missing: " + re.escape(member)):
        review_final_manuscript(project)


@pytest.mark.parametrize(
    "member",
    ["references/library.bib", "results/promoted_evidence_snapshot.json"],
)
def test_final_review_rejects_tampered_reference_or_evidence_in_complete_frozen_zip(
    tmp_path: Path,
    member: str,
) -> None:
    project = _release_project(tmp_path)
    manifest_path = project / "quality_checks" / "blind_reviews" / "submission_bundle_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _write_complete_frozen_bundle_zip(project, manifest, replacements={member: b"tampered frozen payload"})

    with pytest.raises(FinalManuscriptConfirmationError, match=r"bundle ZIP payload.*identity"):
        review_final_manuscript(project)


def test_final_review_rejects_missing_required_frozen_artifact_group(tmp_path: Path) -> None:
    project = _release_project(tmp_path)
    manifest_path = project / "quality_checks" / "blind_reviews" / "submission_bundle_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["frozen_artifacts"].pop("references")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    _refresh_review_bindings(project)

    with pytest.raises(FinalManuscriptConfirmationError, match="missing required groups.*references"):
        review_final_manuscript(project)


def test_final_review_rejects_citation_symlink_escape(tmp_path: Path) -> None:
    project = _release_project(tmp_path)
    citation_path = project / "citation_audit" / "final_citation_audit_report.json"
    outside = tmp_path / "outside-citation.json"
    outside.write_bytes(citation_path.read_bytes())
    citation_path.unlink()
    try:
        citation_path.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    with pytest.raises(FinalManuscriptConfirmationError, match="escapes the project"):
        review_final_manuscript(project)


def test_final_review_rejects_citation_directory_junction_escape(tmp_path: Path) -> None:
    project = _release_project(tmp_path)
    citation_dir = project / "citation_audit"
    outside_dir = tmp_path / "outside-citation-dir"
    shutil.copytree(citation_dir, outside_dir)
    shutil.rmtree(citation_dir)
    if os.name == "nt":
        completed = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(citation_dir), str(outside_dir)],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            pytest.skip(f"junction creation unavailable: {completed.stderr or completed.stdout}")
    else:
        citation_dir.symlink_to(outside_dir, target_is_directory=True)
    try:
        with pytest.raises(FinalManuscriptConfirmationError, match="escapes the project"):
            review_final_manuscript(project)
    finally:
        if os.name == "nt":
            os.rmdir(citation_dir)
        else:
            citation_dir.unlink()


def test_final_review_rejects_reviewer_report_symlink_escape(tmp_path: Path) -> None:
    project = _release_project(tmp_path)
    report_path = project / "quality_checks" / "blind_reviews" / "reviewer_01" / "report.json"
    outside = tmp_path / "outside-review.json"
    outside.write_bytes(report_path.read_bytes())
    report_path.unlink()
    try:
        report_path.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    with pytest.raises(FinalManuscriptConfirmationError, match="escapes the project"):
        review_final_manuscript(project)


def test_final_review_rejects_review_not_bound_to_current_bundle_hash(tmp_path: Path) -> None:
    project = _release_project(tmp_path)
    report_path = project / "quality_checks" / "blind_reviews" / "reviewer_02" / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["frozen_submission_bundle_hash"] = "stale-bundle"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    _refresh_aggregate_report_hashes(project)

    with pytest.raises(FinalManuscriptConfirmationError, match="current submission bundle hash"):
        review_final_manuscript(project)


def test_final_review_enforces_audit_before_bundle_before_reviews(tmp_path: Path) -> None:
    project = _release_project(tmp_path)
    manifest_path = project / "quality_checks" / "blind_reviews" / "submission_bundle_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["created_at"] = "2026-07-18T08:30:00+00:00"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    _write_bundle_zip(project, manifest)

    with pytest.raises(FinalManuscriptConfirmationError, match="after the final citation audit"):
        review_final_manuscript(project)


def test_final_review_rejects_report_produced_before_current_bundle(tmp_path: Path) -> None:
    project = _release_project(tmp_path)
    report_path = project / "quality_checks" / "blind_reviews" / "reviewer_01" / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["recorded_at"] = "2026-07-18T09:30:00+00:00"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    _refresh_aggregate_report_hashes(project)

    with pytest.raises(FinalManuscriptConfirmationError, match="after the current submission bundle"):
        review_final_manuscript(project)


def test_final_review_requires_two_distinct_structured_review_sessions(tmp_path: Path) -> None:
    project = _release_project(tmp_path)
    first = json.loads(
        (project / "quality_checks" / "blind_reviews" / "reviewer_01" / "report.json").read_text(encoding="utf-8")
    )
    second_path = project / "quality_checks" / "blind_reviews" / "reviewer_02" / "report.json"
    second = json.loads(second_path.read_text(encoding="utf-8"))
    second["independent_session_provider_id_hash"] = first["independent_session_provider_id_hash"]
    second_path.write_text(json.dumps(second), encoding="utf-8")
    _refresh_aggregate_report_hashes(project)

    with pytest.raises(FinalManuscriptConfirmationError, match="distinct independent session"):
        review_final_manuscript(project)


def test_final_review_rejects_tampered_submission_bundle_manifest_hash(tmp_path: Path) -> None:
    project = _release_project(tmp_path)
    manifest_path = project / "quality_checks" / "blind_reviews" / "submission_bundle_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["frozen_artifacts"]["manuscript"][0]["size_bytes"] += 1
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(FinalManuscriptConfirmationError, match="submission bundle hash"):
        review_final_manuscript(project)


def test_final_review_rejects_current_bundle_artifact_drift(tmp_path: Path) -> None:
    project = _release_project(tmp_path)
    _write(project / "latex" / "main.pdf", b"%PDF-1.4\n% changed after reviews\n")

    with pytest.raises(
        FinalManuscriptConfirmationError,
        match="current manuscript|frozen submission bundle artifact",
    ):
        review_final_manuscript(project)


def test_final_review_rejects_unrelated_pdf_substituted_for_current_latex_main(tmp_path: Path) -> None:
    project = _release_project(tmp_path)
    _write(project / "supplement" / "unrelated.pdf", b"%PDF-1.4\n% unrelated payload\n")
    manifest_path = project / "quality_checks" / "blind_reviews" / "submission_bundle_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["frozen_artifacts"]["manuscript"] = [_artifact_record(project, "supplement/unrelated.pdf")]
    _write(manifest_path, json.dumps(manifest))
    _refresh_review_bindings(project)

    with pytest.raises(FinalManuscriptConfirmationError, match=r"latex/main\.pdf"):
        review_final_manuscript(project)


@pytest.mark.parametrize("malformed_group", [None, {}, "not-a-list"])
def test_final_review_rejects_every_non_list_frozen_artifact_group(
    tmp_path: Path,
    malformed_group: object,
) -> None:
    project = _release_project(tmp_path)
    manifest_path = project / "quality_checks" / "blind_reviews" / "submission_bundle_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["frozen_artifacts"]["figures"] = malformed_group
    _write(manifest_path, json.dumps(manifest))
    _refresh_review_bindings(project)

    with pytest.raises(FinalManuscriptConfirmationError, match="frozen artifact groups must be lists"):
        review_final_manuscript(project)


@pytest.mark.parametrize("invalid_identity", ["non_string_path", "absolute_path", "boolean_size", "float_size"])
def test_final_review_validates_every_frozen_artifact_identity(
    tmp_path: Path,
    invalid_identity: str,
) -> None:
    project = _release_project(tmp_path)
    identity_path = project / "123"
    identity_path.write_bytes(b"x")
    manifest_path = project / "quality_checks" / "blind_reviews" / "submission_bundle_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    record = {
        "path": "123",
        "sha256": hashlib.sha256(identity_path.read_bytes()).hexdigest(),
        "size_bytes": 1,
    }
    if invalid_identity == "non_string_path":
        record["path"] = 123
    elif invalid_identity == "absolute_path":
        record["path"] = identity_path.as_posix()
    elif invalid_identity == "boolean_size":
        record["size_bytes"] = True
    else:
        record["size_bytes"] = 1.0
    manifest["frozen_artifacts"]["figures"] = [record]
    _write(manifest_path, json.dumps(manifest))
    _refresh_review_bindings(project)

    with pytest.raises(FinalManuscriptConfirmationError, match="frozen artifact identity"):
        review_final_manuscript(project)


@pytest.mark.parametrize(
    "invalid_content",
    [
        "recommendation",
        "scores",
        "score_dimension",
        "boolean_score",
        "nan_score",
        "findings",
        "empty_findings",
        "ungrounded_finding",
        "non_string_grounding",
    ],
)
def test_final_review_requires_complete_grounded_review_content(tmp_path: Path, invalid_content: str) -> None:
    project = _release_project(tmp_path)
    report_path = project / "quality_checks" / "blind_reviews" / "reviewer_01" / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if invalid_content == "recommendation":
        report.pop("overall_recommendation")
    elif invalid_content == "scores":
        report.pop("scores")
    elif invalid_content == "score_dimension":
        report["scores"].pop(next(iter(SCORE_DIMENSIONS)))
    elif invalid_content == "boolean_score":
        report["scores"][next(iter(SCORE_DIMENSIONS))] = True
    elif invalid_content == "nan_score":
        report["scores"][next(iter(SCORE_DIMENSIONS))] = float("nan")
    elif invalid_content == "findings":
        report.pop("findings")
    elif invalid_content == "empty_findings":
        report["findings"] = []
    elif invalid_content == "ungrounded_finding":
        report["findings"][0]["locator"] = ""
    else:
        report["findings"][0]["locator"] = 1
    _write(report_path, json.dumps(report))
    _refresh_aggregate_report_hashes(project)

    with pytest.raises(FinalManuscriptConfirmationError, match="review content schema error"):
        review_final_manuscript(project)


def test_final_review_rejects_report_edited_after_aggregate_generation(tmp_path: Path) -> None:
    project = _release_project(tmp_path)
    report_path = project / "quality_checks" / "blind_reviews" / "reviewer_01" / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["findings"][0]["detail"] = "Edited after aggregate generation."
    _write(report_path, json.dumps(report))

    with pytest.raises(FinalManuscriptConfirmationError, match="SHA-256"):
        review_final_manuscript(project)


def test_final_review_requires_aggregate_timestamp_strictly_after_both_reports(tmp_path: Path) -> None:
    project = _release_project(tmp_path)
    report = json.loads(
        (project / "quality_checks" / "blind_reviews" / "reviewer_02" / "report.json").read_text(encoding="utf-8")
    )
    aggregate_path = project / "quality_checks" / "blind_reviews" / "aggregate.json"
    aggregate = json.loads(aggregate_path.read_text(encoding="utf-8"))
    aggregate["generated_at"] = report["recorded_at"]
    _write(aggregate_path, json.dumps(aggregate))

    with pytest.raises(FinalManuscriptConfirmationError, match="after both structured review reports"):
        review_final_manuscript(project)


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
