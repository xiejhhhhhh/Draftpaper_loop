# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from .claim_contract import build_claim_contract_from_blueprint
from .discipline import infer_discipline_profile
from .discipline_modules import get_discipline_module
from .html_utils import write_html_report
from .journal_profile import JournalProfileError, validate_journal_profile_for_writing
from .project_scaffold import _write_json
from .project_state import load_project, update_stage_status
from .research_blueprint import ResearchBlueprintQualityError, build_research_blueprint


RESEARCH_PLAN_INPUTS = [
    "idea/idea.md",
    "references/literature_items.json",
    "references/citation_evidence.csv",
    "references/literature_review_notes.md",
    "journal_profile/journal_profile.json",
    "journal_profile/journal_guidelines.md",
]

RESEARCH_PLAN_OUTPUTS = [
    "research_plan/research_plan.md",
    "research_plan/research_plan.zh-CN.md",
    "research_plan/research_blueprint.json",
    "research_plan/claim_contract.json",
    "research_plan/figure_storyboard.json",
    "research_plan/method_plan.json",
    "research_plan/discipline_contract.json",
    "research_plan/research_capability_contract.json",
    "research_plan/statistical_validation_contract.json",
    "research_plan/statistical_validation_contract.md",
    "research_plan/review_rule_coverage_report.json",
    "research_plan/review_rule_coverage_report.html",
    "research_plan/research_plan_confirmation_required.json",
    "research_plan/target_journal_anchor_papers.json",
    "research_plan/novelty_overlap_report.json",
    "research_plan/novelty_overlap_report.md",
    "research_plan/novelty_overlap_report.html",
]

MINIMUM_RESEARCH_PLAN_FIGURES = 5
TARGET_RESEARCH_PLAN_FIGURES = 6
MINIMUM_RESEARCH_PLAN_TABLES = 1
TARGET_RESEARCH_PLAN_TABLES = 2


class MissingReferencesError(FileNotFoundError):
    """Raised when the formal research plan is requested before references exist."""


class NoveltyOverlapError(RuntimeError):
    """Raised when retrieved literature appears too similar to the proposed study."""

    def __init__(self, message: str, report_path: Path) -> None:
        super().__init__(message)
        self.report_path = report_path


class ResearchPlanQualityError(RuntimeError):
    """Raised when the generated research plan is too incomplete for downstream loop stages."""


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _read_citation_evidence(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _require_reference_inputs(project_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, str]], str]:
    missing = [relative for relative in RESEARCH_PLAN_INPUTS[1:] if not (project_path / relative).exists()]
    if missing:
        raise MissingReferencesError(
            "Formal research planning requires references outputs first. Missing: " + ", ".join(missing)
        )
    literature_items = _read_json(project_path / "references" / "literature_items.json")
    citation_rows = _read_citation_evidence(project_path / "references" / "citation_evidence.csv")
    literature_notes = (project_path / "references" / "literature_review_notes.md").read_text(encoding="utf-8")
    if not isinstance(literature_items, list) or not literature_items:
        raise MissingReferencesError("references/literature_items.json must contain at least one literature item.")
    if not citation_rows:
        raise MissingReferencesError("references/citation_evidence.csv must contain at least one evidence row.")
    return literature_items, citation_rows, literature_notes


def _compact(text: str, limit: int = 260) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rsplit(" ", 1)[0] + "..."


def _top_items(literature_items: list[dict[str, Any]], limit: int = 6) -> list[dict[str, Any]]:
    return sorted(literature_items, key=lambda item: int(item.get("citation_count") or 0), reverse=True)[:limit]


def _tokens(text: str) -> set[str]:
    stopwords = {
        "the", "and", "for", "with", "using", "based", "from", "this", "that", "study", "paper",
        "method", "methods", "model", "models", "data", "analysis", "research", "framework",
    }
    return {
        token
        for token in re.findall(r"[a-zA-Z][a-zA-Z0-9-]{2,}", (text or "").lower())
        if token not in stopwords
    }


def _study_context(project_path: Path, project_meta: dict[str, Any]) -> str:
    parts = [project_meta.get("title", ""), project_meta.get("idea", ""), project_meta.get("field", "")]
    for relative in [
        "idea/idea.md",
        "data/data_inventory.json",
        "data/data_feasibility_report.json",
        "methods/method_plan.md",
        "methods/method_requirements.json",
    ]:
        path = project_path / relative
        if path.exists():
            parts.append(path.read_text(encoding="utf-8", errors="replace")[:4000])
    return " ".join(parts)


def _journal_aliases(target_journal: str) -> set[str]:
    normalized = (target_journal or "").lower()
    aliases = {normalized} if normalized else set()
    if "apjs" in normalized or "supplement" in normalized:
        aliases.update({"apjs", "astrophysical journal supplement", "astrophysical journal supplement series", "aas journals"})
    if "apj" in normalized or "astrophysical journal" in normalized:
        aliases.update({"apj", "astrophysical journal", "aas journals"})
    return {alias for alias in aliases if alias}


def _similarity_score(study_terms: set[str], item: dict[str, Any]) -> float:
    item_text = " ".join([
        str(item.get("title") or ""),
        str(item.get("abstract") or ""),
        str((item.get("deep_summary") or {}).get("methods") or ""),
        str((item.get("deep_summary") or {}).get("data_used") or ""),
    ])
    item_terms = _tokens(item_text)
    if not study_terms or not item_terms:
        return 0.0
    return round((2 * len(study_terms & item_terms)) / (len(study_terms) + len(item_terms)), 3)


def _pair_similarity(left: str, right: str) -> float:
    left_terms = _tokens(left)
    right_terms = _tokens(right)
    if not left_terms or not right_terms:
        return 0.0
    return round((2 * len(left_terms & right_terms)) / (len(left_terms) + len(right_terms)), 3)


