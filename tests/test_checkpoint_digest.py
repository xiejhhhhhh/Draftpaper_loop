from __future__ import annotations

import json
import tempfile
from pathlib import Path

from draftpaper_cli.checkpoint_digest import build_stage_digest
from draftpaper_cli.checkpoint_summary import preview_checkpoint_summary, write_stage_summary
from draftpaper_cli.checkpoint_summary import show_checkpoint_summary
from draftpaper_cli.orchestrator import checkpoint_project
from draftpaper_cli.passport import refresh_project_passport
from draftpaper_cli.project_scaffold import create_project


def _write_core_fixture(project: Path) -> None:
    files = {
        "core_evidence/core_evidence_report.json": {
            "decision": "pass",
            "promoted_evidence_snapshot_id": "snapshot-test",
            "reviewable_figures": [
                {
                    "path": "results/figures/figure1.png",
                    "caption": "Main result",
                    "interpretation_summary": "The held-out result is supported.",
                }
            ],
        },
        "results/result_validity_report.json": {
            "decision": "conditional_pass",
            "resolved_run_id": "run-test",
        },
        "results/result_support_checkpoint.json": {
            "support_level": "supported",
            "claim_assessments": [{"claim_boundary": "Only the declared cohort is covered."}],
            "metric_records": [
                {
                    "metric_name": "f1",
                    "value": 0.700000,
                    "context": {"run_id": "run-support", "sample_unit": "source"},
                }
            ],
        },
        "data/formal_data_run_binding.json": {
            "run_id": "run-data",
            "sample_unit": "source",
            "validation_design": "source-held-out",
            "source_rows": 9,
            "train_sources": 6,
            "test_sources": 3,
        },
        "results/figure_metadata.json": {
            "figures": [{"path": "results/figures/figure1.png", "figure_id": "Figure 1"}]
        },
        "results/figure_code_trace.json": {
            "traces": [
                {
                    "figure_path": "results/figures/figure1.png",
                    "code_files": ["methods/plotting/make_figure.py"],
                    "statistics": {"seed_count": 3, "source_rows": 10},
                }
            ]
        },
        "results/tables/metrics.csv": "run_id,metric,value,sample_unit\nrun-test,f1,0.753953,source\n",
        "results/tables/analysis_summary.csv": "run_id,validation_design,source_rows\nrun-test,source-held-out,1229\n",
        "results/figures/figure1.png": b"not-a-real-png-for-a-path-preview",
        "methods/plotting/make_figure.py": "print('<figure>')\n",
        "methods/run_manifest.yaml": "run_id: run-test\n",
    }
    for relative, content in files.items():
        path = project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        elif isinstance(content, dict):
            path.write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")
        else:
            path.write_text(content, encoding="utf-8")


def test_core_evidence_digest_lists_complete_unchanged_deliverables_and_trace() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project = create_project(root=tmp, idea="Complete evidence", field="astronomy").path
        _write_core_fixture(project)
        before = refresh_project_passport(project)["artifacts"]
        result = write_stage_summary(
            project,
            stage="core_evidence",
            command="checkpoint",
            payload={"status": "checkpoint_created"},
            before_artifacts=before,
            checkpoint_id="core-evidence-test",
            checkpoint_hash="checkpoint-test",
            publish_index=False,
        )

        summary = json.loads((project / result["stage_summary_json"]).read_text(encoding="utf-8"))
        html = (project / result["stage_summary_zh_html"]).read_text(encoding="utf-8")
        paths = {item["project_relative_path"] for item in summary["stage_deliverables"]}

        assert "results/figures/figure1.png" in paths
        assert "results/tables/metrics.csv" in paths
        assert "methods/plotting/make_figure.py" in paths
        assert summary["deliverable_counts"]["figure"] >= 1
        assert summary["deliverable_counts"]["table"] >= 1
        assert summary["deliverable_counts"]["code"] >= 1
        assert any(item["operation"] == "unchanged" for item in summary["stage_deliverables"])
        assert summary["core_metrics"]["sample_unit"] == "source"
        assert summary["core_metrics"]["validation_design"] == "source-held-out"
        assert summary["review_state"] == "blocked"
        assert "source_rows=" not in summary["stage_narrative_zh"]
        assert "当前样本流程登记" in summary["stage_narrative_zh"]
        assert {item["name_zh"] for item in summary["consistency_checks"]} >= {
            "指标身份一致性",
            "运行身份一致性",
            "图表统计身份一致性",
        }
        assert "results/figures/figure1.png" in html
        assert "methods/plotting/make_figure.py" in html
        assert html.count('class="figure-preview"') == 1
        assert "图表说明" in html
        assert "图表关键统计" in html
        assert "f1" in html
        assert "证据身份与样本分母" in html
        assert "样本流程" in html


