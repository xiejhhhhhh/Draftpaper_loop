from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import subprocess

import pytest
import yaml

from draftpaper_cli.change_impact import CHANGE_CLASS_SPECS, CANONICAL_CHANGE_CLASSES, affected_stages_for_class
from draftpaper_cli.completion_change_classifier import (
    DEFAULT_ENFORCEMENT_MODE,
    classify_completion_change,
    suggest_evidence_refs,
    validate_evidence_refs,
)
from draftpaper_cli.manuscript_completion import prepare_manuscript_completion
from draftpaper_cli.manuscript_completion import (
    COMPLETION_SCHEMA,
    ManuscriptCompletionError,
    apply_manuscript_completion,
    preview_manuscript_completion,
)
from draftpaper_cli.manuscript_revision import build_manuscript_source_map
from draftpaper_cli.project_scaffold import create_project


def test_shadow_uses_conservative_inferred_class_for_new_model_mislabeled_as_prose() -> None:
    result = classify_completion_change(
        project_path=None,
        section="methods",
        instruction="Clarify the method implementation.",
        content="We added a new Transformer architecture and changed the validation split.",
        explicit="prose_only",
        enforcement_mode="shadow",
    )

    assert result.canonical_change_class == "prose_only"
    assert result.effective_change_class == "method_change"
    assert result.decision == "pass_with_shadow_warning"
    assert result.would_block_in_strict is True
    assert result.stale_scope == affected_stages_for_class("method_change", source_stage="methods_writing")


def test_v033_release_defaults_completion_classification_to_strict() -> None:
    assert DEFAULT_ENFORCEMENT_MODE == "strict"


def test_omitted_enforcement_mode_uses_v033_strict_default() -> None:
    result = classify_completion_change(
        project_path=None,
        section="data",
        instruction="Clarify the sample description.",
        content="The cohort now excludes sources below the revised signal threshold.",
        explicit="prose_only",
    )

    assert result.enforcement_mode == DEFAULT_ENFORCEMENT_MODE
    assert result.decision == "classification_mismatch"
    assert result.stale_scope == affected_stages_for_class(
        "cohort_change", source_stage="data_writing"
    )


@pytest.mark.parametrize("change_class", CANONICAL_CHANGE_CLASSES)
def test_every_canonical_class_uses_change_impact_scientific_semantics(change_class: str) -> None:
    spec = CHANGE_CLASS_SPECS[change_class]
    expected_scientific = spec.reopen_evidence or spec.rerun_science or spec.rerun_review

    result = classify_completion_change(
        project_path=None,
        section="discussion",
        instruction="Apply this bounded manuscript revision.",
        content="Polish this sentence for publication.",
        explicit=change_class,
        enforcement_mode="strict",
    )

    assert result.scientific_semantics_changed is expected_scientific
    if spec.release_only:
        assert result.scientific_semantics_changed is False


def test_shadow_still_requires_refs_for_executed_detail() -> None:
    result = classify_completion_change(
        project_path=None,
        section="methods",
        instruction="Clarify the implementation used in the run.",
        content="The run used a new Transformer architecture.",
        explicit="prose_only",
        enforcement_mode="shadow",
    )

    assert result.decision == "classification_refinement_required"
    assert "missing_evidence_refs" in result.rejection_codes


def test_strict_rejects_low_impact_class_for_cohort_change() -> None:
    result = classify_completion_change(
        project_path=None,
        section="data",
        instruction="Clarify the sample description.",
        content="The cohort now excludes the low-quality sources.",
        explicit="prose_only",
        enforcement_mode="strict",
    )

    assert result.inferred_change_class == "cohort_change"
    assert result.decision == "classification_mismatch"
    assert result.stale_scope == affected_stages_for_class(
        "cohort_change", source_stage="data_writing"
    )


@pytest.mark.parametrize(
    "content,expected",
    [
        ("The analytic sample size changed from 100 to 200 participants.", "cohort_change"),
        ("The sample size increased from 100 to 140 participants.", "cohort_change"),
        ("The sample size decreased to 80 participants after screening.", "cohort_change"),
        ("The final sample size doubled after extending recruitment.", "cohort_change"),
        ("The analytic sample size was halved after the quality audit.", "cohort_change"),
        ("N increased from 100 to 125 participants.", "cohort_change"),
        ("We added 30 participants after broadening eligibility.", "cohort_change"),
        ("We dropped 12 sources after quality control.", "cohort_change"),
        ("The analysis added 45 records from the adjudicated cohort.", "cohort_change"),
        ("We added 45 records to the dataset row inventory.", "data_change"),
        ("The dataset row inventory dropped 12 records during deduplication.", "data_change"),
    ],
)
def test_clear_sample_and_cohort_quantity_changes_block_with_precise_scope(
    content: str,
    expected: str,
) -> None:
    result = classify_completion_change(
        project_path=None,
        section="data",
        instruction="Apply this as a prose-only sample-description copyedit.",
        content=content,
        explicit="prose_only",
        enforcement_mode="strict",
    )

    assert result.inferred_change_class == expected
    assert result.decision == "classification_mismatch"
    assert result.would_block_in_strict is True
    assert result.stale_scope == affected_stages_for_class(
        expected, source_stage="data_writing"
    )


