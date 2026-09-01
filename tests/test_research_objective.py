from __future__ import annotations

import json

import pytest

from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.project_state import load_project
from draftpaper_cli.research_blueprint import build_research_blueprint
from draftpaper_cli.research_objective import ResearchObjectiveError, revise_research_objective
from draftpaper_cli.research_plan import (
    _assert_cn_plan_quality,
    _cn_term,
    _load_research_data_context,
    _render_research_plan_cn,
)
from draftpaper_cli.research_plan_confirmation import _refresh_cn_plan_projection


def _objective() -> dict:
    questions = []
    for index in range(1, 4):
        questions.append({
            "claim_id": f"claim_{index}",
            "research_question": f"What scientific relationship is tested in question {index}?",
            "research_question_zh_cn": f"第{index}个科学问题检验什么关系？",
            "expected_finding": f"Question {index} should produce a bounded scientific estimate.",
            "expected_finding_zh_cn": f"第{index}个问题应给出具有明确边界的科学估计。",
            "figure_contract": {
                "proposed_title": f"Scientific relationship {index}",
                "proposed_title_zh_cn": f"科学关系{index}",
                "story_role": "direct_scientific_signal",
                "required_data": ["scientific_sample", "physical_measurement"],
                "required_method": ["controlled_association"],
                "suggested_plot_type": "effect_summary",
                "validation_metric": "effect_size_with_uncertainty",
                "panels": [{
                    "label": "a",
                    "scientific_role": "controlled estimate",
                    "required_method": "controlled_association",
                    "required_data_roles": ["scientific_sample", "physical_measurement"],
                    "expected_content": "Estimate the scientific association with uncertainty.",
                    "expected_content_zh_cn": "估计科学关联及其不确定性。",
                }],
            },
        })
    return {
        "working_title": "A science-first study",
        "working_title_zh_cn": "科学问题优先的研究",
        "scientific_objective": "Quantify an astrophysical relationship while treating machine learning as a measurement tool.",
        "scientific_objective_zh_cn": "量化天体物理关系，并将机器学习仅作为测量工具。",
        "primary_scientific_questions": questions,
        "table_contracts": [
            {
                "table_id": f"table_{index}",
                "proposed_title": f"Scientific summary {index}",
                "proposed_title_zh_cn": f"科学汇总表{index}",
                "required_data": ["scientific_sample"],
                "required_method": ["controlled_summary"],
                "expected_content": f"Report bounded result family {index}.",
                "expected_content_zh_cn": f"报告第{index}组有边界的结果。",
                "validation_metric": "estimate_with_uncertainty",
            }
            for index in range(1, 4)
        ],
        "methodological_hypothesis": "The representation can provide a useful measurement after confounder control.",
        "methodological_hypothesis_zh_cn": "控制混杂因素后，图像表示可以提供有用测量。",
        "data_scope": ["One explicitly defined survey cohort."],
        "data_scope_zh_cn": ["一个明确定义的巡天样本队列"],
        "secondary_analyses": ["Method benchmarking."],
        "secondary_analyses_zh_cn": ["方法性能验证"],
        "claim_boundary": "The study is exploratory and does not establish causal evolution.",
        "claim_boundary_zh_cn": "本研究属于探索性研究，不能据此建立因果演化结论。",
        "field": "astronomy machine learning",
    }


def test_revise_research_objective_updates_managed_metadata_and_stales_chain(tmp_path) -> None:
    project = create_project(
        root=tmp_path,
        idea="Method-centred old objective",
        field="astronomy",
        target_journal="ApJS",
    ).path
    objective_file = tmp_path / "objective.json"
    objective_file.write_text(json.dumps(_objective(), ensure_ascii=False), encoding="utf-8")

    report = revise_research_objective(project, objective_file=objective_file)
    state = load_project(project)

    assert report["status"] == "revised"
    assert state.metadata["idea"].startswith("Quantify an astrophysical relationship")
    assert state.metadata["research_objective"]["primary_scientific_questions"][0]["claim_id"] == "claim_1"
    assert state.metadata["stages"]["references"]["stale"] is True
    assert "## Scientific Objective" in (project / "idea" / "idea.md").read_text(encoding="utf-8")


