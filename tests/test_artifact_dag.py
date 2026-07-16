import json

from draftpaper_cli.artifact_dag import build_artifact_dag, downstream_artifact_ids, stale_artifacts_for_change
from draftpaper_cli.project_scaffold import create_project


def test_formula_or_local_methods_prose_revision_does_not_reopen_data_or_figures() -> None:
    stale = stale_artifacts_for_change("prose_semantic_no_evidence_change", section="methods")
    assert "methods" in stale
    assert "dependent_discussion_claims" in stale
    assert "figures" not in stale
    assert "data_semantics" not in stale


def test_citation_local_change_only_reopens_manuscript_release_chain() -> None:
    stale = stale_artifacts_for_change("citation_local", section="discussion")
    assert {"discussion", "latex_assembly", "citation_audit", "independent_reviews", "quality_release"}.issubset(stale)
    assert "analysis_execution" not in stale
    assert "figures" not in stale


def test_cohort_change_reopens_scientific_chain() -> None:
    stale = stale_artifacts_for_change("cohort_definition_change")
    assert {"data_semantics", "analysis_execution", "figures", "core_evidence", "results", "methods"}.issubset(stale)


def test_artifact_dag_contains_real_hashes_paths_and_executable_edges(tmp_path) -> None:
    project = create_project(root=tmp_path, idea="Executable artifact graph", field="engineering").path
    artifact = project / "methods" / "method_plan.json"
    artifact.write_text("{}", encoding="utf-8")
    stage_manifest = project / "methods" / "stage_manifest.json"
    stage_payload = json.loads(stage_manifest.read_text(encoding="utf-8"))
    stage_payload["output_files"] = ["methods/method_plan.json"]
    stage_manifest.write_text(json.dumps(stage_payload), encoding="utf-8")

    dag = build_artifact_dag(project, write=False)

    assert dag["schema_version"] == "dpl.artifact_dependency_dag.v2"
    assert any(node.get("artifact_id") == "stage:methods" for node in dag["nodes"])
    record = next(node for node in dag["nodes"] if node.get("path") == "methods/method_plan.json")
    assert record["sha256"]
    assert record["node_type"] == "artifact"
    assert f"stage:{record['owner_stage']}" in record["depends_on"]
    downstream = downstream_artifact_ids(dag, [f"stage:{record['owner_stage']}"])
    assert record["artifact_id"] in downstream