@pytest.mark.parametrize(
    "content",
    [
        "Change 'sample size' to 'analytic sample size' for journal terminology.",
        "Typeset N = 100 as N=100 to match journal spacing style.",
        "Hyphenate 'sample-size calculation' consistently in the Methods overview.",
        "The quoted phrase 'increased sample size' is removed from the reviewer response.",
    ],
)
def test_sample_quantity_copyedits_remain_prose_only(content: str) -> None:
    result = classify_completion_change(
        project_path=None,
        section="data",
        instruction="Apply this legitimate copyedit.",
        content=content,
        explicit="prose_only",
        enforcement_mode="strict",
    )

    assert result.inferred_change_class == "prose_only"
    assert result.decision == "accepted"


@pytest.mark.parametrize(
    "section,instruction,content,expected,expected_decision",
    [
        (
            "data",
            "Apply the copyedit and update the analysis source.",
            "Scientific content is unchanged in the caption, but the analysis now uses a new dataset.",
            "data_change",
            "classification_refinement_required",
        ),
        (
            "methods",
            "Update author metadata and describe the revised analysis.",
            "The revision introduces a new method for uncertainty estimation.",
            "method_change",
            "classification_mismatch",
        ),
        (
            "discussion",
            "Describe the new method and changed study design.",
            "The revised design addresses a new research question with a new model.",
            "research_plan_change",
            "classification_mismatch",
        ),
    ],
)
def test_compound_revision_uses_most_conservative_detected_class(
    section: str,
    instruction: str,
    content: str,
    expected: str,
    expected_decision: str,
) -> None:
    result = classify_completion_change(
        project_path=None,
        section=section,
        instruction=instruction,
        content=content,
        explicit="prose_only",
        enforcement_mode="strict",
    )

    assert result.inferred_change_class == expected
    assert result.decision == expected_decision


def test_executed_detail_without_evidence_refs_requires_refinement() -> None:
    result = classify_completion_change(
        project_path=None,
        section="methods",
        instruction="Add the implementation detail used in the run.",
        content="The run used masked pooling over the historical event tokens.",
        explicit="prose_only",
        enforcement_mode="strict",
    )

    assert result.decision == "classification_refinement_required"
    assert "missing_evidence_refs" in result.rejection_codes


def test_data_execution_refinement_reports_conservative_data_scope() -> None:
    result = classify_completion_change(
        project_path=None,
        section="data",
        instruction="Document the executed data preparation detail.",
        content="The analysis used archived records after the declared quality screening step.",
        explicit="prose_only",
        evidence_refs=[{}],
        enforcement_mode="strict",
    )

    assert result.decision == "classification_refinement_required"
    assert result.effective_change_class == "data_change"
    assert result.stale_scope == affected_stages_for_class(
        "data_change", source_stage="data_writing"
    )


def test_evidence_refs_are_suggested_from_fixed_manifests_without_network(tmp_path: Path) -> None:
    methods = tmp_path / "methods"
    methods.mkdir()
    run_manifest = methods / "run_manifest.yaml"
    run_manifest.write_text(
        json.dumps({
            "run_id": "run:current",
            "cohort_id": "cohort:main",
            "steps": {"feature_construction": {"status": "passed"}},
        }),
        encoding="utf-8",
    )
    refs = suggest_evidence_refs(tmp_path, section="methods", text="feature construction used in the current run")

    assert refs
    assert refs[0]["artifact"] == "methods/run_manifest.yaml"
    assert refs[0]["run_id"] == "run:current"
    assert refs[0]["cohort_id"] == "cohort:main"
    assert refs[0]["expected_sha256"]


