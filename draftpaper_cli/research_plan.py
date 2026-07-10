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


def _cn_term(value: Any) -> str:
    text = str(value or "")
    replacements = [
        ("Time-aware Transformer", "时间感知 Transformer"),
        ("time-aware", "时间感知"),
        ("Transformer", "Transformer"),
        ("EP WXT", "EP/WXT"),
        ("flaring-source", "耀发源"),
        ("flaring sources", "耀发源"),
        ("light curves", "光变曲线"),
        ("light curve", "光变曲线"),
        ("current observation tokens", "当前观测 token"),
        ("spectral features", "能谱特征"),
        ("classification", "分类"),
        ("machine learning", "机器学习"),
        ("long-term", "长期"),
        ("using", "结合"),
        (" for ", " 用于 "),
        (" and ", " 和 "),
        (" of ", " 的 "),
        ("high-energy time-domain astronomy", "高能时域天文学"),
        ("X-ray transient", "X 射线暂现源"),
        ("irregular", "不规则采样"),
        ("multimodal", "多模态"),
        ("baseline", "基线模型"),
        ("ablation", "消融实验"),
        ("validation", "验证"),
        ("uncertainty", "不确定性"),
        ("source catalog", "源表"),
        ("source_catalog", "源表"),
        ("class_label", "类别标签"),
        ("modality_availability", "模态可用性"),
        ("current_observation_tokens", "当前观测 token"),
        ("spectral_features", "能谱特征"),
        ("validation_split", "验证划分"),
        ("prediction_score", "预测置信度"),
        ("predicted_label", "预测标签"),
        ("data_alignment", "数据对齐"),
        ("time_aware_transformer", "时间感知 Transformer"),
        ("multimodal_fusion", "多模态融合"),
        ("class_balance_check", "类别均衡检查"),
        ("missingness_check", "缺失情况检查"),
        ("feature_space_diagnostic", "特征空间诊断"),
        ("metric_evaluation", "指标评估"),
        ("ablation_study", "消融实验"),
        ("confusion_or_error_analysis", "混淆与错误分析"),
        ("uncertainty_summary", "不确定性汇总"),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def _cn_sentence(value: Any) -> str:
    text = _cn_term(value)
    templates = [
        (
            "What data coverage and label support are available for ",
            "需要首先确认该研究具备怎样的数据覆盖、标签支撑和模态完整性，研究对象是",
        ),
        (
            "Do the available temporal, spectral, or tabular features contain separable structure before model training?",
            "在模型训练之前，需要判断时间序列、能谱或表格特征中是否已经存在可分辨的类别结构。",
        ),
        (
            "Does the proposed method improve over transparent baselines under a reproducible validation design?",
            "需要在可复现的验证设计下比较拟采用方法与透明基线模型的差异，确认性能提升是否真实存在。",
        ),
        (
            "Which data modality or method component contributes most to the result?",
            "需要通过消融实验判断光变曲线、当前观测、能谱特征或融合模块中哪一部分真正贡献了结果。",
        ),
        (
            "Which classes, samples, or regimes remain uncertain after the proposed method is applied?",
            "需要识别模型应用后仍然不稳定的类别、样本和观测情形，并据此限定论文结论边界。",
        ),
        (
            "The available samples, labels, and modalities should define which classification claims are scientifically supportable.",
            "样本数量、标签质量和模态完整性将决定本文能够支撑到何种强度的分类结论。",
        ),
        (
            "Feature-space diagnostics should show whether the data contain model-ready signal rather than only filename-level evidence.",
            "特征空间诊断应证明数据本身含有可供模型学习的信号，而不是只依赖文件名或元信息形成表面证据。",
        ),
        (
            "The main model result should be judged by baseline comparison, ablation, and verified local metrics.",
            "主模型结果应同时接受基线比较、消融实验和本地可复验指标的约束。",
        ),
        (
            "Ablation should show whether long-term sequences, current observations, spectral features, or fusion drive the result.",
            "消融结果应说明长期序列、当前观测、能谱特征和融合结构分别对结果产生了多少影响。",
        ),
        (
            "Error analysis should constrain the final claim boundary and identify data or method limitations.",
            "错误分析需要反过来约束最终结论，并指出数据或方法上仍然存在的限制。",
        ),
    ]
    for old, new in templates:
        text = text.replace(old, new)
    return text


def _cn_join(values: list[Any]) -> str:
    return "、".join(_cn_term(value) for value in values if str(value or "").strip())


def _render_research_plan_cn(project_meta: dict[str, Any], blueprint: dict[str, Any]) -> str:
    synthesis = blueprint.get("literature_synthesis") or {}
    method_terms = _cn_join(synthesis.get("key_methods") or [])
    data_terms = _cn_join(synthesis.get("key_data_modalities") or [])
    gap_terms = [_cn_sentence(item) for item in (synthesis.get("gap_evidence") or [])[:2] if str(item or "").strip()]
    if method_terms or data_terms:
        synthesis_summary = (
            f"当前文献主要为本研究提供了两类支撑：方法侧集中在{method_terms or '相关模型与验证流程'}，"
            f"数据侧集中在{data_terms or '观测样本、特征构建和标签支撑'}。这些文献的作用不是简单证明本研究一定成立，"
            "而是帮助确定哪些数据输入、模型比较和验证环节必须在后续流程中被明确实现。"
        )
    else:
        synthesis_summary = "当前文献综合结果仍需在 references 阶段继续补充；在正式写作前，应优先检查文献综述索引中的每篇文献是否确实服务于本研究。"
    if gap_terms:
        synthesis_summary += " 与研究缺口直接相关的证据包括：" + "；".join(gap_terms) + "。"
    lines = [
        "# 文献驱动研究方案",
        "",
        "## 项目背景",
        "",
        f"本研究暂定题目为：{_cn_term(project_meta.get('title') or project_meta.get('idea'))}。",
        "",
        f"核心研究想法是围绕“{_cn_term(project_meta.get('idea'))}”构建一套可复验的研究流程。这里的重点不是先写出漂亮的论文表述，而是把文献证据、数据条件、方法路线和预期图表在计划阶段先绑定清楚。",
        "",
        f"研究领域可概括为：{_cn_term(project_meta.get('field'))}。",
        "",
        f"目标期刊为：{project_meta.get('target_journal') or '尚未指定'}。",
        "",
        "## 文献综合",
        "",
        synthesis_summary,
        "",
        "从当前文献证据看，后续写作需要把研究意义落在三个层面：已有工作如何处理类似数据，已有方法在哪些场景下有效，以及本研究的数据与方法是否足以支撑更进一步的结论。Introduction 和 Discussion 应围绕这些证据展开，避免只给出笼统背景。",
        "",
        "## 研究问题与预期发现",
        "",
    ]
    for claim in blueprint.get("research_claims") or []:
        lines.extend([
            f"- {claim.get('claim_id')}：{_cn_sentence(claim.get('research_question'))}",
            f"  预期发现：{_cn_sentence(claim.get('expected_finding'))}",
            "",
        ])
    lines.extend([
        "## 数据与方法约束",
        "",
        "后续数据阶段应优先确认样本覆盖、标签来源、模态缺失、时间采样和质量控制记录。方法阶段则必须围绕这些数据条件构建，而不是脱离数据空谈模型。若某一类数据无法获得，相应图表和结论需要降级，而不是继续保留强结论。",
        "",
        "## 图表故事板",
        "",
    ])
    for index, item in enumerate((blueprint.get("figure_storyboard") or {}).get("figures") or [], start=1):
        lines.extend([
            f"- 图{index}：{_cn_term(item.get('proposed_title'))}",
            f"  研究问题：{_cn_sentence(item.get('research_question'))}",
            f"  预期发现：{_cn_sentence(item.get('expected_finding'))}",
            f"  数据需求：{_cn_join(item.get('required_data') or [])}",
            f"  方法需求：{_cn_join(item.get('required_method') or [])}",
            f"  验证指标：{_cn_term(item.get('validation_metric'))}",
            "",
        ])
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
            f"- 任务{index}：该任务服务于第{index}张主图，核心方法为{_cn_term(task.get('method_family'))}。",
            f"  需要输入的数据包括：{_cn_join(task.get('required_data') or [])}；验证指标为：{_cn_term(task.get('validation_metric'))}。",
        ])
    lines.extend([
        "",
        "## 风险与人工确认",
        "",
        "在进入正式写作和代码生成前，需要人工确认三件事：第一，当前文献集合是否足够覆盖背景、数据和方法；第二，本地或服务器端数据是否能满足图表故事板中的数据需求；第三，方法代码是否能够真实跑出对应图表，而不是只生成流程图或占位图。",
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
    if chinese_chars < 120 or chinese_chars <= ascii_letters * 0.12:
        raise ResearchPlanQualityError("research_plan.zh-CN.md is not sufficiently localized into fluent Chinese.")
    if "Research question:" in text or "Expected finding:" in text:
        raise ResearchPlanQualityError("research_plan.zh-CN.md still contains untranslated English structural labels.")


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
    questions = _build_research_questions(project_meta, citation_rows)
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
        "## Literature Basis",
        "",
        f"This plan is based on {len(literature_items)} retrieved literature records and {len(citation_rows)} citation-evidence rows. It should be revised whenever the references stage changes.",
        "",
    ]

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
        "## Hypotheses",
        "",
        "- H1: A method designed around the literature-supported gap will improve over baseline approaches when evaluated with a transparent validation protocol.",
        "- H2: The selected data construction and preprocessing steps will materially affect model reliability and should be tested through ablation or sensitivity analysis.",
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
    try:
        blueprint = build_research_blueprint(
            project_meta=state.metadata,
            literature_items=literature_items,
            citation_rows=citation_rows,
            discipline_profile=discipline_profile,
            anchor_papers=anchor_papers,
        )
    except ResearchBlueprintQualityError as exc:
        raise ResearchPlanQualityError(str(exc)) from exc
    _write_json(research_plan_dir / "research_blueprint.json", blueprint)
    claim_contract = build_claim_contract_from_blueprint(blueprint)
    _write_json(research_plan_dir / "claim_contract.json", claim_contract)
    _write_json(research_plan_dir / "figure_storyboard.json", blueprint["figure_storyboard"])
    _write_json(research_plan_dir / "method_plan.json", blueprint["method_plan"])
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
    (research_plan_dir / "research_plan.md").write_text(plan_text, encoding="utf-8")
    (research_plan_dir / "research_plan.zh-CN.md").write_text(plan_text_cn, encoding="utf-8")

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
        "outputs": RESEARCH_PLAN_OUTPUTS,
    }
