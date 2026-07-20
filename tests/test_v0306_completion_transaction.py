from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from draftpaper_cli.change_impact import affected_stages_for_class
from draftpaper_cli.cli import build_parser
from draftpaper_cli.command_registry import command_spec
from draftpaper_cli.manuscript_completion import (
    COMPLETION_SCHEMA,
    ManuscriptCompletionError,
    apply_manuscript_completion,
    manuscript_completion_status,
    preview_manuscript_completion,
    rollback_manuscript_completion,
    validate_manuscript_completion_payload,
)
from draftpaper_cli.manuscript_revision import active_user_locks, build_manuscript_source_map
from draftpaper_cli.project_scaffold import create_project


def _project(tmp_path: Path) -> Path:
    project = create_project(
        root=tmp_path,
        idea="Completion transaction test",
        field="astronomy",
        target_journal="Test Journal",
    ).path
    sections = {
        "introduction": "\\section{Introduction}\n\nIntroduction paragraph.\n",
        "data": "\\section{Data}\n\nData paragraph.\n",
        "methods": "\\section{Methods}\n\nMethods paragraph.\n",
        "results": "\\section{Results}\n\nResult paragraph.\n",
        "discussion": "\\section{Discussion}\n\nDiscussion paragraph.\n",
    }
    for section, text in sections.items():
        canonical = project / section / f"{section}.tex"
        canonical.parent.mkdir(parents=True, exist_ok=True)
        canonical.write_text(text, encoding="utf-8")
        projection = project / "latex" / "sections" / f"{section}.tex"
        projection.parent.mkdir(parents=True, exist_ok=True)
        projection.write_text(text, encoding="utf-8")
    (project / "latex" / "main.tex").write_text(
        "\\documentclass{article}\n"
        "\\usepackage{hyperref}\n"
        "\\title{Original title}\n"
        "\\author{}\n"
        "\\begin{document}\n\\maketitle\n"
        "\\input{sections/introduction.tex}\n"
        "\\input{sections/data.tex}\n"
        "\\input{sections/methods.tex}\n"
        "\\input{sections/results.tex}\n"
        "\\input{sections/discussion.tex}\n"
        "\\bibliographystyle{plain}\n\\bibliography{library}\n\\end{document}\n",
        encoding="utf-8",
    )
    bib = "@article{Existing2025, author={A. Existing}, title={Existing}, year={2025}}\n"
    (project / "references" / "library.bib").write_text(bib, encoding="utf-8")
    (project / "latex" / "library.bib").write_text(bib, encoding="utf-8")
    (project / "references" / "literature_items.json").write_text("[]\n", encoding="utf-8")
    build_manuscript_source_map(project)
    return project


def _row(project: Path, section: str) -> dict[str, object]:
    source_map = json.loads((project / "latex" / "manuscript_source_map.json").read_text(encoding="utf-8"))
    return next(
        row
        for row in source_map["paragraphs"]
        if row["section"] == section and "\\section" not in row["context_excerpt"]
    )


def _packet(
    project: Path,
    *,
    change_class: str = "prose_only",
    mode: str = "exact_text",
    include_content: bool = True,
) -> Path:
    target = _row(project, "methods")
    packet_dir = project / "writing" / "author_input"
    packet_dir.mkdir(parents=True, exist_ok=True)
    revision: dict[str, object] = {
        "revision_key": "methods-note",
        "target": {
            "paragraph_id": target["paragraph_id"],
            "expected_sha256": target["before_hash"],
            "expected_text": "Methods paragraph.",
        },
        "operation": "insert_after",
        "mode": mode,
        "change_class": change_class,
    }
    if include_content:
        revision["content"] = "Author-approved bounded method note."
    if mode == "instruction_to_codex":
        revision["instruction"] = "Add a bounded method note without changing evidence."
    payload = {
        "schema_version": COMPLETION_SCHEMA,
        "project_id": json.loads((project / "project.json").read_text(encoding="utf-8"))["project_id"],
        "target_journal": "Test Journal",
        "metadata": {
            "title": "Completed manuscript title",
            "short_title": "Completed title",
            "abstract": "This manuscript reports a bounded analysis.",
            "keywords": ["scientific workflow"],
            "authors": [
                {
                    "id": "author-1",
                    "name": "Alice Example",
                    "affiliations": ["inst-1"],
                    "corresponding": True,
                }
            ],
            "affiliations": [{"id": "inst-1", "name": "Institute of Tests"}],
            "acknowledgments": "We thank the survey team.",
            "data_availability": "Data are available from the named archive.",
            "code_availability": "Code is available from the named repository.",
        },
        "custom_references": [
            {
                "citation_key": "Custom2026",
                "title": "A custom source",
                "authors": ["A. Researcher"],
                "year": 2026,
                "journal": "Journal of Tests",
                "doi": "10.1234/example",
                "evidence_notes": "Supports the bounded comparison.",
            }
        ],
        "section_revisions": [revision],
    }
    path = packet_dir / "completion.yaml"
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def _passing_pdf(_root: Path, packet_dir: Path, **_kwargs: object) -> dict[str, object]:
    pdf = packet_dir / "preview.pdf"
    pdf.write_bytes(b"%PDF-1.4\n% completion preview\n")
    return {"status": "passed", "pdf": "preview.pdf", "engine": "fixture"}


