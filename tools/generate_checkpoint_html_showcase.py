"""Generate anonymous human-checkpoint HTML pages for framework review."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from draftpaper_cli.checkpoint_summary import write_stage_summary
from draftpaper_cli.code_ownership import trace_figures_to_code
from draftpaper_cli.passport import refresh_project_passport
from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.result_evidence import resolve_result_evidence


def _write_json(root: Path, relative: str, payload: Any) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_text(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_figure(root: Path, relative: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (960, 560), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((50, 40, 910, 510), outline="#334155", width=3)
    draw.line((120, 450, 840, 450), fill="#334155", width=3)
    draw.line((120, 450, 120, 100), fill="#334155", width=3)
    for index, height in enumerate((160, 230, 300), start=1):
        x = 220 + (index - 1) * 190
        draw.rectangle((x, 450 - height, x + 100, 450), fill=(31, 120, 180), outline="#0f172a")
        draw.text((x + 18, 460), f"model-{index}", fill="#0f172a")
        draw.text((x + 18, 430 - height), f"{height / 400:.2f}", fill="#0f172a")
    draw.text((145, 62), "Anonymous metric evidence fixture", fill="#0f172a")
    image.save(path)


def _write_core_fixture(root: Path) -> None:
    _write_text(
        root,
        "results/tables/canonical_metrics.csv",
        "run_id,metric,value,model_id,task_id,cohort_id,sample_unit,validation_design_id,split_id,aggregation_id,uncertainty_definition_id,metric_dimension,evidence_role\n"
        "run-core,macro_f1,0.81,model-a,task-a,cohort-core,entity,group-held-out,test,none,none,score,primary\n",
    )
    _write_json(
        root,
        "methods/primary_metric_contract.json",
        {
            "schema_version": "dpl.primary_metric_contract.v1",
            "metric_definition_id": "macro_f1",
            "task_id": "task-a",
            "cohort_id": "cohort-core",
            "sample_unit": "entity",
            "model_id": "model-a",
            "validation_design_id": "group-held-out",
            "split_id": "test",
            "aggregation_id": "none",
            "uncertainty_definition_id": "none",
        },
    )
    _write_json(
        root,
        "methods/run_manifest.yaml",
        {
            "status": "success",
            "run_id": "run-core",
            "run_transaction_id": "txn-core",
            "cohort_id": "cohort-core",
            "sample_unit": "entity",
            "evaluation_split": "test",
            "output_files": ["results/tables/canonical_metrics.csv"],
            "count_evidence": [
                {
                    "count_definition_id": "catalog_entity_count",
                    "entity_type": "entity",
                    "count_mode": "unique_entities",
                    "cohort_id": "cohort-core",
                    "filter_contract_id": "quality-v1",
                    "sample_unit": "entity",
                    "value": 48,
                    "evidence_role": "catalog",
                },
                {
                    "count_definition_id": "model_cohort_count",
                    "entity_type": "entity",
                    "count_mode": "model_members",
                    "cohort_id": "cohort-core",
                    "filter_contract_id": "quality-v1",
                    "sample_unit": "entity",
                    "value": 32,
                    "evidence_role": "model_cohort",
                },
            ],
        },
    )
    _write_json(root, "results/result_validity_report.json", {"decision": "pass", "resolved_run_id": "run-core"})
    _write_json(
        root,
        "results/figure_metadata.json",
        {
            "figures": [
                {
                    "path": "results/figures/figure_core.png",
                    "figure_id": "fig-core",
                    "caption": "The declared model comparison under the held-out contract.",
                    "interpretation_summary": "The figure is limited to the declared cohort and metric identity.",
                }
            ]
        },
    )
    _write_json(
        root,
        "core_evidence/core_evidence_report.json",
        {
            "decision": "pass",
            "promoted_evidence_snapshot_id": "snapshot-core",
            "reviewable_figures": [
                {
                    "path": "results/figures/figure_core.png",
                    "caption": "The declared model comparison under the held-out contract.",
                    "interpretation_summary": "The figure is limited to the declared cohort and metric identity.",
                }
            ],
        },
    )
    _write_figure(root, "results/figures/figure_core.png")
    _write_text(root, "methods/plotting/make_figure.py", "# anonymous fixture\nprint('figure-core')\n")
    resolved = resolve_result_evidence(root)
    primary = resolved["metric_identity_report"]["primary_metric"]["record"]
    _write_json(
        root,
        "results/result_support_checkpoint.json",
        {
            "decision": "pass",
            "support_level": "supported",
            "metric_records": [
                {
                    "metric_record_id": primary["metric_record_id"],
                    "value": primary["value"],
                    "context": {
                        "run_id": "run-core",
                        "cohort_id": "cohort-core",
                        "sample_unit": "entity",
                        "validation_design": "group-held-out",
                        "split_id": "test",
                        "model_id": "model-a",
                        "metric_definition_id": "macro_f1",
                        "task_id": "task-a",
                        "aggregation_id": "none",
                        "uncertainty_definition_id": "none",
                    },
                }
            ],
            "claim_assessments": [{"claim_boundary": "Only the declared cohort and validation design are covered."}],
        },
    )
    _write_json(
        root,
        "results/result_manifest.yaml",
        {"figures": [{"path": "results/figures/figure_core.png", "caption": "Declared comparison"}]},
    )
    trace_figures_to_code(root)
    resolve_result_evidence(root)


def _write_stage_inputs(root: Path) -> None:
    _write_text(root, "research_plan/research_plan.zh-CN.md", "# 匿名研究蓝图\n\n确认研究问题、数据角色和论断边界。\n")
    _write_json(root, "research_plan/feasibility.json", {"status": "pass", "scope": "anonymous fixture"})
    _write_json(root, "data/inventory.json", {"status": "verified", "entity_type": "entity", "count": 48})
    _write_json(root, "data/quality_report.json", {"decision": "pass", "filter_contract_id": "quality-v1"})
    _write_text(root, "data/sample_flow.csv", "count_definition_id,entity_type,count_mode,value\ncatalog_entity_count,entity,unique_entities,48\n")
    _write_json(root, "methods/method_plan.json", {"status": "verified", "method_family": "anonymous-baseline"})
    _write_text(root, "methods/scripts/execute_analysis.py", "# anonymous fixture\nprint('analysis')\n")
    _write_json(root, "quality_checks/final_quality_report.json", {"decision": "pass", "checks": ["html", "identity", "paths"]})
    _write_json(root, "citation_audit/final_citation_audit.json", {"status": "passed", "cited_reference_count": 3})
    _write_text(root, "latex/main.tex", "\\documentclass{article}\n\\begin{document}Anonymous fixture.\\end{document}\n")


def _write_route_checkpoint(root: Path) -> None:
    _write_json(
        root,
        "results/result_support_checkpoint.json",
        {
            "decision": "route_decision_required",
            "support_level": "failed",
            "requires_user_decision": True,
            "route_options": [
                {
                    "route": "downgrade_research_claim",
                    "label": "收窄论断",
                    "description": "保留当前可支持的结果边界。",
                    "stale_policy": "只重建下游论断和写作。",
                    "current_executable_command": "apply-result-downgrade",
                },
                {
                    "route": "supplement_data_and_method",
                    "label": "补充数据与方法证据",
                    "description": "补充或重跑当前证据链。",
                    "stale_policy": "数据、方法、结果和下游稿件重新进入待确认状态。",
                    "current_executable_command": "prepare-result-rescue",
                },
            ],
            "claim_assessments": [{"claim_id": "claim-core", "support_status": "not_supported"}],
        },
    )


def generate(output_root: Path) -> dict[str, Any]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_root = output_root / f"run-{stamp}"
    project = create_project(
        root=run_root,
        idea="Anonymous cross-discipline checkpoint evidence",
        field="generic scientific workflow",
        target_journal="Anonymous Fixture Journal",
        project_slug_override="anonymous-checkpoint-showcase",
        project_id_override="showcase01",
    ).path
    _write_core_fixture(project)
    _write_stage_inputs(project)

    stages = ("research_plan", "data", "methods", "result_support", "core_evidence", "quality_checks")
    reports: list[dict[str, Any]] = []
    for stage in stages:
        if stage == "result_support":
            _write_route_checkpoint(project)
        elif stage == "core_evidence":
            _write_core_fixture(project)
        before = refresh_project_passport(project)["artifacts"]
        report = write_stage_summary(
            project,
            stage=stage,
            command=f"test-showcase-{stage}",
            payload={
                "status": "checkpoint_created",
                "test_mode": True,
                "test_auto_confirmation": True,
                "confirmed_plan_hash": "plan-showcase",
                "summary": "Anonymous framework fixture generated this checkpoint for HTML review.",
            },
            before_artifacts=before,
            checkpoint_id=f"showcase-{stage}",
            checkpoint_hash=f"showcase-hash-{stage}",
            publish_index=True,
        )
        reports.append(
            {
                "stage": stage,
                "review_state": json.loads((project / report["stage_summary_json"]).read_text(encoding="utf-8"))["review_state"],
                "project_relative_html": report["stage_summary_zh_html"],
                "absolute_html": report["absolute_stage_summary_zh_html"],
                "absolute_summary": report["absolute_stage_summary_json"],
                "test_auto_confirmation": True,
            }
        )
    manifest = {"schema_version": "dpl.checkpoint_html_showcase.v1", "project": str(project), "checkpoints": reports}
    output_root.mkdir(parents=True, exist_ok=True)
    manifest_path = run_root / "showcase_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {**manifest, "manifest_path": str(manifest_path.resolve())}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=Path(".tmp/framework-html-showcase"))
    args = parser.parse_args()
    print(json.dumps(generate(args.output_root.resolve()), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