def test_preview_checkpoint_is_non_consumable_and_hides_confirmation_command() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project = create_project(root=tmp, idea="Preview evidence", field="astronomy").path
        checkpoint = checkpoint_project(project, stage="idea")
        ledger = project / "checkpoint_ledger.jsonl"
        ledger_before = ledger.read_text(encoding="utf-8")
        (project / "idea" / "idea.md").write_text("# changed upstream\n", encoding="utf-8")

        preview = preview_checkpoint_summary(project, checkpoint["checkpoint_hash"])
        confirmation = json.loads(Path(preview["confirmation_request"]).read_text(encoding="utf-8"))
        summary = json.loads(Path(preview["stage_summary_json"]).read_text(encoding="utf-8"))

        assert preview["status"] == "preview_only"
        assert summary["review_state"] == "preview_only"
        assert confirmation["confirmation_command"] is None
        assert ledger.read_text(encoding="utf-8") == ledger_before


def test_build_stage_digest_rejects_missing_explicit_artifact_as_blocking() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = create_project(root=tmp, idea="Missing evidence", field="astronomy").path
        digest = build_stage_digest(
            root,
            stage="core_evidence",
            command="checkpoint",
            payload={"status": "checkpoint_created"},
            artifact_manifest={
                "artifacts": [
                    {
                        "project_relative_path": "results/figures/missing.png",
                        "operation": "failed",
                        "after_byte_sha256": None,
                    }
                ]
            },
            checkpoint_hash="checkpoint-test",
        )

        assert digest["review_state"] in {"blocked", "stale"}
        assert digest["unresolved"]


def test_generic_human_stage_adapters_produce_narrative_identity_and_targets() -> None:
    stage_files = {
        "research_plan": "research_plan/research_plan.md",
        "data": "data/data_inventory.json",
        "methods": "methods/method_plan.md",
        "plugin": "plugins/plugin_manifest.json",
        "quality_checks": "quality_checks/quality_report.json",
        "writing": "writing/author_input/packet.md",
        "data_writing": "data/data_writing_context.json",
        "methods_writing": "methods/method_writing_context.json",
    }
    with tempfile.TemporaryDirectory() as tmp:
        project = create_project(root=tmp, idea="All stage summaries", field="workflow engineering").path
        for stage, relative in stage_files.items():
            path = project / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.suffix == ".json":
                path.write_text(
                    json.dumps(
                        {
                            "status": "passed",
                            "run_id": "run-generic",
                            "confirmed_plan_hash": "plan-generic",
                            "validation_design": "source-held-out",
                        }
                    ),
                    encoding="utf-8",
                )
            else:
                path.write_text("# Stage output\n\nGenerated stage evidence.\n", encoding="utf-8")
            digest = build_stage_digest(
                project,
                stage=stage,
                command="stage-checkpoint",
                payload={
                    "status": "completed",
                    "output_path": relative,
                    "run_id": "run-generic",
                    "confirmed_plan_hash": "plan-generic",
                    "validation_design": "source-held-out",
                },
                artifact_manifest={
                    "artifacts": [
                        {
                            "project_relative_path": relative,
                            "operation": "unchanged",
                        }
                    ]
                },
                checkpoint_hash=f"checkpoint-{stage}",
            )

            assert digest["stage_narrative_zh"].startswith("本阶段围绕")
            assert "1 项确认范围内成果" in digest["stage_narrative_zh"]
            assert digest["deliverable_counts"]
            assert digest["inspection_targets"]
            assert digest["identity"]["run_id"] == "run-generic"
            assert digest["identity"]["plan_hash"] == "plan-generic"
            assert digest["claim_boundaries"]


def test_generic_stage_summary_writes_complete_html_for_plan_and_plugin() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project = create_project(root=tmp, idea="Generic HTML stages", field="workflow engineering").path
        for stage, relative in (
            ("research_plan", "research_plan/research_plan.md"),
            ("plugin", "plugins/plugin_manifest.json"),
        ):
            path = project / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# Stage output\n", encoding="utf-8")
            result = write_stage_summary(
                project,
                stage=stage,
                command="stage-checkpoint",
                payload={
                    "status": "completed",
                    "output_path": relative,
                    "run_id": "run-html",
                    "confirmed_plan_hash": "plan-html",
                },
                before_artifacts=[],
                checkpoint_id=f"{stage}-html-test",
                checkpoint_hash=f"hash-{stage}",
                publish_index=False,
            )
            summary = json.loads((project / result["stage_summary_json"]).read_text(encoding="utf-8"))
            html = (project / result["stage_summary_zh_html"]).read_text(encoding="utf-8")
            assert "本阶段围绕" in summary["stage_narrative_zh"]
            assert Path(relative).name in summary["stage_narrative_zh"]
            assert relative in html
            assert "本阶段完整成果" in html
            assert "stage summary hash" in html
            assert summary["identity"]["plan_hash"] == "plan-html"
            assert summary["inspection_targets"]