def test_nested_record_suggestion_copies_selected_record_identities(tmp_path: Path) -> None:
    evidence = tmp_path / "results" / "resolved_result_evidence.json"
    evidence.parent.mkdir()
    evidence.write_text(
        json.dumps({
            "records": [{
                "run_id": "run:nested",
                "cohort_id": "cohort:nested",
                "snapshot_id": "snapshot:nested",
                "step": "masked pooling",
            }]
        }),
        encoding="utf-8",
    )

    refs = suggest_evidence_refs(tmp_path, section="methods", text="masked pooling used in the current run")

    assert refs[0]["artifact"] == "results/resolved_result_evidence.json"
    assert refs[0]["json_pointer"] == "/records/0"
    assert refs[0]["run_id"] == "run:nested"
    assert refs[0]["cohort_id"] == "cohort:nested"
    assert refs[0]["snapshot_id"] == "snapshot:nested"


def test_evidence_suggestions_skip_allowed_path_that_resolves_outside_project(tmp_path: Path) -> None:
    project = tmp_path / "project"
    outside = tmp_path / "outside"
    project.mkdir()
    outside.mkdir()
    (outside / "run_manifest.yaml").write_text(
        json.dumps({"run_id": "run:outside", "cohort_id": "cohort:outside"}),
        encoding="utf-8",
    )
    methods_link = project / "methods"
    try:
        methods_link.symlink_to(outside, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        if os.name != "nt":
            pytest.skip(f"directory symlinks are unavailable on this platform: {exc}")
        junction = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(methods_link), str(outside)],
            capture_output=True,
            text=True,
            check=False,
        )
        if junction.returncode != 0:
            pytest.skip(f"directory links are unavailable on this platform: {junction.stderr}")

    refs = suggest_evidence_refs(project, section="methods", text="used in the current run")

    assert refs == []


def test_valid_evidence_refs_allow_evidence_backed_prose(tmp_path: Path) -> None:
    methods = tmp_path / "methods"
    methods.mkdir()
    run_manifest = methods / "run_manifest.yaml"
    run_manifest.write_text(
        json.dumps({"run_id": "run:current", "cohort_id": "cohort:main", "steps": {"feature_construction": "passed"}}),
        encoding="utf-8",
    )
    ref = {
        "artifact": "methods/run_manifest.yaml",
        "json_pointer": "/steps/feature_construction",
        "expected_sha256": __import__("hashlib").sha256(run_manifest.read_bytes()).hexdigest(),
        "run_id": "run:current",
        "cohort_id": "cohort:main",
    }
    result = classify_completion_change(
        project_path=tmp_path,
        section="methods",
        instruction="Add the implementation detail used in the run.",
        content="The run used the declared feature construction step.",
        explicit="prose_only",
        evidence_refs=[ref],
        enforcement_mode="strict",
    )

    assert result.decision == "accepted"
    assert result.evidence_validation["status"] == "passed"
    assert result.stale_scope == affected_stages_for_class("prose_only", source_stage="methods_writing")


def test_uppercase_sha256_is_normalized_for_evidence_comparison(tmp_path: Path) -> None:
    run_manifest = tmp_path / "methods" / "run_manifest.yaml"
    run_manifest.parent.mkdir()
    run_manifest.write_text(json.dumps({"run_id": "run:current"}), encoding="utf-8")

    validation = validate_evidence_refs(tmp_path, [{
        "artifact": "methods/run_manifest.yaml",
        "json_pointer": "/run_id",
        "expected_sha256": hashlib.sha256(run_manifest.read_bytes()).hexdigest().upper(),
    }])

    assert validation["status"] == "passed"
    assert validation["issues"] == []


def test_json_pointer_accepts_a_present_null_value(tmp_path: Path) -> None:
    manifest = tmp_path / "methods" / "run_manifest.yaml"
    manifest.parent.mkdir()
    manifest.write_text(json.dumps({"result": None}), encoding="utf-8")

    validation = validate_evidence_refs(tmp_path, [{
        "artifact": "methods/run_manifest.yaml",
        "json_pointer": "/result",
        "expected_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
    }])

    assert validation["status"] == "passed"
    assert "evidence_pointer_missing" not in validation["issues"]


@pytest.mark.parametrize("pointer", ["records/0", "/records/~2", "/records/trailing~"])
def test_json_pointer_rejects_malformed_syntax(tmp_path: Path, pointer: str) -> None:
    manifest = tmp_path / "methods" / "run_manifest.yaml"
    manifest.parent.mkdir()
    manifest.write_text(json.dumps({"records": [{"run_id": "run:1"}]}), encoding="utf-8")

    validation = validate_evidence_refs(tmp_path, [{
        "artifact": "methods/run_manifest.yaml",
        "json_pointer": pointer,
        "expected_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
    }])

    assert validation["status"] == "failed"
    assert "evidence_pointer_invalid" in validation["issues"]