@pytest.mark.parametrize(
    "evidence_refs,field_path",
    [
        ({"artifact": "methods/run_manifest.yaml"}, r"section_revisions\[0\]\.evidence_refs"),
        (None, r"section_revisions\[0\]\.evidence_refs"),
        (["methods/run_manifest.yaml"], r"section_revisions\[0\]\.evidence_refs\[0\]"),
        ([{"artifact": "methods/run_manifest.yaml"}, 7], r"section_revisions\[0\]\.evidence_refs\[1\]"),
    ],
)
def test_completion_packet_validates_evidence_ref_shape_before_coercion(
    tmp_path: Path,
    evidence_refs: object,
    field_path: str,
) -> None:
    project = _project(tmp_path)
    packet = _packet(project)
    payload = yaml.safe_load(packet.read_text(encoding="utf-8"))
    payload["section_revisions"][0]["evidence_refs"] = evidence_refs

    with pytest.raises(ManuscriptCompletionError, match=field_path):
        validate_manuscript_completion_payload(project, payload)


def test_completion_payload_rejects_mixed_evidence_ref_keys_and_preserves_valid_refs(tmp_path: Path) -> None:
    project = _project(tmp_path)
    packet = _packet(project)
    payload = yaml.safe_load(packet.read_text(encoding="utf-8"))
    valid_ref = {
        "artifact": "methods/run_manifest.yaml",
        "json_pointer": "/run_id",
        "expected_sha256": "a" * 64,
    }
    payload["section_revisions"][0]["evidence_refs"] = [valid_ref]

    normalized = validate_manuscript_completion_payload(project, payload)

    assert normalized["section_revisions"][0]["evidence_refs"] == [valid_ref]
    payload["section_revisions"][0]["evidence_refs"] = [{**valid_ref, 7: "invalid"}]
    with pytest.raises(
        ManuscriptCompletionError,
        match=r"section_revisions\[0\]\.evidence_refs\[0\]\.<key>",
    ):
        validate_manuscript_completion_payload(project, payload)


def test_completion_yaml_rejects_mixed_evidence_ref_keys_before_hashing(tmp_path: Path) -> None:
    project = _project(tmp_path)
    packet = _packet(project)
    payload = yaml.safe_load(packet.read_text(encoding="utf-8"))
    payload["section_revisions"][0]["evidence_refs"] = [{
        "artifact": "methods/run_manifest.yaml",
        7: "invalid",
    }]
    packet.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")

    with pytest.raises(
        ManuscriptCompletionError,
        match=r"section_revisions\[0\]\.evidence_refs\[0\]\.<key>",
    ):
        preview_manuscript_completion(project, packet)


