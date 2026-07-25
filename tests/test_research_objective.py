from __future__ import annotations

import json

import pytest

from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.project_state import load_project
from draftpaper_cli.research_blueprint import build_research_blueprint
from draftpaper_cli.research_objective import ResearchObjectiveError, revise_research_objective
from draftpaper_cli.research_plan import _assert_cn_plan_quality, _cn_term, _render_research_plan_cn
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
    rendered = _render_research_plan_cn(metadata, blueprint)
    _assert_cn_plan_quality(rendered)
    assert "量化天体物理关系" in rendered
    assert "数据处理、统计检验、机器学习模型和可视化只在能够回答这些问题时作为分析工具" in rendered
    assert "第1个科学问题检验什么关系" in rendered


def test_research_objective_requires_three_questions(tmp_path) -> None:
    project = create_project(root=tmp_path, idea="Old objective", field="astronomy").path
    payload = _objective()
    payload["primary_scientific_questions"] = payload["primary_scientific_questions"][:2]
    objective_file = tmp_path / "objective.json"
    objective_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ResearchObjectiveError, match="3 to 8"):
        revise_research_objective(project, objective_file=objective_file)


def test_fallback_storyboard_preserves_bilingual_objective_claims(tmp_path) -> None:
    project = create_project(root=tmp_path, idea="Old objective", field="astronomy").path
    payload = _objective()
    for question in payload["primary_scientific_questions"]:
        question.pop("figure_contract", None)
    objective_file = tmp_path / "objective.json"
    objective_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    revise_research_objective(project, objective_file=objective_file)
    metadata = load_project(project).metadata

    blueprint = build_research_blueprint(
        project_meta=metadata,
        literature_items=[{
            "bibtex_key": "Science2026",
            "title": "Astronomy classifier calibration",
            "abstract": "Grouped validation and calibrated probabilities are assessed.",
            "citation_count": 1,
        }],
        citation_rows=[{
            "citation_key": "Science2026",
            "claim": "current gap",
            "evidence_summary": "A gap.",
        }],
        discipline_profile={"primary_discipline": "astronomy"},
    )

    first = blueprint["figure_storyboard"]["figures"][0]
    assert first["research_question_zh_cn"] == "第1个科学问题检验什么关系？"
    assert first["expected_finding_zh_cn"].startswith("第1个问题应给出")
    rendered = _render_research_plan_cn(metadata, blueprint)
    _assert_cn_plan_quality(rendered)


def test_claim_driven_storyboard_infers_calibration_evidence_contract(tmp_path) -> None:
    project = create_project(root=tmp_path, idea="Old objective", field="astronomy").path
    payload = _objective()
    questions = payload["primary_scientific_questions"]
    questions[0].update({
        "claim_id": "calibration_comparison",
        "research_question": (
            "How do Brier score, log loss, reliability behaviour, and expected "
            "calibration error differ among frozen model predictions?"
        ),
        "research_question_zh_cn": "冻结模型预测的概率校准与可靠性有何差异？",
    })
    questions[1].update({
        "claim_id": "history_increment",
        "research_question": (
            "Does historical context provide a consistent paired improvement "
            "over matched current-event predictions?"
        ),
        "research_question_zh_cn": "历史信息是否带来一致的配对增量？",
    })
    questions[2].update({
        "claim_id": "source_robustness",
        "research_question": (
            "Are aggregate metrics dominated by a small subset of held-out groups "
            "under group-block bootstrap summaries?"
        ),
        "research_question_zh_cn": "汇总指标是否由少数留出组主导？",
    })
    for question in questions:
        question.pop("figure_contract", None)
    payload["primary_scientific_questions"].append({
        "claim_id": "failure_structure",
        "research_question": (
            "Which held-out groups and confidence regimes account for recurrent "
            "misclassification or overconfidence?"
        ),
        "research_question_zh_cn": "哪些留出组和置信区间贡献重复误分类或过度置信？",
        "expected_finding": "Failure concentration is categorical grouped evidence.",
        "expected_finding_zh_cn": "失败集中属于分组类别证据。",
    })
    objective_file = tmp_path / "objective.json"
    objective_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    revise_research_objective(project, objective_file=objective_file)

    blueprint = build_research_blueprint(
        project_meta=load_project(project).metadata,
        literature_items=[{
            "bibtex_key": "Calibration2026",
            "title": "Grouped probability calibration",
            "abstract": "Reliability and proper scoring rules are evaluated by group.",
            "citation_count": 1,
        }],
        citation_rows=[{
            "citation_key": "Calibration2026",
            "claim": "calibration evaluation",
            "evidence_summary": "Grouped evaluation is required.",
        }],
        discipline_profile={"primary_discipline": "astronomy"},
    )

    figures = blueprint["figure_storyboard"]["figures"]
    assert len(figures) == 6
    assert figures[0]["proposed_title"] == "Analysis cohort and frozen-evidence alignment"
    assert figures[1]["proposed_title"] == "Probability calibration and reliability across model outputs"
    assert figures[1]["proposed_title_zh_cn"] == "不同模型输出的概率校准与可靠性"
    assert "proper_scoring_rules" in figures[1]["required_method"]
    assert figures[2]["suggested_plot_type"] == "paired_effect_summary"
    assert figures[3]["suggested_plot_type"] == "group_robustness_summary"
    assert figures[4]["suggested_plot_type"] == "error_calibration_summary"
    assert figures[5]["proposed_title"] == "Integrated evidence and final claim boundary"
    assert all(figure.get("scientific_claim_boundary") for figure in figures)
    assert all(figure.get("scientific_claim_boundary_zh_cn") for figure in figures)
    rendered = _render_research_plan_cn(load_project(project).metadata, blueprint)
    _assert_cn_plan_quality(rendered)
    assert "独立采样单位" in rendered
    for leaked_term in ("DINOv2", "形态与物理状态", "图像层复核", "独立星系样本数"):
        assert leaked_term not in rendered


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