def analyze_target_journal_literature(
    project_path: Path,
    project_meta: dict[str, Any],
    literature_items: list[dict[str, Any]],
    *,
    high_similarity_threshold: float = 0.82,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    study_terms = _tokens(_study_context(project_path, project_meta))
    aliases = _journal_aliases(project_meta.get("target_journal", ""))
    enriched = []
    for item in literature_items:
        publication = str(item.get("publication") or "").lower()
        journal_match = any(alias in publication for alias in aliases)
        similarity = max(
            _similarity_score(study_terms, item),
            _pair_similarity(str(project_meta.get("idea") or ""), str(item.get("title") or "")),
            _pair_similarity(str(project_meta.get("title") or ""), str(item.get("title") or "")),
        )
        anchor_score = round(
            (0.55 * float(item.get("citation_weight") or 0))
            + (0.35 * similarity)
            + (0.10 if journal_match else 0.0),
            3,
        )
        enriched.append({
            "citation_key": item.get("bibtex_key", ""),
            "title": item.get("title", ""),
            "publication": item.get("publication", ""),
            "year": item.get("year", ""),
            "doi": item.get("doi", ""),
            "url": item.get("url", ""),
            "citation_weight": item.get("citation_weight", 0),
            "target_journal_match": journal_match,
            "study_similarity_score": similarity,
            "anchor_score": anchor_score,
            "evidence_summary": item.get("evidence_notes") or "",
        })
    anchors = sorted(enriched, key=lambda item: (item["anchor_score"], item["target_journal_match"]), reverse=True)[:8]
    high_similarity = sorted(
        [item for item in enriched if item["study_similarity_score"] >= high_similarity_threshold],
        key=lambda item: item["study_similarity_score"],
        reverse=True,
    )
    report = {
        "target_journal": project_meta.get("target_journal"),
        "high_similarity_threshold": high_similarity_threshold,
        "high_similarity_found": bool(high_similarity),
        "high_similarity_count": len(high_similarity),
        "highest_similarity_score": max((item["study_similarity_score"] for item in enriched), default=0.0),
        "high_similarity_items": high_similarity,
        "recommended_action": (
            "Ask the user whether to continue, revise the research question, change the data or method route, or reposition the manuscript."
            if high_similarity else
            "Proceed, using target-journal anchor papers as structural references without copying claims or wording."
        ),
    }
    return anchors, report


def _write_novelty_report_md(path: Path, report: dict[str, Any], anchors: list[dict[str, Any]]) -> None:
    lines = [
        "# Novelty and Target-Journal Anchor Report",
        "",
        f"Target journal: {report.get('target_journal')}",
        "",
        f"High similarity found: {str(report.get('high_similarity_found')).lower()}",
        "",
        f"Highest similarity score: {report.get('highest_similarity_score')}",
        "",
        "## High-Similarity Items",
        "",
    ]
    for item in report.get("high_similarity_items") or []:
        lines.append(f"- `{item.get('citation_key')}` {item.get('title')} ({item.get('publication')}, similarity={item.get('study_similarity_score')})")
    if not report.get("high_similarity_items"):
        lines.append("- None.")
    lines.extend(["", "## Target-Journal Anchor Papers", ""])
    for item in anchors:
        lines.append(f"- `{item.get('citation_key')}` {item.get('title')} ({item.get('publication')}, anchor={item.get('anchor_score')}, similarity={item.get('study_similarity_score')})")
    lines.extend(["", "## Recommended Action", "", str(report.get("recommended_action") or "")])
    markdown = "\n".join(lines) + "\n"
    path.write_text(markdown, encoding="utf-8")
    write_html_report(path.with_suffix(".html"), markdown, title="Novelty and Target-Journal Anchor Report")


def _evidence_by_claim(citation_rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in citation_rows:
        grouped.setdefault(row.get("claim") or "background evidence", []).append(row)
    return grouped


def _format_evidence_sentence(row: dict[str, str]) -> str:
    key = row.get("citation_key", "unknown")
    summary = _compact(row.get("evidence_summary", ""))
    return f"`{key}` supports the {row.get('claim', 'evidence')} claim: {summary}"


def _infer_data_requirements(project_meta: dict[str, Any], evidence_rows: list[dict[str, str]]) -> str:
    blob = " ".join(
        [project_meta.get("idea", ""), project_meta.get("field", "")]
        + [row.get("evidence_summary", "") for row in evidence_rows]
    ).lower()
    requirements = []
    if any(term in blob for term in ["multimodal", "photometric", "spectroscopic", "survey", "time-domain"]):
        requirements.append("multimodal survey records with aligned object identifiers, observation times, and quality flags")
    if any(term in blob for term in ["image", "figure", "vision"]):
        requirements.append("image-derived or visual feature products with reproducible preprocessing metadata")
    if any(term in blob for term in ["external validation", "validation", "generalization"]):
        requirements.append("an external validation split or independent dataset to test generalization")
    if not requirements:
        requirements.append("a documented primary dataset with reproducible preprocessing and quality-control metadata")
    return "; ".join(requirements) + "."


def _infer_method_route(project_meta: dict[str, Any], evidence_rows: list[dict[str, str]]) -> str:
    blob = " ".join(
        [project_meta.get("idea", ""), project_meta.get("field", "")]
        + [row.get("evidence_summary", "") for row in evidence_rows]
    ).lower()
    if "transformer" in blob or "attention" in blob:
        return (
            "Start with a transparent baseline model, then evaluate a transformer or attention-based model for sequence "
            "and multimodal feature fusion. The method section should report preprocessing, feature alignment, model "
            "inputs, validation protocol, ablation design, and uncertainty handling."
        )
    if "multimodal" in blob:
        return (
            "Construct modality-specific feature blocks, compare single-modality baselines with fused models, and use "
            "ablation tests to show which data source adds value."
        )
    return "Define baseline models first, then introduce the proposed method only where it directly addresses the literature-supported gap."


def _research_plan_output_policy(discipline_profile: dict[str, Any] | None = None) -> dict[str, int | str]:
    module = get_discipline_module(discipline_profile or {})
    module_spec = module.spec.as_dict()
    minimum_figures = max(MINIMUM_RESEARCH_PLAN_FIGURES, int(module_spec.get("minimum_main_figures") or 0))
    target_figures = max(TARGET_RESEARCH_PLAN_FIGURES, minimum_figures, int(module_spec.get("target_main_figures") or 0))
    return {
        "discipline": str(module_spec.get("module_id") or "default"),
        "minimum_figures": minimum_figures,
        "target_figures": target_figures,
        "minimum_tables": MINIMUM_RESEARCH_PLAN_TABLES,
        "target_tables": TARGET_RESEARCH_PLAN_TABLES,
    }


def _expected_figure_lines(policy: dict[str, int | str]) -> list[str]:
    specs = [
        "Study workflow from data acquisition, data construction, quality control, method execution, validation, and interpretation.",
        "Data source, sample coverage, missingness, and preprocessing overview, including the evidence needed to judge whether the planned study is feasible.",
        "Proposed model or analytical framework, including the components that directly address the literature-supported research gap.",
        "Baseline comparison and ablation or sensitivity design, so the proposed method can be separated from simpler alternatives.",
        "Validation and uncertainty assessment, including external, temporal, spatial, class-stratified, or reviewer-relevant checks when the discipline requires them.",
        "Main result synthesis figure that connects the strongest empirical patterns to the manuscript claim boundary and highlights failure modes or limitations.",
    ]
    target = int(policy.get("target_figures") or TARGET_RESEARCH_PLAN_FIGURES)
    while len(specs) < target:
        specs.append("Additional discipline-specific diagnostic or supplementary main figure required by the target journal, reviewer risks, or data structure.")
    return [f"- Fig. {index}: {text}" for index, text in enumerate(specs[:target], start=1)]


def _expected_table_lines(policy: dict[str, int | str]) -> list[str]:
    specs = [
        "Dataset summary, data provenance, preprocessing choices, quality-control criteria, and validation split design.",
        "Baseline comparison, ablation, sensitivity, or robustness metrics that can be traced to the planned figures and method code.",
    ]
    target = int(policy.get("target_tables") or TARGET_RESEARCH_PLAN_TABLES)
    while len(specs) < target:
        specs.append("Additional discipline-specific table required by the target journal or reviewer-risk profile.")
    return [f"- Table {index}: {text}" for index, text in enumerate(specs[:target], start=1)]


def _storyboard_markdown(blueprint: dict[str, Any]) -> list[str]:
    storyboard = blueprint.get("figure_storyboard") or {}
    lines = ["## Figure Storyboard", ""]
    lines.append(
        "Each planned figure is bound to a research question, expected finding, data requirement, method requirement, validation metric, and citation support. Downstream figure planning and code generation should follow this storyboard before falling back to generic discipline templates."
    )
    lines.append("")
    for index, item in enumerate(storyboard.get("figures") or [], start=1):
        lines.extend([
            f"- Fig. {index}: {item.get('proposed_title')} (`{item.get('figure_id')}`)",
            f"  Research question: {item.get('research_question')}",
            f"  Expected finding: {item.get('expected_finding')}",
            f"  Required data: {', '.join(item.get('required_data') or [])}",
            f"  Required method: {', '.join(item.get('required_method') or [])}",
            f"  Validation metric: {item.get('validation_metric')}",
            f"  Literature support: {', '.join(item.get('supporting_literature_keys') or [])}",
            "",
        ])
    lines.extend(["## Planned Core Tables", ""])
    for index, item in enumerate(storyboard.get("tables") or [], start=1):
        lines.append(f"- Table {index}: {item.get('proposed_title')} (`{item.get('table_id')}`)")
    lines.append("")
    return lines


def _method_plan_markdown(blueprint: dict[str, Any]) -> list[str]:
    lines = ["## Method Plan Contract", ""]
    lines.append(
        "The method plan below is generated inside the research-plan stage and should be consumed by method blueprinting, figure planning, and analysis-code generation."
    )
    lines.append("")
    for task in (blueprint.get("method_plan") or {}).get("method_tasks") or []:
        lines.extend([
            f"- {task.get('task_id')} for {task.get('figure_id')}: {task.get('method_family')}",
            f"  Required data: {', '.join(task.get('required_data') or [])}",
            f"  Validation metric: {task.get('validation_metric')}",
            "",
        ])
    return lines


def _load_research_data_context(project_path: Path) -> dict[str, Any]:
    context: dict[str, Any] = {"status": "not_available", "table_summaries": []}
    inventory_path = project_path / "data" / "data_inventory.json"
    feasibility_path = project_path / "data" / "data_feasibility_report.json"
    role_path = project_path / "data" / "data_role_coverage_report.json"
    if inventory_path.is_file():
        try:
            inventory = json.loads(inventory_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            inventory = {}
        context.update(
            {
                "status": "inventory_available",
                "file_count": int(inventory.get("file_count") or 0),
                "external_file_count": int(inventory.get("external_file_count") or 0),
                "tabular_file_count": int(inventory.get("tabular_file_count") or 0),
                "cross_table_row_total": int(inventory.get("total_rows") or 0),
            }
        )
        tables = []
        for item in inventory.get("files") or []:
            if not isinstance(item, dict) or item.get("row_count") is None:
                continue
            logical_name = str(item.get("path") or "").replace("\\", "/").rsplit("/", 1)[-1]
            tables.append(
                {
                    "logical_name": logical_name,
                    "row_count": int(item.get("row_count") or 0),
                    "column_count": int(item.get("column_count") or 0),
                    "missing_cell_ratio": item.get("missing_cell_ratio"),
                }
            )
        context["table_summaries"] = tables[:20]
    if feasibility_path.is_file():
        try:
            feasibility = json.loads(feasibility_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            feasibility = {}
        context["feasibility"] = {
            key: feasibility.get(key)
            for key in (
                "decision",
                "scientific_goal_supported",
                "supported_claim_level",
                "min_rows",
                "observed_rows",
                "blocking_issues",
                "recommended_actions",
            )
        }
    if role_path.is_file():
        try:
            coverage = json.loads(role_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            coverage = {}
        context["role_coverage"] = {
            "decision": coverage.get("decision"),
            "required_roles": coverage.get("required_roles") or [],
            "available_roles": coverage.get("available_roles") or [],
            "missing_roles": coverage.get("missing_roles") or [],
        }
    return context


_CN_PHRASES = {
    "reconciled_counts_label_provenance_and_zero_cross_split_source_overlap": "样本计数核对、标签来源审计及跨数据集目标零重叠",
    "held_out_macro_f1_balanced_accuracy_roc_auc_and_expected_calibration_error": "留出集macro-F1、平衡准确率、ROC-AUC及期望校准误差",
    "class_specific_precision_recall_f1_with_confidence_and_error_support": "含置信度与错误样本支持的类别级精确率、召回率和F1",
    "bootstrap_median_and_central_interval_with_effect_size_and_adjusted_distribution_test": "含效应量与多重检验校正的bootstrap中位数及中心区间",
    "uncertainty_aware_interval_overlap_with_population_comparability": "考虑不确定性与样本人群可比性的区间重叠",
    "stratified_metric_and_interval_stability_with_uncertainty": "含不确定性的分层指标与区间稳定性",
    "planned confirmatory or predictive claims are supportable by the current data gate": "当前数据门能够支撑计划中的确认性或预测性主张",
    "planned confirmatory claims are supportable by the current data gate": "当前数据门能够支撑计划中的确认性主张",
    "planned predictive claims are supportable by the current data gate": "当前数据门能够支撑计划中的预测性主张",
    "Test whether ImageNet-pretrained DINOv2 representations of Euclid Q1 VIS galaxy cutouts retain morphology-related information supported by DESI spectroscopy and independent catalog morphology after controlling redshift, luminosity, sample selection, class imbalance, spatial grouping, and image missingness; evaluate bounded use for classification, representation analysis, and anomaly candidate discovery.": "检验基于 ImageNet 预训练的 DINOv2 表示能否从 Euclid Q1 VIS 星系切图中保留形态学信息，并利用 DESI 光谱与独立形态目录进行验证；在控制红移、光度、样本选择、类别不平衡、空间分组和图像缺失后，评估其在分类、表示分析和异常候选发现中的有限适用性。",
    "Sample construction, image coverage, and missingness": "样本构建、图像覆盖与缺失机制",
    "Image-representation structure against independent targets and confounders": "图像表示与独立形态目标及混杂因素的关系",
    "Group-aware representation prediction versus transparent baselines": "分组感知验证下的表示预测与透明基线比较",
    "Incremental-value and confounder ablation": "增量信息价值与混杂因素消融",
    "Class-wise error, imbalance, and uncertainty structure": "类别级误差、不平衡与不确定性结构",
    "Anomaly candidates and image-quality interpretation boundary": "异常候选的稳定性与图像质量解释边界",
    "End-to-end temporal classification workflow": "端到端时序分类流程",
    "End-to-end classification workflow": "端到端分类流程",
    "Class support and modality completeness for the sample": "样本类别支持度与模态完整性",
    "Temporal and feature structure before model training": "模型训练前的时间与特征结构",
    "Feature structure before model training": "模型训练前的特征结构",
    "Baseline versus proposed-model performance": "基线模型与拟采用模型的性能比较",
    "Ablation of declared feature and method components": "已声明特征与方法组件的消融分析",
    "Error structure and uncertainty across confused classes": "易混淆类别的错误结构与不确定性",
    "End-to-end research workflow": "端到端研究流程",
    "Data support and quality-control overview": "数据支持与质量控制概览",
    "Primary feature distribution and observation support": "主要特征分布与观测支持",
    "Main empirical relationship or model response": "主要经验关系或模型响应",
    "Validation, robustness, or ablation summary": "验证、稳健性与消融汇总",
    "Final evidence synthesis and claim boundary": "最终证据综合与结论边界",
    "Dataset, method, validation, and citation-evidence summary": "数据集、方法、验证与引用证据汇总",
    "source_catalog": "源目录",
    "image_availability": "图像可用性记录",
    "valid_image_cohort": "有效图像样本队列",
    "missingness_reason": "缺失原因",
    "image_embedding": "图像表示向量",
    "independent_target": "独立科学目标",
    "confounder_variables": "混杂变量",
    "group_validation_split": "分组验证划分",
    "class_label": "类别标签",
    "catalog_baseline_features": "目录基线特征",
    "predicted_label": "预测类别",
    "prediction_score": "预测得分",
    "class_support": "类别样本支持度",
    "image_cutout": "科学图像切图",
    "quality_flags": "图像质量标记",
    "candidate_score": "候选异常得分",
    "data_inventory": "数据清单",
    "method_requirements": "方法需求",
    "validation_design": "验证设计",
    "data_summary": "数据汇总",
    "method_summary": "方法汇总",
    "citation_traceability": "引用可追溯性",
    "primary_observations": "主要观测数据",
    "declared_feature_groups": "已声明特征组",
    "modality_availability": "模态可用性",
    "features": "分析特征",
    "validation_split": "验证划分",
    "image_or_raster_data": "图像或栅格数据",
    "label_or_response": "标签或响应变量",
    "sample_group": "样本分组",
    "cohort_flow_audit": "样本队列流转审计",
    "missingness_analysis": "缺失机制分析",
    "representation_projection": "表示空间投影",
    "target_confounder_diagnostic": "目标与混杂因素诊断",
    "group_aware_validation": "分组感知验证",
    "transparent_baseline_comparison": "透明基线比较",
    "uncertainty_estimation": "不确定性估计",
    "feature_group_ablation": "特征组消融",
    "confounder_control": "混杂因素控制",
    "label_leakage_check": "标签泄漏检查",
    "confusion_or_error_analysis": "混淆与错误分析",
    "class_imbalance_analysis": "类别不平衡分析",
    "uncertainty_summary": "不确定性汇总",
    "anomaly_stability_analysis": "异常候选稳定性分析",
    "image_quality_review": "图像质量复核",
    "candidate_interpretation_boundary": "候选解释边界评估",
    "image_validity": "图像有效性记录",
    "embedding_membership": "嵌入样本归属",
    "selection_covariates": "选择相关协变量",
    "cohort_accounting_reconciliation": "样本队列计数核对",
    "selection_missingness_analysis": "选择与缺失机制分析",
    "reconciled_cohort_counts_and_missingness_effects": "核对后的样本数量与缺失效应",
    "continuous_colour_magnitude_observables": "连续颜色与星等观测量",
    "continuous_color_magnitude_observables": "连续颜色与星等观测量",
    "catalog_profile_morphology": "星表轮廓形态",
    "physical_state_proxy": "物理状态代理",
    "morphology_state_association": "形态与物理状态关联分析",
    "image_level_validation": "图像层复核",
    "association_effects_with_uncertainty": "含不确定性的关联效应",
    "continuous_physical_observables": "连续物理观测量",
    "absolute_magnitude": "绝对星等",
    "image_quality_flags": "图像质量标记",
    "group_id": "样本分组标识",
    "proxy_label_definition": "代理标签定义",
    "confounder_adjusted_association": "混杂因素调整后的关联分析",
    "stratified_bootstrap": "分层自助重采样",
    "label_definition_audit": "标签定义审计",
    "adjusted_effect_size_and_bootstrap_interval": "调整后效应量与自助重采样区间",
    "image_morphology_measurement": "图像形态测量",
    "apparent_magnitude": "视星等",
    "selection_function": "选择函数",
    "sample_support": "样本支持度",
    "stratified_population_analysis": "分层群体分析",
    "interaction_estimation": "交互效应估计",
    "selection_sensitivity_analysis": "选择效应敏感性分析",
    "within_stratum_trend_and_support_interval": "分层内部趋势与支持区间",
    "transition_population_analysis": "过渡群体分析",
    "image_catalog_discordance_analysis": "图像与星表不一致性分析",
    "uncertainty_resampling": "不确定性重采样",
    "group_difference_with_resampling_interval": "含重采样区间的群体差异",
    "neighbour_contamination": "邻近源污染",
    "background_quality": "背景质量",
    "rank_stability_and_quality_screen_pass_rate": "排序稳定性与质量筛查通过率",
    "cohort_flow_and_missingness": "样本流转与缺失机制图",
    "structure_state_multiview": "结构与状态多视图",
    "adjusted_effect_summary": "调整后效应汇总图",
    "stratified_population_trends": "分层群体趋势图",
    "transition_discordance_analysis": "过渡与不一致群体分析图",
    "candidate_stability_gallery": "候选稳定性画廊",
    "cohort flow audit": "样本队列流转审计",
    "missingness analysis": "缺失机制分析",
    "representation projection": "表示空间投影",
    "target confounder diagnostic": "目标与混杂因素诊断",
    "group aware validation": "分组感知验证",
    "transparent baseline comparison": "透明基线比较",
    "uncertainty estimation": "不确定性估计",
    "feature group ablation": "特征组消融",
    "confounder control": "混杂因素控制",
    "label leakage check": "标签泄漏检查",
    "confusion or error analysis": "混淆与错误分析",
    "class imbalance analysis": "类别不平衡分析",
    "uncertainty summary": "不确定性汇总",
    "anomaly stability analysis": "异常候选稳定性分析",
    "image quality review": "图像质量复核",
    "candidate interpretation boundary": "候选解释边界评估",
    "cohort_coverage": "样本队列覆盖率",
    "target_and_confounder_association": "目标及混杂因素关联强度",
    "group_held_out_metric": "分组留出性能指标",
    "incremental_metric_delta": "增量性能差值",
    "classwise_uncertainty": "类别级不确定性",
    "candidate_stability": "候选稳定性",
    "Time-aware Transformer": "时间感知 Transformer",
    "time_aware_transformer": "时间感知 Transformer",
    "current_observation_tokens": "当前观测 token",
    "spectral_features": "能谱特征",
    "multimodal_fusion": "多模态融合",
    "data_alignment": "数据对齐",
    "class_balance_check": "类别均衡检查",
    "missingness_check": "缺失情况检查",
    "feature_space_diagnostic": "特征空间诊断",
    "metric_evaluation": "指标评估",
    "ablation_study": "消融实验",
    "declared_component_comparison": "已声明组件比较",
    "source catalog": "源目录",
    "group-aware validation": "分组感知验证",
    "transparent baselines": "透明基线模型",
    "image representation": "图像表示",
    "representation analysis": "表示分析",
    "anomaly candidate discovery": "异常候选发现",
    "galaxy morphology": "星系形态",
    "galaxy evolution": "星系演化",
    "scientific image representation": "科学图像表示",
    "survey imaging": "巡天成像",
    "high-energy time-domain astronomy": "高能时域天文学",
    "X-ray transient": "X 射线暂现源",
    "light curves": "光变曲线",
    "light curve": "光变曲线",
    "machine learning": "机器学习",
    "astronomy": "天文学",
    "classification": "分类",
    "validation": "验证",
    "uncertainty": "不确定性",
    "multimodal": "多模态",
    "spectral": "光谱",
    "transformer": "Transformer",
    "survey": "巡天",
    "time": "时间信息",
    "event": "事件",
    "redshift": "红移",
    "label": "标签",
    "class": "类别",
    "baseline": "基线模型",
    "ablation": "消融实验",
    "long-term": "长期",
    "irregular": "不规则采样",
}


_CN_SENTENCES = {
    "Quantify the source, image-available, image-valid, and analysis cohorts together with every exclusion step.": "量化源样本、图像可用样本、图像有效样本和最终分析样本，并标出每一步排除的对象与原因。",
    "Compare image missingness rates and recorded reasons across the declared sample groups and relevant covariates.": "比较各预定样本组的图像缺失率和已记录原因，并检查缺失是否随相关协变量系统变化。",
    "Visualize the representation geometry as exploratory evidence while coloring points only by the independent scientific target.": "将表示空间几何结构作为探索性证据展示，并仅使用独立科学目标对样本着色。",
    "Quantify target association separately from redshift, luminosity, acquisition group, and other declared confounders.": "分别量化表示与科学目标、红移、光度、观测分组及其他预定混杂因素的关联。",
    "Report held-out performance across the declared groups and folds without allowing group leakage between training and evaluation.": "报告各预定分组和交叉验证折上的留出性能，并确保训练集与评估集之间不存在分组泄漏。",
    "Compare the representation-based model with transparent catalog-only and simple predictive baselines on identical cohorts and splits.": "在完全相同的样本队列和数据划分上，将表示模型与仅使用目录变量的透明基线及简单预测基线比较。",
    "Show fold- or group-level uncertainty intervals for every primary performance estimate.": "为每个主要性能估计给出验证折或样本组层面的不确定性区间。",
    "Measure the change in held-out performance when each declared feature group is removed or added on matched folds.": "在匹配的验证折上逐一移除或加入预定特征组，量化留出性能的变化。",
    "Compare image-representation gain before and after controlling the declared catalog and acquisition confounders.": "比较控制目录变量和观测条件混杂因素前后，图像表示带来的增量性能。",
    "Demonstrate that identifiers and label-defining variables cannot leak into the predictive feature set.": "证明对象标识符和用于定义标签的变量没有泄漏到预测特征中。",
    "Show class-wise confusion and error patterns using held-out predictions only.": "仅使用留出预测展示类别级混淆关系和错误模式。",
    "Report class support together with class-wise precision, recall, and performance sensitivity to imbalance handling.": "同时报告各类别样本量、精确率、召回率以及性能对不平衡处理方式的敏感性。",
    "Compare confidence or calibration evidence across classes and identify unreliable prediction regimes.": "比较不同类别的置信度或校准证据，并识别预测不可靠的样本区间。",
    "Measure candidate-rank stability across seeds, resampling, preprocessing choices, and reference cohorts.": "量化异常候选排序在不同随机种子、重采样、预处理选择和参照样本队列下的稳定性。",
    "Display candidate cutouts with image-quality diagnostics to separate scientific structure from artefacts.": "结合图像质量诊断展示候选切图，以区分潜在科学结构与成像伪影。",
    "Retain only stable candidates not explained by quality failures and mark them as requiring independent confirmation.": "仅保留无法由质量缺陷解释的稳定候选，并明确标记其仍需独立确认。",
    "Which source, image-available, image-valid, and analysis cohorts support the proposed representation study, and how do label provenance and missingness constrain them?": "哪些源样本、图像可用样本、图像有效样本和最终分析样本能够支撑本研究，标签来源与缺失机制又会如何限制这些样本队列？",
    "The sample flow should define distinct source, image-available, image-valid, and analysis cohorts before any representation claim is made.": "在讨论图像表示能力之前，应先明确区分源样本、图像可用样本、图像有效样本和最终分析样本，并给出各阶段损失原因。",
    "Does the image representation contain structure associated with an independently defined scientific target rather than only identifiers or preprocessing artifacts?": "图像表示中是否存在与独立定义的科学目标相关的结构，而不是只反映对象标识、预处理步骤或其他伪信号？",
    "Representation structure should be related to an independent target while remaining explicitly separated from exploratory visualization and label-defining variables.": "表示空间应与独立科学目标建立可检验关联，同时必须将探索性可视化与用于定义标签的变量严格区分。",
    "Does representation-based prediction generalize under group-aware validation and class imbalance?": "在考虑类别不平衡并采用分组感知验证后，基于图像表示的预测能否推广到未参与训练的样本组？",
    "Held-out performance and uncertainty should be compared with transparent baselines on the same cohort, sample unit, and split.": "拟采用方法与透明基线必须使用相同样本队列、样本单位和数据划分进行比较，并同时报告留出性能与不确定性。",
    "What information does the image representation add beyond catalog, selection, or other confounding variables?": "排除目录变量、样本选择和其他混杂因素后，图像表示还能提供多少独立的形态信息？",
    "Ablation should distinguish incremental visual information from redshift, brightness, color, acquisition, or label leakage.": "消融分析应区分真正新增的视觉信息与红移、亮度、颜色、观测条件或标签泄漏造成的表观增益。",
    "Which classes and sample regimes remain uncertain after accounting for imbalance and calibration?": "在处理类别不平衡并检查概率校准后，哪些类别和样本区间仍然具有较高不确定性？",
    "Class-wise errors, support, calibration, and uncertainty should identify where predictive interpretation is reliable and where it must be limited.": "类别级误差、样本支持度、校准和不确定性应共同界定预测在哪些条件下可信，在哪些条件下必须收紧解释。",
    "Are high-scoring anomaly candidates stable under resampling and separable from image-quality failures?": "高异常得分候选能否在重采样和分析扰动下保持稳定，并与图像质量缺陷清楚区分？",
    "Only candidates stable across the declared perturbations and not explained by image-quality defects should be retained for independent scientific follow-up.": "只有在预先声明的扰动下保持稳定且不能由图像质量缺陷解释的候选，才应进入后续独立科学核验。",
    "Do the available temporal, spectral, or tabular features contain separable structure before model training?": "在模型训练之前，时间序列、光谱或表格特征中是否已经存在可分辨的科学结构？",
    "Does the proposed method improve over transparent baselines under a reproducible validation design?": "在可复现的验证设计下，拟采用方法相对于透明基线是否具有稳定且可解释的改进？",
    "Which data modality or method component contributes most to the result?": "哪一类数据模态或方法组件对结果贡献最大？",
    "Which classes, samples, or regimes remain uncertain after the proposed method is applied?": "应用拟采用方法后，哪些类别、样本或观测区间仍然不确定？",
    "The available samples, labels, and modalities should define which classification claims are scientifically supportable.": "样本规模、标签质量和模态完整性共同决定本文能够支撑何种强度的分类结论。",
    "Feature-space diagnostics should show whether the data contain model-ready signal rather than only filename-level evidence.": "特征空间诊断应证明数据本身包含可供模型学习的信号，而不是依赖文件名或元信息形成表面证据。",
    "The main model result should be judged by baseline comparison, ablation, and verified local metrics.": "主模型结果应同时接受基线比较、消融实验和本地可复验指标的约束。",
    "Ablation should show which declared feature groups or method components drive the result.": "消融实验应说明哪些已声明的特征组或方法组件真正驱动了结果。",
    "Error analysis should constrain the final claim boundary and identify data or method limitations.": "错误分析应反过来约束最终结论，并指出仍然存在的数据或方法限制。",
    "The data overview should establish the observation support and the limits of downstream claims.": "数据概览应明确可用观测证据，并界定后续结论能够达到的强度。",
    "What primary relationship or pattern should be tested first?": "首先需要检验的核心关系或经验模式是什么？",
    "The first empirical result should reveal whether the core idea is supported by visible data structure.": "第一项经验结果应判断核心想法是否得到可观测数据结构的支持。",
    "Which baseline or alternative method is necessary for a credible comparison?": "为了形成可信比较，需要纳入哪些基线或替代方法？",
    "Method comparison should prevent the manuscript from relying on an unsupported proposed-method narrative.": "方法比较应防止论文只依赖未经证据支持的拟采用方法叙事。",
    "How robust is the main result to validation, sensitivity, or quality-control choices?": "主要结果对验证方式、敏感性设定和质量控制选择有多稳健？",
    "Robustness evidence should determine whether the result can be written as a strong claim or a limited exploratory finding.": "稳健性证据应决定结果能够写成较强结论，还是只能作为有限的探索性发现。",
    "What final evidence synthesis should be shown before writing Results and Discussion?": "在撰写结果与讨论之前，需要展示怎样的最终证据综合？",
    "The synthesis figure should connect verified empirical outputs to the final claim boundary.": "综合图应把经过验证的经验输出与最终结论边界连接起来。",
    "How do the main environmental or remote-sensing variables vary across the study units?": "主要环境变量或遥感变量在不同研究单元之间如何变化？",
    "Distribution and quality diagnostics should identify usable gradients and outlier-sensitive variables.": "分布与质量诊断应识别可用梯度以及对异常值敏感的变量。",
    "Which driver has the clearest empirical relationship with the target response?": "哪个驱动因素与目标响应具有最清晰的经验关系？",
    "Driver-response evidence should be supported by effect size, uncertainty, and validation rather than visual trend alone.": "驱动因素与响应之间的关系必须由效应量、不确定性和验证结果共同支持，不能只依赖视觉趋势。",
    "Does the model remain stable under spatial, temporal, or group-aware validation?": "模型在空间、时间或分组感知验证下是否保持稳定？",
    "Validation diagnostics should show whether the result generalizes beyond random split artifacts.": "验证诊断应判断结果能否超越随机划分造成的假象并实现推广。",
    "What final zoning, suitability, or response pattern is scientifically defensible?": "最终能够得到科学辩护的分区、适宜性或响应格局是什么？",
    "The synthesis result should connect the validated model output to a bounded geographical interpretation.": "综合结果应把经过验证的模型输出与边界明确的地理解释联系起来。",
}


def _cn_term(value: Any) -> str:
    text = str(value or "").strip()
    for old, new in sorted(_CN_PHRASES.items(), key=lambda item: len(item[0]), reverse=True):
        text = re.sub(re.escape(old), new, text, flags=re.IGNORECASE)
    text = text.replace("_", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _cn_sentence(value: Any) -> str:
    source = str(value or "").strip()
    if source in _CN_SENTENCES:
        return _CN_SENTENCES[source]
    if source.startswith("What data coverage and label support are available for "):
        subject = source.removeprefix("What data coverage and label support are available for ").rstrip("?")
        return f"围绕“{_cn_term(subject)}”，现有数据能够提供怎样的覆盖范围、标签依据和模态完整性？"
    if source.startswith("What empirical data support the proposed study: "):
        subject = source.removeprefix("What empirical data support the proposed study: ").rstrip("?")
        return f"围绕“{_cn_term(subject)}”，哪些经验数据能够直接支撑这项研究？"
    if source.startswith("What spatial, temporal, and variable coverage supports "):
        subject = source.removeprefix("What spatial, temporal, and variable coverage supports ").rstrip("?")
        return f"围绕“{_cn_term(subject)}”，现有数据能够提供怎样的空间、时间和变量覆盖？"
    if source.startswith("Show the evidence produced by ") and source.endswith(" for the contracted research question."):
        method = source.removeprefix("Show the evidence produced by ").removesuffix(" for the contracted research question.")
        return f"展示由{_cn_term(method)}产生的证据，并说明该证据如何回答已确认的研究问题。"
    if source.startswith("Present the contracted ") and source.endswith(" evidence."):
        role = source.removeprefix("Present the contracted ").removesuffix(" evidence.")
        return f"展示研究合同中规定的{_cn_term(role)}证据。"
    translated = _cn_term(source)
    translated = translated.replace("?", "？")
    if translated and translated[-1] not in "。！？":
        translated += "。"
    return translated


def _cn_join(values: list[Any]) -> str:
    return "、".join(_cn_term(value) for value in values if str(value or "").strip())


def _localized_cn(value: dict[str, Any], field: str) -> str:
    localized = str(value.get(f"{field}_zh_cn") or "").strip()
    return localized or _cn_sentence(value.get(field))


def _render_research_plan_cn(project_meta: dict[str, Any], blueprint: dict[str, Any]) -> str:
    synthesis = blueprint.get("literature_synthesis") or {}
    method_terms = _cn_join(synthesis.get("key_methods") or [])
    data_terms = _cn_join(synthesis.get("key_data_modalities") or [])
    if method_terms or data_terms:
        synthesis_summary = (
            f"当前文献主要为本研究提供了两类支撑：方法侧集中在{method_terms or '相关模型与验证流程'}，"
            f"数据侧集中在{data_terms or '观测样本、特征构建和标签支撑'}。这些文献的作用不是简单证明本研究一定成立，"
            "而是帮助确定哪些数据输入、模型比较和验证环节必须在后续流程中被明确实现。"
        )
    else:
        synthesis_summary = "当前文献综合结果仍需在 references 阶段继续补充；在正式写作前，应优先检查文献综述索引中的每篇文献是否确实服务于本研究。"
    evidence_keys = []
    for item in blueprint.get("claim_evidence_links") or []:
        key = str(item.get("citation_key") or "").strip()
        if key and key not in evidence_keys:
            evidence_keys.append(key)
    if evidence_keys:
        synthesis_summary += " 当前研究主张已与以下文献证据建立初步绑定：" + "、".join(f"`{key}`" for key in evidence_keys[:12]) + "。"
    objective = blueprint.get("research_objective") or project_meta.get("research_objective") or {}
    working_title_cn = str(objective.get("working_title_zh_cn") or "").strip()
    title_text = working_title_cn or _cn_term(
        objective.get("working_title") or project_meta.get("title") or project_meta.get("idea")
    ).rstrip("。！？")
    scientific_objective_cn = str(objective.get("scientific_objective_zh_cn") or "").strip()
    if not scientific_objective_cn:
        scientific_objective_cn = _cn_sentence(
            objective.get("scientific_objective") or project_meta.get("idea")
        )
    lines = [
        "# 文献驱动研究方案",
        "",
        "## 项目背景",
        "",
        f"本研究暂定题目为：{title_text}。",
        "",
        f"核心科学目标是：{scientific_objective_cn.rstrip('。！？')}。",
        "",
        f"研究领域可概括为：{_cn_term(project_meta.get('field'))}。",
        "",
        f"目标期刊为：{project_meta.get('target_journal') or '尚未指定'}。",
        "",
    ]
    if objective:
        method_hypothesis = str(objective.get("methodological_hypothesis_zh_cn") or "").strip()
        if not method_hypothesis:
            method_hypothesis = _cn_sentence(objective.get("methodological_hypothesis"))
        data_scope = objective.get("data_scope_zh_cn") or objective.get("data_scope") or []
        secondary = objective.get("secondary_analyses_zh_cn") or objective.get("secondary_analyses") or []
        boundary = str(objective.get("claim_boundary_zh_cn") or "").strip()
        if not boundary:
            boundary = _cn_sentence(objective.get("claim_boundary"))
        lines.extend([
            "## 研究目标合同",
            "",
            f"- 科学目标：{scientific_objective_cn}",
            f"- 方法假设：{method_hypothesis}",
            f"- 数据范围：{_cn_join(data_scope)}。",
            f"- 次级分析：{_cn_join(secondary) or '无'}。",
            f"- 结论边界：{boundary}",
            "",
            "本研究以天体物理问题为主线。DINOv2、降维、分类器和异常检测等只在能够回答上述科学问题时作为分析工具使用，不能替代科学目标本身。",
            "",
        ])
    lines.extend([
        "## 文献综合",
        "",
        synthesis_summary,
        "",
        "从当前文献证据看，后续写作需要把研究意义落在三个层面：已有工作如何处理类似数据，已有方法在哪些场景下有效，以及本研究的数据与方法是否足以支撑更进一步的结论。引言和讨论应围绕这些证据展开，避免只给出笼统背景。",
        "",
        "## 数据盘点与可行性边界",
        "",
    ])
    data_context = blueprint.get("data_feasibility_context") or {}
    if data_context.get("status") == "inventory_available":
        lines.extend([
            f"当前数据盘点共识别 {data_context.get('file_count', 0)} 个文件，其中 {data_context.get('external_file_count', 0)} 个通过只读外部数据合同接入；可读表格共 {data_context.get('tabular_file_count', 0)} 个。",
            "",
            f"各表行数累计为 {data_context.get('cross_table_row_total', 0)}，该数字只是跨表盘点总量，不能作为独立星系样本数。后续所有样本量必须绑定到具体表、样本单位和筛选阶段。",
            "",
        ])
        for table in data_context.get("table_summaries") or []:
            lines.append(
                f"- `{table.get('logical_name')}`：{table.get('row_count')} 行、{table.get('column_count')} 列，单元格缺失比例为 {float(table.get('missing_cell_ratio') or 0):.2%}。"
            )
        lines.append("")
    else:
        lines.extend(["当前尚无可读取的数据盘点；在确认蓝图前必须完成数据清单和样本单位核验。", ""])
    feasibility = data_context.get("feasibility") or {}
    if feasibility:
        level = str(feasibility.get("supported_claim_level") or "尚未确定")
        level_cn = "仅支持探索性或先导性结论" if "exploratory" in level.lower() or "pilot" in level.lower() else _cn_term(level)
        decision = "有条件通过" if feasibility.get("decision") == "conditional_pass" else _cn_term(feasibility.get("decision"))
        lines.extend([
            f"数据可行性结论为“{decision}”，当前证据边界为“{level_cn}”。这意味着研究可以继续设计，但不能在获得更强验证前写成确认性结论。",
            "",
        ])
    coverage = data_context.get("role_coverage") or {}
    if coverage:
        lines.extend([
            f"图表合同要求的数据角色包括：{_cn_join(coverage.get('required_roles') or [])}。",
            f"当前未覆盖的数据角色：{_cn_join(coverage.get('missing_roles') or []) or '无'}。",
            "",
        ])
    lines.extend([
        "## 研究问题与预期发现",
        "",
    ])
    for claim in blueprint.get("research_claims") or []:
        lines.extend([
            f"- {claim.get('claim_id')}：{_localized_cn(claim, 'research_question')}",
            f"  预期发现：{_localized_cn(claim, 'expected_finding')}",
            "",
        ])
    if objective:
        constraint_text = (
            "后续数据阶段必须按照目标合同逐级核对样本流转、代理标签来源、选择效应、图像质量和各物理观测量的来源。"
            "方法阶段只能选择能够估计形态与物理状态关系、控制混杂因素、报告不确定性并完成图像层复核的分析工具。"
            "若必要数据或方法无法补齐，应在人工检查点收紧对应主张，不能保留原强度结论或生成相似替代图。"
        )
    else:
        constraint_text = (
            "后续数据阶段应优先确认样本覆盖、标签来源、模态缺失、时间采样和质量控制记录。"
            "方法阶段则必须围绕这些数据条件构建，而不是脱离数据空谈模型。"
            "若某一类数据无法获得，相应图表和结论需要降级，而不是继续保留强结论。"
        )
    lines.extend(["## 数据与方法约束", "", constraint_text, "", "## 图表故事板", ""])
    for index, item in enumerate((blueprint.get("figure_storyboard") or {}).get("figures") or [], start=1):
        figure_title = str(item.get("proposed_title_zh_cn") or "").strip() or _cn_term(item.get("proposed_title"))
        lines.extend([
            f"- 图{index}：{figure_title}",
            f"  对应主张：`{item.get('claim_id')}`",
            f"  研究问题：{_localized_cn(item, 'research_question')}",
            f"  预期发现：{_localized_cn(item, 'expected_finding')}",
            f"  数据需求：{_cn_join(item.get('required_data') or [])}",
            f"  方法需求：{_cn_join(item.get('required_method') or [])}",
            f"  验证指标：{_cn_term(item.get('validation_metric'))}",
        ])
        for panel in item.get("panels") or item.get("panel_contract") or []:
            lines.append(
                f"  子图（{panel.get('label')}）：{_localized_cn(panel, 'expected_content')}"
            )
        lines.append("")
    lines.extend(["## 核心表格", ""])
    for index, item in enumerate((blueprint.get("figure_storyboard") or {}).get("tables") or [], start=1):
        lines.extend([
            f"- 表{index}：{_cn_term(item.get('proposed_title'))}",
            f"  数据需求：{_cn_join(item.get('required_data') or [])}",
            f"  方法需求：{_cn_join(item.get('required_method') or [])}",
            "",
        ])
    lines.extend(["## 方法计划", ""])
    for index, task in enumerate((blueprint.get("method_plan") or {}).get("method_tasks") or [], start=1):
        lines.extend([
            f"- 任务{index}：该任务服务于 `{task.get('figure_id')}`，核心方法为{_cn_term(task.get('method_family'))}。",
            f"  需要输入的数据包括：{_cn_join(task.get('required_data') or [])}；验证指标为：{_cn_term(task.get('validation_metric'))}。",
        ])
    lines.extend([
        "",
        "## 风险与人工确认",
        "",
        "在进入关键图表代码生成前，需要人工确认三件事：第一，当前文献集合是否足够覆盖背景、数据和方法；第二，现有数据与可行性结论是否能满足图表故事板；第三，计划中的方法能否真实生成各主图及其子图，而不是只生成流程图、占位图或相似替代图。",
        "",
        "人工确认后的研究蓝图与可行性快照是关键图表的唯一科学合同。执行阶段只能修复依赖、路径、性能和代码错误；若需要改变研究主张、样本队列、数据角色、方法、统计检验、主图或子图，必须重新打开研究蓝图，由用户纠错并确认新版本后才能继续。",
        "",
        "## 文献笔记索引",
        "",
        "[打开完整文献综述索引](../references/literature_summaries/index.html)",
        "",
    ])
    return "\n".join(lines)


def _assert_cn_plan_quality(text: str) -> None:
    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    ascii_letters = len(re.findall(r"[A-Za-z]", text))
    if chinese_chars < 300 or chinese_chars <= ascii_letters * 0.30:
        raise ResearchPlanQualityError("research_plan.zh-CN.md is not sufficiently localized into fluent Chinese.")
    if "Research question:" in text or "Expected finding:" in text or "Required data:" in text or "Required method:" in text:
        raise ResearchPlanQualityError("research_plan.zh-CN.md still contains untranslated English structural labels.")
    if ".?" in text or "。?" in text:
        raise ResearchPlanQualityError("research_plan.zh-CN.md contains malformed mixed-language punctuation.")
    for line in text.splitlines():
        clean = re.sub(r"https?://\S+|`[^`]+`", "", line)
        for segment in re.split(r"[\u4e00-\u9fff，。；：、（）“”]+", clean):
            if len(re.findall(r"[A-Za-z][A-Za-z0-9-]*", segment)) >= 12:
                preview = re.sub(r"\s+", " ", segment).strip()[:160]
                raise ResearchPlanQualityError(
                    f"research_plan.zh-CN.md contains a long untranslated English passage: {preview}"
                )


def _build_research_questions(project_meta: dict[str, Any], citation_rows: list[dict[str, str]]) -> list[str]:
    idea = project_meta.get("idea", "the proposed study")
    has_gap = any((row.get("claim") or "") == "current gap" for row in citation_rows)
    questions = [
        f"RQ1: How can {idea} be formulated as a reproducible empirical study grounded in the retrieved literature?",
        "RQ2: Which data sources and preprocessing steps are necessary to test the proposed research gap without relying on unsupported assumptions?",
        "RQ3: How does the proposed method compare with baseline or literature-derived alternatives under a transparent validation protocol?",
    ]
    if has_gap:
        questions.append("RQ4: Does the proposed design directly address the literature-supported gap identified in the citation evidence table?")
    return questions


def render_research_questions(project_meta: dict[str, Any], citation_rows: list[dict[str, str]]) -> str:
    lines = ["# Research Questions", ""]
    for question in _build_research_questions(project_meta, citation_rows):
        lines.extend([question, ""])
    return "\n".join(lines)


def render_research_plan(
    project_meta: dict[str, Any],
    literature_items: list[dict[str, Any]],
    citation_rows: list[dict[str, str]],
    literature_notes: str,
    anchor_papers: list[dict[str, Any]] | None = None,
    discipline_profile: dict[str, Any] | None = None,
    blueprint: dict[str, Any] | None = None,
) -> str:
    grouped = _evidence_by_claim(citation_rows)
    top_items = _top_items(literature_items)
    objective = (blueprint or {}).get("research_objective") or project_meta.get("research_objective") or {}
    objective_questions = [
        str(item.get("research_question") or "").strip()
        for item in objective.get("primary_scientific_questions") or []
        if isinstance(item, dict) and str(item.get("research_question") or "").strip()
    ] if isinstance(objective, dict) else []
    questions = objective_questions or _build_research_questions(project_meta, citation_rows)
    evidence_sentences = [_format_evidence_sentence(row) for row in citation_rows[:8]]
    output_policy = _research_plan_output_policy(discipline_profile)

    lines = [
        "# Literature-Informed Research Plan",
        "",
        "## Project Context",
        "",
        f"Working title: {project_meta.get('title') or project_meta.get('idea')}",
        "",
        f"Research idea: {project_meta.get('idea')}",
        "",
        f"Field or aim: {project_meta.get('field')}",
        "",
        f"Target journal: {project_meta.get('target_journal')}",
        "",
    ]
    if objective:
        lines.extend([
            "## Science-First Objective Contract",
            "",
            f"Scientific objective: {objective.get('scientific_objective')}",
            "",
            f"Methodological hypothesis: {objective.get('methodological_hypothesis')}",
            "",
            "Data scope:",
            *[f"- {item}" for item in objective.get("data_scope") or []],
            "",
            "Secondary analyses:",
            *([f"- {item}" for item in objective.get("secondary_analyses") or []] or ["- None declared."]),
            "",
            f"Claim boundary: {objective.get('claim_boundary')}",
            "",
            "Named models and algorithms remain methodological tools unless the scientific objective explicitly defines a method-comparison study.",
            "",
        ])
    lines.extend([
        "## Literature Basis",
        "",
        f"This plan is based on {len(literature_items)} retrieved literature records and {len(citation_rows)} citation-evidence rows. It should be revised whenever the references stage changes.",
        "",
    ])

    for item in top_items:
        authors = ", ".join(item.get("authors") or ["Unknown author"])
        lines.append(f"- `{item.get('bibtex_key')}`: {item.get('title')} ({authors}, {item.get('year')}).")

    lines.extend(["", "## Evidence-Supported Gap", ""])
    gap_rows = grouped.get("current gap") or citation_rows[:2]
    for row in gap_rows[:4]:
        lines.append(f"- {_format_evidence_sentence(row)}")
    lines.extend([
        "",
        "The formal research gap should therefore be written as a literature-supported problem rather than as a free-form AI assumption. The first draft should focus on the gap that can be traced to the strongest citation evidence above.",
        "",
        "## Target-Journal Anchor Literature",
        "",
    ])
    for item in (anchor_papers or [])[:5]:
        lines.append(
            f"- `{item.get('citation_key')}` should be used as a structural reference for the target journal because it has anchor score {item.get('anchor_score')} and study similarity {item.get('study_similarity_score')}. The draft may follow its manuscript logic at a high level, but must not copy wording, claims, figures, or unsupported assumptions."
        )
    if not anchor_papers:
        lines.append("- No target-journal anchor paper was identified from the current literature set.")
    lines.extend([
        "",
        "## Research Questions",
        "",
    ])
    for question in questions:
        lines.append(f"- {question}")

    lines.extend([
        "",
        "## Methodological Hypothesis",
        "",
        f"- {objective.get('methodological_hypothesis') if objective else 'The proposed methods should be evaluated only as tools for answering the declared scientific questions under a transparent validation protocol.'}",
        "",
        "## Data Requirements",
        "",
        _infer_data_requirements(project_meta, citation_rows),
        "",
        "## Method Route",
        "",
        _infer_method_route(project_meta, citation_rows),
        "",
        "## Expected Figures and Tables",
        "",
        f"The research plan must reserve at least {output_policy['minimum_figures']} main figures and at least {output_policy['minimum_tables']} core table before the downstream Methods and Results stages. The current discipline policy is `{output_policy['discipline']}` and targets {output_policy['target_figures']} main figures.",
        "",
        "",
    ])
    if blueprint:
        lines.extend(_storyboard_markdown(blueprint))
        lines.extend(_method_plan_markdown(blueprint))
    else:
        lines.extend(_expected_figure_lines(output_policy))
        lines.extend(_expected_table_lines(output_policy))
        lines.append("")
    lines.extend([
        "## Expected Contribution",
        "",
        "The expected contribution is a traceable research design that connects the user-provided idea to explicit literature evidence, reproducible data construction, and a validation strategy that can be checked before manuscript writing.",
        "",
        "## Risks and User Confirmation",
        "",
        "- Confirm whether the available local data are sufficient for the proposed validation design.",
        "- Confirm whether the retrieved literature set is broad enough for the target journal before writing the Introduction.",
        "- Confirm whether the method route can be implemented and run before generating the Methods section.",
        "",
        "## Citation Evidence Used",
        "",
    ])
    for sentence in evidence_sentences:
        lines.append(f"- {sentence}")
    lines.extend([
        "",
        "## Literature Notes Snapshot",
        "",
        "The full literature notes are maintained as a separate HTML index so the research plan remains readable and does not re-render nested Markdown headings from the references stage.",
        "",
        "[Open the full literature summaries](../references/literature_summaries/index.html)",
        "",
    ])
    return "\n".join(lines)


def _set_research_plan_manifest(project_path: Path) -> None:
    manifest_path = project_path / "research_plan" / "stage_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["input_files"] = RESEARCH_PLAN_INPUTS
    manifest["output_files"] = RESEARCH_PLAN_OUTPUTS
    _write_json(manifest_path, manifest)


def generate_research_plan(project: str | Path, *, allow_high_similarity: bool = False) -> dict[str, Any]:
    """Generate a formal research plan from retrieved literature and citation evidence."""
    state = load_project(project)
    from .research_plan_confirmation import confirmation_state

    confirmation = confirmation_state(state.path)
    if confirmation.get("required") and confirmation.get("current"):
        raise ResearchPlanQualityError(
            "The research blueprint is already human-confirmed. Run reopen-research-plan before changing its scientific contract."
        )
    try:
        validate_journal_profile_for_writing(state.path)
    except JournalProfileError as exc:
        raise MissingReferencesError(str(exc)) from exc
    literature_items, citation_rows, literature_notes = _require_reference_inputs(state.path)
    research_plan_dir = state.path / "research_plan"
    research_plan_dir.mkdir(parents=True, exist_ok=True)
    anchor_papers, novelty_report = analyze_target_journal_literature(state.path, state.metadata, literature_items)
    _write_json(research_plan_dir / "target_journal_anchor_papers.json", {"anchor_papers": anchor_papers})
    _write_json(research_plan_dir / "novelty_overlap_report.json", novelty_report)
    _write_novelty_report_md(research_plan_dir / "novelty_overlap_report.md", novelty_report, anchor_papers)
    if novelty_report.get("high_similarity_found") and not allow_high_similarity:
        raise NoveltyOverlapError(
            "A highly similar paper was found. Review research_plan/novelty_overlap_report.md and rerun generate-plan with --allow-high-similarity only if the user chooses to continue.",
            research_plan_dir / "novelty_overlap_report.md",
        )

    discipline_profile = infer_discipline_profile(state.path)
    data_context = _load_research_data_context(state.path)
    try:
        blueprint = build_research_blueprint(
            project_meta=state.metadata,
            literature_items=literature_items,
            citation_rows=citation_rows,
            discipline_profile=discipline_profile,
            anchor_papers=anchor_papers,
            data_context=data_context,
        )
    except ResearchBlueprintQualityError as exc:
        raise ResearchPlanQualityError(str(exc)) from exc
    _write_json(research_plan_dir / "research_blueprint.json", blueprint)
    claim_contract = build_claim_contract_from_blueprint(blueprint)
    _write_json(research_plan_dir / "claim_contract.json", claim_contract)
    _write_json(research_plan_dir / "figure_storyboard.json", blueprint["figure_storyboard"])
    _write_json(research_plan_dir / "method_plan.json", blueprint["method_plan"])
    from .statistical_validation import bind_statistical_validations_to_storyboard, build_statistical_validation_contract, statistical_plan_summary

    build_statistical_validation_contract(state.path, blueprint=blueprint)
    bind_statistical_validations_to_storyboard(state.path)
    blueprint = json.loads((research_plan_dir / "research_blueprint.json").read_text(encoding="utf-8"))
    for obsolete_name in ["research_plan.html", "research_questions.md", "research_questions.html"]:
        obsolete_path = research_plan_dir / obsolete_name
        if obsolete_path.exists():
            obsolete_path.unlink()
    plan_text = render_research_plan(
        state.metadata,
        literature_items,
        citation_rows,
        literature_notes,
        anchor_papers,
        discipline_profile,
        blueprint,
    )
    plan_text_cn = _render_research_plan_cn(state.metadata, blueprint)
    _assert_cn_plan_quality(plan_text_cn)
    plan_text = plan_text.rstrip() + "\n\n" + statistical_plan_summary(state.path, language="en")
    plan_text_cn = plan_text_cn.rstrip() + "\n\n" + statistical_plan_summary(state.path, language="zh-CN")
    (research_plan_dir / "research_plan.md").write_text(plan_text, encoding="utf-8")
    (research_plan_dir / "research_plan.zh-CN.md").write_text(plan_text_cn, encoding="utf-8")

    # The plan is the authoritative hand-off from literature interpretation to
    # data/method execution. Resolve a final composite discipline contract here
    # so downstream stages cannot silently select unrelated generic plugins.
    from .research_capabilities import resolve_research_capabilities

    capability_contract = resolve_research_capabilities(state.path)
    from .statistical_validation import assess_review_rule_coverage
    from .research_plan_confirmation import mark_research_plan_confirmation_required

    assess_review_rule_coverage(state.path)
    mark_research_plan_confirmation_required(state.path)

    update_stage_status(state.path, "research_plan", "draft")
    _set_research_plan_manifest(state.path)
    cited_keys = {str(row.get("citation_key") or "").strip() for row in citation_rows if row.get("citation_key")}
    return {
        "status": "written",
        "project_path": str(state.path),
        "research_plan": str(research_plan_dir / "research_plan.md"),
        "research_plan_zh_cn": str(research_plan_dir / "research_plan.zh-CN.md"),
        "citation_count": len(cited_keys),
        "literature_count": len(literature_items),
        "anchor_paper_count": len(anchor_papers),
        "highest_similarity_score": novelty_report.get("highest_similarity_score"),
        "discipline_contract": capability_contract["discipline_contract"],
        "research_capability_contract": capability_contract["research_capability_contract"],
        "outputs": RESEARCH_PLAN_OUTPUTS,
    }