def test_preview_apply_idempotency_and_hash_guard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = _project(tmp_path)
    packet = _packet(project)
    original_methods = (project / "methods" / "methods.tex").read_text(encoding="utf-8")
    monkeypatch.setattr("draftpaper_cli.manuscript_completion._build_completion_preview_pdf", _passing_pdf)

    preview = preview_manuscript_completion(project, packet)

    assert preview["status"] == "ready_for_human_review"
    packet_root = project / preview["packet"]
    assert (packet_root / "preview.diff").is_file()
    assert (packet_root / "candidate" / "latex" / "main.tex").is_file()
    assert (packet_root / "preview.pdf").is_file()
    assert "Completed manuscript title" in (packet_root / "candidate" / "latex" / "main.tex").read_text(encoding="utf-8")
    assert (project / "methods" / "methods.tex").read_text(encoding="utf-8") == original_methods
    assert not (project / "writing" / "manuscript_metadata.yaml").exists()

    with pytest.raises(ManuscriptCompletionError, match="hash"):
        apply_manuscript_completion(project, preview["packet_id"], "0" * 64)

    applied = apply_manuscript_completion(project, preview["packet_id"], preview["packet_hash"])
    assert applied["status"] == "applied"
    assert "Completed manuscript title" in (project / "writing" / "manuscript_metadata.yaml").read_text(encoding="utf-8")
    assert "Author-approved bounded method note" in (project / "methods" / "methods.tex").read_text(encoding="utf-8")
    assert "Custom2026" in (project / "references" / "library.bib").read_text(encoding="utf-8")
    assert active_user_locks(project, "methods")
    repeated = apply_manuscript_completion(project, preview["packet_id"], preview["packet_hash"])
    assert repeated["status"] == "already_applied"
    assert (project / "methods" / "methods.tex").read_text(encoding="utf-8").count("Author-approved bounded method note") == 1
    assert (project / "references" / "library.bib").read_text(encoding="utf-8").count("Custom2026") == 1
    assert manuscript_completion_status(project)["status"] == "applied"


def test_change_report_preserves_legacy_class_and_computed_stale_scope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = _project(tmp_path)
    packet = _packet(project, change_class="prose_only")
    payload = yaml.safe_load(packet.read_text(encoding="utf-8"))
    payload["section_revisions"][0]["content"] = "A new Transformer architecture changed the validation split."
    packet.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    monkeypatch.setattr("draftpaper_cli.manuscript_completion._build_completion_preview_pdf", _passing_pdf)

    preview = preview_manuscript_completion(project, packet)
    report = json.loads((project / preview["packet"] / "change_stale_report.json").read_text(encoding="utf-8"))
    change = report["changes"][0]
    assert change["legacy_change_class"] == "prose_only"
    assert change["effective_change_class"] == "prose_only"
    assert change["inferred_change_class"] == "method_change"
    assert change["classification_decision"] == "classification_mismatch"
    assert change["computed_stale_scope"] == affected_stages_for_class(
        "method_change", source_stage="methods_writing"
    )