def test_result_support_summary_exposes_mutually_exclusive_routes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project = create_project(root=tmp, idea="Result support route", field="astronomy").path
        results = project / "results"
        results.mkdir(parents=True, exist_ok=True)
        (results / "result_validity_report.json").write_text(
            json.dumps({"decision": "conditional_pass", "issues": ["threshold not configured"]}),
            encoding="utf-8",
        )
        (results / "result_support_checkpoint.json").write_text(
            json.dumps(
                {
                    "decision": "route_decision_required",
                    "support_level": "failed",
                    "requires_user_decision": True,
                    "metrics": {"primary_f1": 0.71},
                    "metric_records": [{"metric_name": "f1", "value": 0.71, "context": {"run_id": "run-1", "sample_unit": "source"}}],
                    "claim_assessments": [{"claim_id": "c1", "support_status": "supported"}, {"claim_id": "c2", "support_status": "not_supported"}],
                    "failed_claims": [{"claim_id": "c2", "support_status": "not_supported"}],
                    "route_options": [
                        {"route": "downgrade_research_claim", "label": "收窄论断", "description": "保留当前结果。", "stale_policy": "仅下游文字失效。", "current_executable_command": "apply-result-downgrade"},
                        {"route": "supplement_data_and_method", "label": "补充证据", "description": "重跑证据链。", "stale_policy": "数据、方法和结果失效。", "current_executable_command": "prepare-result-rescue"},
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (results / "figures").mkdir(parents=True, exist_ok=True)
        (results / "figures" / "figure1.png").write_bytes(b"not-a-real-png")
        (results / "figure_metadata.json").write_text(
            json.dumps(
                {
                    "figures": [
                        {
                            "path": "results/figures/figure1.png",
                            "figure_id": "Figure 1",
                            "interpretation_summary": "The route review keeps the declared cohort boundary visible.",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        (results / "figure_code_trace.json").write_text(
            json.dumps(
                {
                    "traces": [
                        {
                            "figure_path": "results/figures/figure1.png",
                            "code_files": ["methods/plotting/make_figure.py"],
                            "statistics": {"source_rows": 9},
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        (project / "methods" / "plotting").mkdir(parents=True, exist_ok=True)
        (project / "methods" / "plotting" / "make_figure.py").write_text("print('figure')\n", encoding="utf-8")
        refresh_project_passport(project)
        result = write_stage_summary(
            project,
            stage="result_support",
            command="assess-result-support",
            payload={
                "status": "written",
                "requires_user_decision": True,
                "figure_path": "results/figures/figure1.png",
                "code_files": ["methods/plotting/make_figure.py"],
            },
            before_artifacts=refresh_project_passport(project)["artifacts"],
            checkpoint_id="result-support-route-test",
            publish_index=False,
        )
        summary = json.loads((project / result["stage_summary_json"]).read_text(encoding="utf-8"))
        html = (project / result["stage_summary_zh_html"]).read_text(encoding="utf-8")

        assert summary["review_state"] == "blocked"
        assert len(summary["decision_routes"]) == 2
        assert "人工决策路线" in html
        assert "apply-result-downgrade" in html
        assert "prepare-result-rescue" in html
        assert 'class="figure-preview"' in html
        assert "The route review keeps the declared cohort boundary visible." in html
        assert "methods/plotting/make_figure.py" in html


def test_latest_checkpoint_pointer_precedes_older_ledger_event() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project = create_project(root=tmp, idea="Latest pointer", field="astronomy").path
        checkpoint_project(project, stage="idea")
        latest = write_stage_summary(
            project,
            stage="result_support",
            command="assess-result-support",
            payload={"status": "review_required", "requires_user_decision": True},
            before_artifacts=[],
            checkpoint_id="result-support-latest-test",
            publish_index=True,
        )

        shown = show_checkpoint_summary(project)

        assert shown["status"] == "ready_for_human_review"
        assert shown["summary"]["checkpoint_id"] == "result-support-latest-test"
        assert shown["stage_summary_zh_html"]["project_relative_path"] == latest["stage_summary_zh_html"]