def test_objective_contract_drives_claims_storyboard_and_chinese_plan(tmp_path) -> None:
    project = create_project(root=tmp_path, idea="Old objective", field="astronomy").path
    objective_file = tmp_path / "objective.json"
    objective_file.write_text(json.dumps(_objective(), ensure_ascii=False), encoding="utf-8")
    revise_research_objective(project, objective_file=objective_file)
    metadata = load_project(project).metadata

    blueprint = build_research_blueprint(
        project_meta=metadata,
        literature_items=[{
            "bibtex_key": "Science2026",
            "title": "An astronomy measurement study",
            "abstract": "Physical measurements and image structure are compared.",
            "citation_count": 3,
        }],
        citation_rows=[{"citation_key": "Science2026", "claim": "current gap", "evidence_summary": "A gap."}],
        discipline_profile={"primary_discipline": "astronomy"},
        data_context={"status": "inventory_available", "table_summaries": [], "role_coverage": {}},
    )

    assert blueprint["research_claims"][0]["research_question"].startswith("What scientific relationship")
    assert blueprint["figure_storyboard"]["figures"][0]["proposed_title"] == "Scientific relationship 1"
    assert blueprint["figure_storyboard"]["figures"][0]["required_method"] == ["controlled_association"]
    assert [item["table_id"] for item in blueprint["figure_storyboard"]["tables"]] == [
        "table_1",
        "table_2",
        "table_3",
    ]
    rendered = _render_research_plan_cn(metadata, blueprint)
    _assert_cn_plan_quality(rendered)
    assert "量化天体物理关系" in rendered
    assert "机器学习、聚类、分类器和空间分析只在能够回答上述科学问题时作为分析工具" in rendered
    assert "第1个科学问题检验什么关系" in rendered


def test_chinese_plan_is_discipline_neutral_and_localizes_agricultural_metrics(tmp_path) -> None:
    project = create_project(root=tmp_path, idea="Old objective", field="crop remote sensing").path
    payload = _objective()
    payload["working_title_zh_cn"] = "中国强筋小麦遥感制图"
    payload["scientific_objective_zh_cn"] = "量化中国强筋小麦分布及农业气候适宜性。"
    payload["field"] = "crop remote sensing"
    payload["primary_scientific_questions"][0]["figure_contract"]["validation_metric"] = (
        "macro_f1_balanced_accuracy_user_accuracy_producer_accuracy_and_expected_calibration_error"
    )
    objective_file = tmp_path / "objective.json"
    objective_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    revise_research_objective(project, objective_file=objective_file)
    metadata = load_project(project).metadata
    blueprint = build_research_blueprint(
        project_meta=metadata,
        literature_items=[{"bibtex_key": "Crop2026", "title": "Crop mapping evidence", "citation_count": 1}],
        citation_rows=[{"citation_key": "Crop2026", "claim": "current gap", "evidence_summary": "Gap."}],
        discipline_profile={"primary_discipline": "geography"},
        data_context={"status": "inventory_available", "table_summaries": [], "role_coverage": {}},
    )

    rendered = _render_research_plan_cn(metadata, blueprint)

    _assert_cn_plan_quality(rendered)
    assert "宏平均F1、平衡准确率、用户精度、生产者精度及期望校准误差" in rendered
    assert "天体物理" not in rendered
    assert "独立星系样本数" not in rendered


def test_research_objective_requires_three_questions(tmp_path) -> None:
    project = create_project(root=tmp_path, idea="Old objective", field="astronomy").path
    payload = _objective()
    payload["primary_scientific_questions"] = payload["primary_scientific_questions"][:2]
    objective_file = tmp_path / "objective.json"
    objective_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ResearchObjectiveError, match="3 to 8"):
        revise_research_objective(project, objective_file=objective_file)


def test_research_objective_rejects_duplicate_table_ids(tmp_path) -> None:
    project = create_project(root=tmp_path, idea="Old objective", field="astronomy").path
    payload = _objective()
    payload["table_contracts"][1]["table_id"] = payload["table_contracts"][0]["table_id"]
    objective_file = tmp_path / "objective.json"
    objective_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ResearchObjectiveError, match="Duplicate table_id"):
        revise_research_objective(project, objective_file=objective_file)


