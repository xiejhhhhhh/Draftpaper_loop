from __future__ import annotations

import json

from draftpaper_cli.checkpoint_summary import write_stage_summary
from draftpaper_cli.code_ownership import trace_figures_to_code
from draftpaper_cli.passport import refresh_project_passport
from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.result_evidence import resolve_result_evidence


def test_strict_anonymous_fixture_produces_confirmable_complete_html(tmp_path) -> None:
    project = create_project(root=tmp_path, idea="Anonymous evidence fixture", field="generic").path
    results = project / "results"
    tables = results / "tables"
    figures = results / "figures"
    plotting = project / "methods" / "plotting"
    for path in (tables, figures, plotting):
        path.mkdir(parents=True, exist_ok=True)
    analysis = project / "methods" / "src" / "fixture_analysis.py"
    analysis.parent.mkdir(parents=True, exist_ok=True)
    analysis.write_text("print('fixture-analysis')\n", encoding="utf-8")
    (project / "methods" / "executable_analysis_spec.json").write_text(
        json.dumps(
            {
                "schema_version": "dpl.executable_analysis_spec.v1",
                "analysis_specs": [
                    {
                        "analysis_spec_id": "analysis-fixture",
                        "task_id": "task-a",
                        "estimand_id": "estimand-a",
                        "cohort_view_id": "cohort-a-held-out",
                        "sample_unit": "entity",
                        "split_id": "test",
                        "implementation_entry_point": "methods/src/fixture_analysis.py",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (project / "methods" / "analysis_formula_ast.json").write_text(
        json.dumps(
            {
                "schema_version": "dpl.analysis_formula_ast.v1",
                "formulas": [{"formula_id": "macro-f1", "analysis_spec_id": "analysis-fixture", "ast": {"type": "symbol", "name": "macro_f1"}}],
            }
        ),
        encoding="utf-8",
    )
    (project / "methods" / "resampling_contract.json").write_text(
        json.dumps(
            {
                "schema_version": "dpl.resampling_contract.v1",
                "contracts": [{"analysis_spec_id": "analysis-fixture", "method": "none_declared"}],
            }
        ),
        encoding="utf-8",
    )
    (project / "methods" / "run_selection_policy.json").write_text(
        json.dumps(
            {
                "schema_version": "dpl.run_selection_policy.v1",
                "selection_role": "primary",
                "selection_metric": "macro_f1",
                "selection_partition": "validation",
                "locked_before_test_access": True,
                "test_access_policy": "held-out after selection lock",
                "aggregation_policy": "prespecified_primary",
            }
        ),
        encoding="utf-8",
    )
    (project / "methods" / "method_code_manifest.json").write_text(
        json.dumps(
            {
                "method_families": ["fixture-analysis"],
                "primary_metric": "macro_f1",
                "verify_command_argv": ["{python}", "methods/src/fixture_analysis.py"],
            }
        ),
        encoding="utf-8",
    )
    (tables / "canonical_metrics.csv").write_text(
        "run_id,metric,value,model_id,task_id,cohort_id,sample_unit,validation_design_id,split_id,aggregation_id,uncertainty_definition_id\n"
        "run-1,macro_f1,0.81,model-a,task-a,cohort-a,entity,group-held-out,test,none,none\n",
        encoding="utf-8",
    )
    (project / "methods" / "primary_metric_contract.json").write_text(
        json.dumps({
            "schema_version": "dpl.primary_metric_contract.v1",
            "metric_definition_id": "macro_f1",
            "task_id": "task-a",
            "cohort_id": "cohort-a",
            "sample_unit": "entity",
            "model_id": "model-a",
            "validation_design_id": "group-held-out",
            "split_id": "test",
            "aggregation_id": "none",
            "uncertainty_definition_id": "none",
        }),
        encoding="utf-8",
    )
    (project / "methods" / "run_manifest.yaml").write_text(
        json.dumps({
            "status": "success",
            "run_id": "run-1",
            "run_transaction_id": "txn-1",
            "analysis_spec_id": "analysis-fixture",
            "output_files": ["results/tables/canonical_metrics.csv"],
            "count_evidence": [
                {
                    "count_definition_id": "model_unique_entity_count",
                    "entity_type": "entity",
                    "count_mode": "unique_entities",
                    "cohort_id": "cohort-a",
                    "filter_contract_id": "quality-v1",
                    "sample_unit": "entity",
                    "value": 12,
                    "evidence_role": "model_cohort",
                }
            ],
        }),
        encoding="utf-8",
    )
    (results / "result_validity_report.json").write_text(
        json.dumps({"decision": "pass", "resolved_run_id": "run-1"}), encoding="utf-8"
    )
    (results / "result_support_checkpoint.json").write_text(
        json.dumps({
            "support_level": "supported",
        }),
        encoding="utf-8",
    )
    (project / "core_evidence" / "core_evidence_report.json").write_text(
        json.dumps({
            "decision": "pass",
            "reviewable_figures": [{
                "path": "results/figures/figure1.png",
                "caption": "Anonymous fixture figure",
                "interpretation_summary": "Fixture-only trace validation.",
            }],
        }),
        encoding="utf-8",
    )
    (results / "figure_metadata.json").write_text(
        json.dumps({"figures": [{"path": "results/figures/figure1.png", "figure_id": "fig-1"}]}),
        encoding="utf-8",
    )
    (figures / "figure1.png").write_bytes(b"fixture-image")
    (plotting / "make_figure.py").write_text("# fig-1\nprint('fixture')\n", encoding="utf-8")

    resolved = resolve_result_evidence(project)
    assert resolved["strict_status"] == "passed"
    trace_figures_to_code(project)
    # Re-resolve so the active bundle captures the newly generated v2 trace.
    resolved = resolve_result_evidence(project)
    assert resolved["run_evidence_bundle"]["status"] == "validated"
    before = refresh_project_passport(project)["artifacts"]
    result = write_stage_summary(
        project,
        stage="core_evidence",
        command="test-strict-fixture",
        payload={"status": "checkpoint_created"},
        before_artifacts=before,
        checkpoint_id="strict-fixture-checkpoint",
        checkpoint_hash="strict-fixture-hash",
        publish_index=False,
    )
    summary = json.loads((project / result["stage_summary_json"]).read_text(encoding="utf-8"))
    html = (project / result["stage_summary_zh_html"]).read_text(encoding="utf-8")
    confirmation = json.loads((project / result["confirmation_request"]).read_text(encoding="utf-8"))
    assert summary["review_state"] == "confirmable"
    assert summary["test_auto_confirmation"] is False
    assert confirmation["review_state"] == "confirmable"
    assert confirmation["confirmation_command"]
    assert "证据身份与样本分母" in html
    assert "样本流程" in html
    assert "macro_f1=0.810" in html
    assert "PrimaryMetricContract" in html
    assert "results/figures/figure1.png" in html
    assert "methods/plotting/make_figure.py" in html


def test_strict_fixture_can_record_test_only_confirmation_skip(tmp_path) -> None:
    project = create_project(root=tmp_path, idea="Anonymous confirmation skip", field="generic").path
    result = write_stage_summary(
        project,
        stage="core_evidence",
        command="test-strict-fixture",
        payload={"status": "checkpoint_created", "test_mode": True, "test_auto_confirmation": True},
        before_artifacts=[],
        checkpoint_id="strict-fixture-auto-skip",
        checkpoint_hash="strict-fixture-auto-skip-hash",
        publish_index=False,
    )
    summary = json.loads((project / result["stage_summary_json"]).read_text(encoding="utf-8"))
    html = (project / result["stage_summary_zh_html"]).read_text(encoding="utf-8")
    request = json.loads((project / result["confirmation_request"]).read_text(encoding="utf-8"))

    assert summary["test_auto_confirmation"] is True
    assert request["test_auto_confirmation"] is True
    assert "测试流程跳过人工确认动作" in html
    assert "不代表任何真实科研结果已被用户确认" in html