@pytest.mark.parametrize("token", ["\u00b2", "\u0661", "-1", "+1", "9" * 5000])
def test_json_pointer_non_ascii_or_unsafe_list_index_is_missing_without_raising(
    tmp_path: Path,
    token: str,
) -> None:
    manifest = tmp_path / "methods" / "run_manifest.yaml"
    manifest.parent.mkdir()
    manifest.write_text(json.dumps({"records": [{"run_id": "run:1"}]}), encoding="utf-8")

    validation = validate_evidence_refs(tmp_path, [{
        "artifact": "methods/run_manifest.yaml",
        "json_pointer": f"/records/{token}",
        "expected_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
    }])

    assert validation["status"] == "failed"
    assert "evidence_pointer_missing" in validation["issues"]


@pytest.mark.parametrize("identity_key", ["run_id", "cohort_id", "snapshot_id"])
def test_present_identity_is_validated_from_pointer_selected_record(tmp_path: Path, identity_key: str) -> None:
    evidence = tmp_path / "results" / "resolved_result_evidence.json"
    evidence.parent.mkdir()
    evidence.write_text(
        json.dumps({
            "records": [{
                "run_id": "run:current",
                "cohort_id": "cohort:main",
                "snapshot_id": "snapshot:current",
                "step": "masked pooling",
            }]
        }),
        encoding="utf-8",
    )
    ref: dict[str, str] = {
        "artifact": "results/resolved_result_evidence.json",
        "json_pointer": "/records/0",
        "expected_sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
        "run_id": "run:current",
        "cohort_id": "cohort:main",
        "snapshot_id": "snapshot:current",
    }
    ref[identity_key] = f"{identity_key}:stale"

    result = classify_completion_change(
        project_path=tmp_path,
        section="methods",
        instruction="Add the implementation detail used in the run.",
        content="The run used the declared masked pooling step.",
        explicit="prose_only",
        evidence_refs=[ref],
        enforcement_mode="strict",
    )

    assert result.decision == "classification_refinement_required"
    assert f"evidence_{identity_key}_mismatch" in result.rejection_codes


def _completion_project(tmp_path: Path) -> Path:
    project = create_project(
        root=tmp_path,
        idea="Completion snapshot identity test",
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
        "\\documentclass{article}\n\\begin{document}\n"
        "\\input{sections/introduction.tex}\n"
        "\\input{sections/data.tex}\n"
        "\\input{sections/methods.tex}\n"
        "\\input{sections/results.tex}\n"
        "\\input{sections/discussion.tex}\n"
        "\\bibliographystyle{plain}\n\\bibliography{library}\n\\end{document}\n",
        encoding="utf-8",
    )
    (project / "references" / "library.bib").write_text("", encoding="utf-8")
    (project / "latex" / "library.bib").write_text("", encoding="utf-8")
    (project / "references" / "literature_items.json").write_text("[]\n", encoding="utf-8")
    build_manuscript_source_map(project)
    return project


def _completion_packet(project: Path, evidence_ref: dict[str, str]) -> Path:
    source_map = json.loads((project / "latex" / "manuscript_source_map.json").read_text(encoding="utf-8"))
    target = next(
        row
        for row in source_map["paragraphs"]
        if row["section"] == "methods" and "\\section" not in row["context_excerpt"]
    )
    payload = {
        "schema_version": COMPLETION_SCHEMA,
        "project_id": json.loads((project / "project.json").read_text(encoding="utf-8"))["project_id"],
        "target_journal": "Test Journal",
        "metadata": {
            "title": "Completed manuscript title",
            "short_title": "Completed title",
            "abstract": "This manuscript reports a bounded analysis.",
            "keywords": ["scientific workflow"],
            "authors": [{
                "id": "author-1",
                "name": "Alice Example",
                "affiliations": ["inst-1"],
                "corresponding": True,
            }],
            "affiliations": [{"id": "inst-1", "name": "Institute of Tests"}],
            "acknowledgments": "We thank the survey team.",
            "data_availability": "Data are available from the named archive.",
            "code_availability": "Code is available from the named repository.",
        },
        "custom_references": [],
        "section_revisions": [{
            "revision_key": "methods-note",
            "target": {
                "paragraph_id": target["paragraph_id"],
                "expected_sha256": target["before_hash"],
                "expected_text": "Methods paragraph.",
            },
            "operation": "insert_after",
            "mode": "exact_text",
            "change_class": "prose_only",
            "content": "The run used the declared masked pooling step.",
            "evidence_refs": [evidence_ref],
        }],
    }
    path = project / "writing" / "author_input" / "completion.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def _passing_pdf(_root: Path, packet_dir: Path, **_kwargs: object) -> dict[str, object]:
    pdf = packet_dir / "preview.pdf"
    pdf.write_bytes(b"%PDF-1.4\n% completion preview\n")
    return {"status": "passed", "pdf": "preview.pdf", "engine": "fixture"}