def test_research_objective_limits_table_contracts_to_eight(tmp_path) -> None:
    project = create_project(root=tmp_path, idea="Old objective", field="astronomy").path
    payload = _objective()
    payload["table_contracts"] = [
        {
            "table_id": f"table_{index}",
            "proposed_title": f"Scientific summary {index}",
            "required_data": ["scientific_sample"],
            "required_method": ["controlled_summary"],
        }
        for index in range(1, 10)
    ]
    objective_file = tmp_path / "objective.json"
    objective_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ResearchObjectiveError, match="at most 8 tables"):
        revise_research_objective(project, objective_file=objective_file)


def test_research_data_context_suppresses_duplicate_inventory_rows(tmp_path) -> None:
    project = create_project(root=tmp_path, idea="Duplicate inventory", field="machine learning").path
    inventory = {
        "file_count": 2,
        "total_rows": 20,
        "files": [
            {"path": "data/processed/features.csv", "row_count": 10, "column_count": 3},
            {"path": "data/processed/features.csv", "row_count": 10, "column_count": 3},
        ],
    }
    (project / "data" / "data_inventory.json").write_text(
        json.dumps(inventory), encoding="utf-8"
    )

    context = _load_research_data_context(project)

    assert [item["logical_name"] for item in context["table_summaries"]] == ["features.csv"]


def test_science_objective_figure_roles_have_chinese_labels() -> None:
    assert _cn_term("image_validity") == "图像有效性记录"
    assert _cn_term("confounder_adjusted_association") == "混杂因素调整后的关联分析"
    assert _cn_term("selection_sensitivity_analysis") == "选择效应敏感性分析"
    assert _cn_term("rank_stability_and_quality_screen_pass_rate") == "排序稳定性与质量筛查通过率"
    assert _cn_term(
        "planned confirmatory or predictive claims are supportable by the current data gate"
    ) == "当前数据门能够支撑计划中的确认性或预测性主张"
    assert _cn_term(
        "held_out_macro_f1_balanced_accuracy_roc_auc_and_expected_calibration_error"
    ) == "留出集macro-F1、平衡准确率、ROC-AUC及期望校准误差"


def test_agricultural_plan_terms_are_localized_without_corrupting_paths() -> None:
    assert _cn_term("multi_year_optical_and_sar_observations") == "多年光学与SAR观测"
    assert _cn_term("spatially_blocked_suitability_model") == "空间分块适宜性模型"
    assert _cn_term(
        "area_adjusted_user_and_producer_accuracy_with_95_percent_confidence_intervals"
    ) == "面积校正的用户精度、生产者精度及95%置信区间"
    assert _cn_term(r"D:\SW_Maping中的只读谱系材料") == r"D:\SW_Maping中的只读谱系材料"


def test_review_projection_uses_final_statistical_contract(tmp_path) -> None:
    project = create_project(root=tmp_path, idea="Old objective", field="astronomy").path
    objective_file = tmp_path / "objective.json"
    objective_file.write_text(json.dumps(_objective(), ensure_ascii=False), encoding="utf-8")
    revise_research_objective(project, objective_file=objective_file)
    metadata = load_project(project).metadata
    blueprint = build_research_blueprint(
        project_meta=metadata,
        literature_items=[{"bibtex_key": "Science2026", "title": "Astronomy evidence", "citation_count": 1}],
        citation_rows=[{"citation_key": "Science2026", "claim": "current gap", "evidence_summary": "Gap."}],
        discipline_profile={"primary_discipline": "astronomy"},
    )
    (project / "research_plan" / "research_blueprint.json").write_text(
        json.dumps(blueprint, ensure_ascii=False), encoding="utf-8"
    )
    (project / "research_plan" / "statistical_validation_contract.json").write_text(
        json.dumps({"task_families": ["sampling_and_independence", "spatial_validation"]}),
        encoding="utf-8",
    )
    (project / "research_plan" / "research_plan.zh-CN.md").write_text("stale projection", encoding="utf-8")

    digest = _refresh_cn_plan_projection(project)
    text = (project / "research_plan" / "research_plan.zh-CN.md").read_text(encoding="utf-8")

    assert len(digest) == 64
    assert "## 统计验证计划" in text
    assert "空间依赖" in text
    assert "stale projection" not in text