def test_apply_rejects_evidence_ref_changed_after_preview(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = _project(tmp_path)
    run_manifest = project / "methods" / "run_manifest.yaml"
    run_manifest.write_text(json.dumps({"run_id": "run:current", "step": "masked pooling"}), encoding="utf-8")
    packet = _packet(project)
    payload = yaml.safe_load(packet.read_text(encoding="utf-8"))
    payload["section_revisions"][0]["content"] = "The run used the declared masked pooling step."
    payload["section_revisions"][0]["evidence_refs"] = [{
        "artifact": "methods/run_manifest.yaml",
        "json_pointer": "/step",
        "expected_sha256": __import__("hashlib").sha256(run_manifest.read_bytes()).hexdigest(),
        "run_id": "run:current",
    }]
    packet.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    monkeypatch.setattr("draftpaper_cli.manuscript_completion._build_completion_preview_pdf", _passing_pdf)

    preview = preview_manuscript_completion(project, packet)
    assert preview["status"] == "ready_for_human_review"
    run_manifest.write_text(json.dumps({"run_id": "run:changed", "step": "different"}), encoding="utf-8")

    with pytest.raises(ManuscriptCompletionError, match="evidence ref"):
        apply_manuscript_completion(project, preview["packet_id"], preview["packet_hash"])


def test_apply_failure_rolls_back_every_canonical_artifact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = _project(tmp_path)
    packet = _packet(project)
    monkeypatch.setattr("draftpaper_cli.manuscript_completion._build_completion_preview_pdf", _passing_pdf)
    preview = preview_manuscript_completion(project, packet)
    before_methods = (project / "methods" / "methods.tex").read_bytes()
    before_bib = (project / "references" / "library.bib").read_bytes()

    def fail_reference(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise RuntimeError("injected reference failure")

    monkeypatch.setattr("draftpaper_cli.manuscript_completion.add_custom_reference", fail_reference)
    with pytest.raises(RuntimeError, match="injected reference failure"):
        apply_manuscript_completion(project, preview["packet_id"], preview["packet_hash"])

    assert not (project / "writing" / "manuscript_metadata.yaml").exists()
    assert (project / "methods" / "methods.tex").read_bytes() == before_methods
    assert (project / "references" / "library.bib").read_bytes() == before_bib
    assert not (project / "writing" / "manuscript_completion" / "active_completion_manifest.json").exists()


def test_rollback_restores_snapshot_and_rejects_post_apply_edits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = _project(tmp_path)
    packet = _packet(project)
    monkeypatch.setattr("draftpaper_cli.manuscript_completion._build_completion_preview_pdf", _passing_pdf)
    preview = preview_manuscript_completion(project, packet)
    apply_manuscript_completion(project, preview["packet_id"], preview["packet_hash"])
    methods = project / "methods" / "methods.tex"
    applied_bytes = methods.read_bytes()
    methods.write_text(methods.read_text(encoding="utf-8") + "Manual later edit.\n", encoding="utf-8")

    with pytest.raises(ManuscriptCompletionError, match="changed after completion"):
        rollback_manuscript_completion(project, preview["packet_id"])

    methods.write_bytes(applied_bytes)
    rolled_back = rollback_manuscript_completion(project, preview["packet_id"])
    assert rolled_back["status"] == "rolled_back"
    assert "Author-approved bounded method note" not in methods.read_text(encoding="utf-8")
    assert "Custom2026" not in (project / "references" / "library.bib").read_text(encoding="utf-8")
    assert manuscript_completion_status(project)["status"] == "rolled_back"


@pytest.mark.parametrize(
    ("mode", "include_content", "change_class", "preview_status"),
    [
        ("instruction_to_codex", False, "prose_only", "codex_patch_required"),
        ("exact_text", True, "data_change", "scientific_reopen_required"),
    ],
)
def test_preview_blocks_unresolved_or_scientific_packets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    include_content: bool,
    change_class: str,
    preview_status: str,
) -> None:
    project = _project(tmp_path)
    packet = _packet(project, mode=mode, include_content=include_content, change_class=change_class)
    monkeypatch.setattr("draftpaper_cli.manuscript_completion._build_completion_preview_pdf", _passing_pdf)

    preview = preview_manuscript_completion(project, packet)

    assert preview["status"] == preview_status
    with pytest.raises(ManuscriptCompletionError, match="ready completion packet"):
        apply_manuscript_completion(project, preview["packet_id"], preview["packet_hash"])


def test_compile_required_is_non_passing_and_completion_commands_are_protected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _project(tmp_path)
    packet = _packet(project)
    monkeypatch.setattr(
        "draftpaper_cli.manuscript_completion._build_completion_preview_pdf",
        lambda *_args, **_kwargs: {"status": "compile_required", "pdf": None, "reason": "No TeX engine."},
    )

    preview = preview_manuscript_completion(project, packet)

    assert preview["status"] == "compile_required"
    preview_spec = command_spec("preview-manuscript-completion")
    apply_spec = command_spec("apply-manuscript-completion")
    rollback_spec = command_spec("rollback-manuscript-completion")
    assert preview_spec is not None and preview_spec.protected_action is False
    assert apply_spec is not None and apply_spec.protected_action is True
    assert rollback_spec is not None and rollback_spec.protected_action is True
    parser = build_parser()
    assert parser.parse_args(
        ["preview-manuscript-completion", "--project", str(project), "--input", str(packet)]
    ).command == "preview-manuscript-completion"
    assert parser.parse_args(
        [
            "apply-manuscript-completion",
            "--project",
            str(project),
            "--packet-id",
            "packet:example",
            "--packet-hash",
            "0" * 64,
        ]
    ).command == "apply-manuscript-completion"