def test_public_preview_reports_method_scope_without_mutating_stages_when_refinement_is_required(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _completion_project(tmp_path)
    packet = _completion_packet(project, {})
    payload = yaml.safe_load(packet.read_text(encoding="utf-8"))
    payload["section_revisions"][0]["content"] = (
        "The run used a new Transformer architecture in the revised analysis."
    )
    packet.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    project_state_before = (project / "project.json").read_bytes()
    methods_before = (project / "methods" / "methods.tex").read_bytes()
    monkeypatch.setattr("draftpaper_cli.manuscript_completion._build_completion_preview_pdf", _passing_pdf)

    preview = preview_manuscript_completion(project, packet)
    report = json.loads((project / preview["packet"] / "change_stale_report.json").read_text(encoding="utf-8"))
    change = report["changes"][0]
    expected_scope = affected_stages_for_class("method_change", source_stage="methods_writing")

    assert preview["status"] == "classification_refinement_required"
    assert preview["next_command"] is None
    assert change["effective_change_class"] == "method_change"
    assert change["inferred_change_class"] == "method_change"
    assert change["classification_decision"] == "classification_refinement_required"
    assert change["scientific_semantics_changed"] is True
    assert change["stale_scope"] == expected_scope
    assert change["computed_stale_scope"] == expected_scope
    assert (project / "project.json").read_bytes() == project_state_before
    assert (project / "methods" / "methods.tex").read_bytes() == methods_before

    with pytest.raises(ManuscriptCompletionError, match="ready completion packet"):
        apply_manuscript_completion(project, preview["packet_id"], preview["packet_hash"])

    assert (project / "project.json").read_bytes() == project_state_before
    assert (project / "methods" / "methods.tex").read_bytes() == methods_before


def test_preview_rejects_wrong_snapshot_identity_in_pointer_selected_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _completion_project(tmp_path)
    evidence = project / "results" / "resolved_result_evidence.json"
    evidence.write_text(
        json.dumps({"records": [{"snapshot_id": "snapshot:current", "step": "masked pooling"}]}),
        encoding="utf-8",
    )
    packet = _completion_packet(project, {
        "artifact": "results/resolved_result_evidence.json",
        "json_pointer": "/records/0",
        "expected_sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
        "snapshot_id": "snapshot:stale",
    })
    monkeypatch.setattr("draftpaper_cli.manuscript_completion._build_completion_preview_pdf", _passing_pdf)

    preview = preview_manuscript_completion(project, packet)
    report = json.loads((project / preview["packet"] / "change_stale_report.json").read_text(encoding="utf-8"))

    assert preview["status"] == "classification_refinement_required"
    assert "evidence_snapshot_id_mismatch" in report["changes"][0]["rejection_codes"]


def test_apply_revalidates_snapshot_identity_through_public_api(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _completion_project(tmp_path)
    evidence = project / "results" / "resolved_result_evidence.json"
    evidence.write_text(
        json.dumps({"records": [{"snapshot_id": "snapshot:current", "step": "masked pooling"}]}),
        encoding="utf-8",
    )
    packet = _completion_packet(project, {
        "artifact": "results/resolved_result_evidence.json",
        "json_pointer": "/records/0",
        "expected_sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
        "snapshot_id": "snapshot:current",
    })
    monkeypatch.setattr("draftpaper_cli.manuscript_completion._build_completion_preview_pdf", _passing_pdf)
    preview = preview_manuscript_completion(project, packet)
    assert preview["status"] == "ready_for_human_review"
    evidence.write_text(
        json.dumps({"records": [{"snapshot_id": "snapshot:changed", "step": "masked pooling"}]}),
        encoding="utf-8",
    )

    with pytest.raises(ManuscriptCompletionError, match="evidence_snapshot_id_mismatch"):
        apply_manuscript_completion(project, preview["packet_id"], preview["packet_hash"])


def test_arbitrary_project_file_is_not_an_allowed_evidence_ref(tmp_path: Path) -> None:
    arbitrary = tmp_path / "arbitrary.json"
    arbitrary.write_text("{}", encoding="utf-8")
    digest = __import__("hashlib").sha256(arbitrary.read_bytes()).hexdigest()

    result = classify_completion_change(
        project_path=tmp_path,
        section="methods",
        instruction="Add the implementation detail used in the run.",
        content="The method used masked pooling.",
        explicit="prose_only",
        evidence_refs=[{"artifact": "arbitrary.json", "json_pointer": "/", "expected_sha256": digest}],
        enforcement_mode="strict",
    )

    assert result.decision == "classification_refinement_required"
    assert "evidence_artifact_not_allowed" in result.rejection_codes


@pytest.mark.parametrize(
    "ref,code",
    [
        ({"artifact": "methods/run_manifest.yaml", "json_pointer": "/run_id"}, "evidence_hash_required"),
        ({"artifact": "methods/run_manifest.yaml", "expected_sha256": "a" * 64}, "evidence_pointer_required"),
    ],
)
def test_hash_and_pointer_are_required_for_evidence_refs(tmp_path: Path, ref: dict[str, str], code: str) -> None:
    path = tmp_path / "methods" / "run_manifest.yaml"
    path.parent.mkdir()
    path.write_text(json.dumps({"run_id": "run:1"}), encoding="utf-8")

    result = classify_completion_change(
        project_path=tmp_path,
        section="methods",
        instruction="Record the implementation used in the run.",
        content="The run used the declared method.",
        explicit="prose_only",
        evidence_refs=[ref],
        enforcement_mode="strict",
    )

    assert result.decision == "classification_refinement_required"
    assert code in result.rejection_codes


def test_strict_rejects_claim_narrowing_mislabeled_as_prose() -> None:
    result = classify_completion_change(
        project_path=None,
        section="results",
        instruction="Narrow the interpretation.",
        content="The conclusion is limited to the held-out cohort.",
        explicit="prose_only",
        enforcement_mode="strict",
    )

    assert result.inferred_change_class == "claim_boundary_change"
    assert result.decision == "classification_mismatch"


@pytest.mark.parametrize(
    "content",
    [
        "The value 1000 is typeset as 1,000 to follow journal numeric style.",
        "Change 'Figure 2' to 'Fig. 2' to match the journal abbreviation style.",
    ],
)
def test_results_numeric_typography_and_figure_reference_copyedits_are_prose_only(content: str) -> None:
    result = classify_completion_change(
        project_path=None,
        section="results",
        instruction="Apply this copyedit without changing scientific meaning.",
        content=content,
        explicit="prose_only",
        enforcement_mode="strict",
    )

    assert result.inferred_change_class == "prose_only"
    assert result.decision == "accepted"


def test_changed_reported_result_is_detected_without_bare_number_heuristic() -> None:
    result = classify_completion_change(
        project_path=None,
        section="results",
        instruction="Update the reported result.",
        content="The reported treatment-effect estimate changes from 0.74 to 0.58 after adjudication.",
        explicit="prose_only",
        enforcement_mode="strict",
    )

    assert result.inferred_change_class == "result_interpretation_change"
    assert result.decision == "classification_mismatch"


@pytest.mark.parametrize(
    "section,content,expected",
    [
        (
            "data",
            "For the final analysis, records are drawn from MIMIC-IV instead of the eICU source.",
            "data_change",
        ),
        (
            "data",
            "The analysis source changed from the legacy registry to the adjudicated release.",
            "data_change",
        ),
        (
            "methods",
            "We fit gradient-boosted trees in place of the prespecified logistic regression.",
            "method_change",
        ),
        (
            "methods",
            "The primary estimator changed from Cox regression to a random survival forest.",
            "method_change",
        ),
        (
            "data",
            "Patients receiving dialysis were removed from the analytic population.",
            "cohort_change",
        ),
        (
            "data",
            "Eligibility was broadened to include participants aged 75 years or older.",
            "cohort_change",
        ),
        (
            "results",
            "Accuracy replaces AUROC as the primary performance measure.",
            "metrics_change",
        ),
        (
            "methods",
            "We retrained the classifier after revising the image normalization step.",
            "run_change",
        ),
        (
            "methods",
            "The analysis was run again after the feature audit.",
            "run_change",
        ),
        (
            "results",
            "Figure 3 switches from calibration curves to decision-curve analysis.",
            "figure_change",
        ),
        (
            "results",
            "Panel C was revised to show subgroup sensitivity rather than overall specificity.",
            "figure_change",
        ),
        (
            "results",
            "Panel A now plots cumulative incidence; it previously showed overall survival.",
            "figure_change",
        ),
    ],
)
def test_realistic_scientific_paraphrases_infer_conservative_change_classes(
    section: str,
    content: str,
    expected: str,
) -> None:
    result = classify_completion_change(
        project_path=None,
        section=section,
        instruction="Polish this sentence as bounded completion prose.",
        content=content,
        explicit="prose_only",
        enforcement_mode="strict",
    )

    assert result.inferred_change_class == expected
    assert result.decision in {"classification_mismatch", "classification_refinement_required"}
    assert result.would_block_in_strict is True


@pytest.mark.parametrize(
    "section,content,expected",
    [
        ("data", "We dropped 27 patients after duplicate linkage was identified.", "cohort_change"),
        ("data", "Twelve sources were removed after the astrometric quality audit.", "cohort_change"),
        ("methods", "The prespecified estimator was supplanted by a random survival forest.", "method_change"),
        ("methods", "The final model now employs gradient-boosted trees.", "method_change"),
        ("results", "The primary endpoint became 90-day readmission.", "metrics_change"),
        ("results", "The reported outcome switched to progression-free survival.", "metrics_change"),
        ("methods", "We repeated the analysis after adjudication.", "run_change"),
        ("methods", "We re-executed the analysis after the feature audit.", "run_change"),
        ("results", "Figure 5 depicts adjusted risk instead of crude incidence.", "figure_change"),
        ("results", "Panel D shows class-specific recall instead of overall accuracy.", "figure_change"),
    ],
)
def test_remaining_scientific_paraphrase_families_block_in_strict_mode(
    section: str,
    content: str,
    expected: str,
) -> None:
    result = classify_completion_change(
        project_path=None,
        section=section,
        instruction="Apply this as a prose-only manuscript copyedit.",
        content=content,
        explicit="prose_only",
        enforcement_mode="strict",
    )

    assert result.inferred_change_class == expected
    assert result.decision in {"classification_mismatch", "classification_refinement_required"}
    assert result.would_block_in_strict is True


@pytest.mark.parametrize(
    "section,content,expected,decision",
    [
        (
            "data",
            "Replace the ground-truth label 'nonresponder' with 'responder' for 42 training records.",
            "data_change",
            "classification_mismatch",
        ),
        (
            "results",
            "Replace label 'Hazard ratio' with 'Adjusted hazard ratio' on the Figure 2 y-axis.",
            "prose_only",
            "accepted",
        ),
        (
            "results",
            "Replace the panel label 'B' with 'C' in Figure 4 to match the callout order.",
            "prose_only",
            "accepted",
        ),
        (
            "results",
            "Change the outcome class label from 'Poor' to 'Unfavorable' in the Figure 3 legend.",
            "prose_only",
            "accepted",
        ),
        (
            "results",
            "Replace the outcome class label 'Responder' with 'Response' on the y-axis.",
            "prose_only",
            "accepted",
        ),
        (
            "results",
            "Replace the outcome label 'Response' with 'Clinical response' in the table header.",
            "prose_only",
            "accepted",
        ),
        (
            "results",
            "Change the class label from 'Case' to 'Cases' in the caption only.",
            "prose_only",
            "accepted",
        ),
        (
            "data",
            "Change the target label from 'control' to 'case' for 12 records.",
            "data_change",
            "classification_mismatch",
        ),
        (
            "results",
            "Replace the record label 'control' with 'case' for patient 18.",
            "data_change",
            "classification_mismatch",
        ),
    ],
)
def test_replace_label_is_data_change_only_for_scientific_labels(
    section: str,
    content: str,
    expected: str,
    decision: str,
) -> None:
    result = classify_completion_change(
        project_path=None,
        section=section,
        instruction="Apply the requested label revision.",
        content=content,
        explicit="prose_only",
        enforcement_mode="strict",
    )

    assert result.inferred_change_class == expected
    assert result.decision == decision


@pytest.mark.parametrize(
    "instruction,content",
    [
        ("Apply journal word choice.", "In Methods, replace 'utilized' with 'used' for journal style."),
        ("Apply journal word choice.", "Change we utilized to we used for journal style."),
        ("Apply the terminology copyedit.", "The word used here is changed to applied for house style."),
        ("Apply consistent hyphenation.", "Hyphenate 'feature construction' consistently in the Methods overview."),
        (
            "Apply consistent hyphenation.",
            "Change 'historical event tokens' to 'historical-event tokens' throughout Methods.",
        ),
    ],
)
def test_methods_editorial_terminology_does_not_require_evidence_refs(
    instruction: str,
    content: str,
) -> None:
    result = classify_completion_change(
        project_path=None,
        section="methods",
        instruction=instruction,
        content=content,
        explicit="prose_only",
        enforcement_mode="strict",
    )

    assert result.inferred_change_class == "prose_only"
    assert result.decision == "accepted"
    assert "missing_evidence_refs" not in result.rejection_codes


@pytest.mark.parametrize(
    "content",
    [
        "We used inverse-probability weighting in the analysis.",
        "The pipeline recomputed embeddings after preprocessing.",
        "The estimator was fitted on the development cohort.",
        "The analysis pipeline processed and trained the input records.",
    ],
)
def test_real_executed_details_still_require_evidence_refs(content: str) -> None:
    result = classify_completion_change(
        project_path=None,
        section="methods",
        instruction="Document this implementation detail.",
        content=content,
        explicit="prose_only",
        enforcement_mode="strict",
    )

    assert result.decision == "classification_refinement_required"
    assert "missing_evidence_refs" in result.rejection_codes


def test_strict_uses_data_change_when_declared_run_change_is_too_narrow() -> None:
    result = classify_completion_change(
        project_path=None,
        section="data",
        instruction="Update the analysis source.",
        content="Replace data with a new dataset for the analysis.",
        explicit="run_change",
        enforcement_mode="strict",
    )

    assert result.inferred_change_class == "data_change"
    assert result.decision == "classification_mismatch"


def test_executed_detail_cannot_hide_behind_metadata_class() -> None:
    result = classify_completion_change(
        project_path=None,
        section="methods",
        instruction="Add the implementation detail used in the run.",
        content="The model used masked pooling.",
        explicit="metadata_only",
        enforcement_mode="strict",
    )

    assert result.decision == "classification_refinement_required"
    assert "missing_evidence_refs" in result.rejection_codes


def test_completion_template_and_docs_explain_evidence_refs(tmp_path: Path) -> None:
    project = create_project(root=tmp_path, idea="Evidence ref template", field="astronomy").path
    result = prepare_manuscript_completion(project)
    template = (project / result["template"]).read_text(encoding="utf-8")

    assert "evidence_refs:" in template
    assert "json_pointer:" in template
    assert "expected_sha256:" in template
    for name in ("docs/manuscript_completion.md", "docs/manuscript_completion.zh-CN.md"):
        content = Path(name).read_text(encoding="utf-8")
        assert "suggested_evidence_refs" in content
        assert "classification_refinement_required" in content


def test_strict_calibration_gate_meets_release_error_rates() -> None:
    fixture = Path("tests/fixtures/completion_change_calibration.json")
    rows = json.loads(fixture.read_text(encoding="utf-8"))

    assert len(rows) >= 60
    assert len({row["discipline_family"] for row in rows}) >= 3
    assert {row["independent_label"] for row in rows} == {"scientific_change", "legitimate_completion"}
    classifier_input_labels = {
        (
            row["section"],
            row["instruction"],
            row["content"],
            row.get("explicit"),
            row["independent_label"],
        )
        for row in rows
    }
    assert len(classifier_input_labels) >= 60
    confusion = {
        "true_positive": 0,
        "false_negative": 0,
        "false_positive": 0,
        "true_negative": 0,
    }
    for row in rows:
        assert row["explicit"] in CANONICAL_CHANGE_CLASSES, row["case_id"]
        result = classify_completion_change(
            project_path=None,
            section=row["section"],
            instruction=row["instruction"],
            content=row["content"],
            explicit=row.get("explicit"),
            enforcement_mode="strict",
        )
        scientific = row["independent_label"] == "scientific_change"
        blocked = result.would_block_in_strict
        key = {
            (True, True): "true_positive",
            (True, False): "false_negative",
            (False, True): "false_positive",
            (False, False): "true_negative",
        }[(scientific, blocked)]
        confusion[key] += 1

    scientific_total = confusion["true_positive"] + confusion["false_negative"]
    legitimate_total = confusion["true_negative"] + confusion["false_positive"]
    scientific_false_negative_rate = confusion["false_negative"] / scientific_total
    legitimate_false_block_rate = confusion["false_positive"] / legitimate_total

    assert scientific_total > 0 and legitimate_total > 0
    assert scientific_false_negative_rate == 0, confusion
    assert legitimate_false_block_rate <= 0.05, confusion
    assert DEFAULT_ENFORCEMENT_MODE == "strict"
