"""Discipline ontology and symmetric cross-discipline literature policy."""

from __future__ import annotations

import re
from typing import Any, Iterable


DISCIPLINE_UNKNOWN = "discipline_unknown"
GENERAL_METHODOLOGY = "general_methodology"
GENUINELY_MULTIDISCIPLINARY = "genuinely_multidisciplinary"
GENERAL_BACKGROUND = "general_background"

_CROSS_DISCIPLINE_ROLES = {
    "method_transfer",
    "comparison",
    "general_methodology",
    "statistical_method",
}


# Markers are intentionally conservative. High-specificity markers are used as
# conflict evidence; broad words such as "population" and "survey" never are.
DISCIPLINE_ONTOLOGY: dict[str, dict[str, Any]] = {
    "astronomy": {
        "parent": "physical_science",
        "markers": (
            "astronomy",
            "astrophysics",
            "galaxy",
            "galaxies",
            "stellar",
            "redshift",
            "cosmology",
            "supernova",
            "天文学",
            "天体物理",
            "星系",
            "恒星",
            "红移",
        ),
        "high_specificity_markers": (
            "astrophysics",
            "galaxy",
            "galaxies",
            "redshift",
            "cosmology",
            "天体物理",
            "星系",
            "红移",
        ),
    },
    "physics": {
        "parent": "physical_science",
        "markers": ("physics", "quantum", "particle physics", "condensed matter", "物理", "量子"),
        "high_specificity_markers": ("particle physics", "condensed matter", "量子物理"),
    },
    "medicine": {
        "parent": "health_science",
        "markers": (
            "medicine",
            "medical",
            "clinical",
            "patient",
            "disease",
            "diagnosis",
            "therapy",
            "医学",
            "临床",
            "患者",
            "疾病",
            "诊断",
        ),
        "high_specificity_markers": ("clinical trial", "patient cohort", "diagnosis", "therapy", "临床试验", "患者队列"),
    },
    "public_health": {
        "parent": "health_science",
        "markers": (
            "public health",
            "epidemiology",
            "population health",
            "health policy",
            "公共卫生",
            "流行病学",
            "人群健康",
        ),
        "high_specificity_markers": ("public health", "epidemiology", "公共卫生", "流行病学"),
    },
    "life_science": {
        "parent": "life_science",
        "markers": (
            "biology",
            "biological",
            "genomic",
            "transcriptomic",
            "protein",
            "cellular",
            "生物",
            "基因",
            "转录组",
            "蛋白",
            "细胞",
        ),
        "high_specificity_markers": ("genomic", "transcriptomic", "protein", "cellular", "基因组", "转录组", "蛋白质"),
    },
    "ecology": {
        "parent": "life_science",
        "markers": (
            "ecology",
            "ecological",
            "biodiversity",
            "ecosystem",
            "habitat",
            "conservation",
            "species richness",
            "food web",
            "vegetation",
            "生态",
            "生态学",
            "生物多样性",
            "生态系统",
            "栖息地",
            "物种丰富度",
            "食物网",
            "植被",
        ),
        "high_specificity_markers": (
            "ecology",
            "ecological",
            "biodiversity",
            "ecosystem",
            "species richness",
            "生态学",
            "生物多样性",
            "生态系统",
        ),
    },
    "environmental_science": {
        "parent": "earth_science",
        "markers": (
            "environmental science",
            "environmental change",
            "pollution",
            "climate impact",
            "环境科学",
            "环境变化",
            "污染",
        ),
        "high_specificity_markers": ("environmental science", "pollution", "环境科学", "污染"),
    },
    "agriculture": {
        "parent": "life_science",
        "markers": (
            "agriculture",
            "agricultural",
            "crop",
            "soil fertility",
            "livestock",
            "农业",
            "农作物",
            "土壤肥力",
            "畜牧",
        ),
        "high_specificity_markers": ("agriculture", "agricultural", "crop yield", "农业", "农作物"),
    },
    "computer_science": {
        "parent": "computing",
        "markers": ("computer science", "software", "algorithm", "programming", "database", "计算机", "软件", "算法", "编程"),
        "high_specificity_markers": ("computer science", "software engineering", "programming", "计算机科学", "软件工程"),
    },
    "machine_learning": {
        "parent": "computing",
        "markers": (
            "machine learning",
            "deep learning",
            "neural network",
            "transformer",
            "representation learning",
            "foundation model",
            "机器学习",
            "深度学习",
            "神经网络",
            "表征学习",
        ),
        "high_specificity_markers": ("machine learning", "deep learning", "neural network", "机器学习", "深度学习", "神经网络"),
    },
    "statistics": {
        "parent": "mathematical_science",
        "markers": (
            "statistics",
            "statistical inference",
            "causal inference",
            "bayesian",
            "统计学",
            "统计推断",
            "因果推断",
            "贝叶斯",
        ),
        "high_specificity_markers": ("statistical inference", "causal inference", "统计推断", "因果推断"),
    },
    "social_science": {
        "parent": "social_science",
        "markers": (
            "social science",
            "society",
            "governance",
            "rural",
            "village",
            "public administration",
            "社会科学",
            "治理",
            "乡村",
            "农村",
            "公共管理",
        ),
        "high_specificity_markers": ("social science", "rural governance", "public administration", "社会科学", "乡村治理", "公共管理"),
    },
    "economics": {
        "parent": "social_science",
        "markers": ("economics", "economic", "finance", "income", "economy", "econometric", "经济", "金融", "收入", "计量经济"),
        "high_specificity_markers": ("economics", "econometric", "经济学", "计量经济"),
    },
    "geography": {
        "parent": "earth_science",
        "markers": (
            "geography",
            "geospatial",
            "remote sensing",
            "earth observation",
            "land cover",
            "地理",
            "地理空间",
            "遥感",
            "对地观测",
            "土地覆盖",
        ),
        "high_specificity_markers": ("geospatial", "remote sensing", "earth observation", "地理空间", "遥感", "对地观测"),
    },
    "chemistry": {
        "parent": "physical_science",
        "markers": ("chemistry", "chemical", "molecule", "compound", "化学", "分子", "化合物"),
        "high_specificity_markers": ("chemistry", "chemical reaction", "化学", "化学反应"),
    },
    "materials_science": {
        "parent": "physical_science",
        "markers": ("materials science", "material", "crystal", "alloy", "perovskite", "材料", "晶体", "合金", "钙钛矿"),
        "high_specificity_markers": ("materials science", "perovskite", "材料科学", "钙钛矿"),
    },
    "law": {
        "parent": "social_science",
        "markers": ("law", "legal", "jurisdiction", "regulation", "法学", "法律", "司法管辖", "监管"),
        "high_specificity_markers": ("legal doctrine", "jurisdiction", "法学", "司法管辖"),
    },
    "humanities": {
        "parent": "humanities",
        "markers": ("humanities", "history", "philosophy", "literature studies", "人文学", "历史学", "哲学", "文学研究"),
        "high_specificity_markers": ("humanities", "philosophy", "人文学", "哲学"),
    },
}


def _normalized(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "").casefold()).strip()


def _marker_present(text: str, marker: str) -> bool:
    value = marker.casefold()
    if re.search(r"[\u3400-\u9fff]", value):
        return value in text
    escaped = re.escape(value).replace(r"\ ", r"\s+")
    return re.search(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", text) is not None


def discipline_evidence(text: Any, *, max_results: int = 5) -> list[dict[str, Any]]:
    """Return ranked discipline hypotheses with auditable marker evidence."""
    value = _normalized(text)
    rows: list[dict[str, Any]] = []
    for discipline, profile in DISCIPLINE_ONTOLOGY.items():
        markers = [marker for marker in profile.get("markers") or () if _marker_present(value, str(marker))]
        high = [marker for marker in profile.get("high_specificity_markers") or () if _marker_present(value, str(marker))]
        if not markers:
            continue
        rows.append(
            {
                "discipline": discipline,
                "parent": profile.get("parent"),
                "markers": sorted(set(markers)),
                "high_specificity_markers": sorted(set(high)),
                "score": len(markers) + (2 * len(high)),
            }
        )
    rows.sort(key=lambda item: (-int(item["score"]), str(item["discipline"])))
    return rows[:max_results]


def discipline_hypotheses_from_ontology(text: Any, *, max_results: int = 4) -> list[str]:
    rows = discipline_evidence(text, max_results=max_results)
    return [str(row["discipline"]) for row in rows] or [DISCIPLINE_UNKNOWN]


def discipline_marker_terms(disciplines: Iterable[str], text: Any) -> list[str]:
    """Return the actual marker phrases supporting the requested disciplines."""
    allowed = {str(value) for value in disciplines}
    result: list[str] = []
    for row in discipline_evidence(text, max_results=len(DISCIPLINE_ONTOLOGY)):
        if row["discipline"] not in allowed:
            continue
        result.extend(str(value) for value in row["markers"])
    return list(dict.fromkeys(result))


def _expanded_disciplines(values: Iterable[str]) -> set[str]:
    expanded: set[str] = set()
    for raw in values:
        value = str(raw or "").strip()
        if not value or value in {"general", DISCIPLINE_UNKNOWN}:
            continue
        expanded.add(value)
        parent = str((DISCIPLINE_ONTOLOGY.get(value) or {}).get("parent") or "")
        if parent:
            expanded.add(parent)
    return expanded


def _declared_cross_discipline_role(item: dict[str, Any] | None) -> str:
    if not item:
        return ""
    for key in ("cross_discipline_role", "citation_role", "intended_role", "intended_use"):
        value = str(item.get(key) or "").strip().casefold().replace("-", "_").replace(" ", "_")
        if value in _CROSS_DISCIPLINE_ROLES:
            return value
    return ""


def assess_discipline_compatibility(
    project_disciplines: Iterable[str],
    candidate_disciplines: Iterable[str],
    *,
    candidate_evidence: Iterable[dict[str, Any]] = (),
    item: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply one symmetric compatibility rule with explicit transfer exceptions."""
    project = {str(value) for value in project_disciplines if str(value).strip()}
    candidate = {str(value) for value in candidate_disciplines if str(value).strip()}
    project_unknown = not project or project <= {"general", DISCIPLINE_UNKNOWN}
    candidate_unknown = not candidate or candidate <= {"general", DISCIPLINE_UNKNOWN}
    role = _declared_cross_discipline_role(item)
    if project_unknown or candidate_unknown:
        return {
            "state": "review_required",
            "score": 0.35,
            "reason_codes": ["project_discipline_unknown" if project_unknown else "candidate_discipline_unknown"],
            "project_disciplines": sorted(project),
            "candidate_disciplines": sorted(candidate),
            "cross_discipline_role": role or None,
        }

    project_expanded = _expanded_disciplines(project)
    candidate_expanded = _expanded_disciplines(candidate)
    overlap = sorted(project_expanded & candidate_expanded)
    if overlap:
        return {
            "state": "accepted",
            "score": 1.0,
            "reason_codes": ["discipline_overlap"],
            "overlap": overlap,
            "project_disciplines": sorted(project),
            "candidate_disciplines": sorted(candidate),
            "cross_discipline_role": role or None,
        }

    if role:
        return {
            "state": "review_required",
            "score": 0.6,
            "reason_codes": ["explicit_cross_discipline_role"],
            "project_disciplines": sorted(project),
            "candidate_disciplines": sorted(candidate),
            "cross_discipline_role": role,
        }

    high_specificity = sorted(
        {
            str(marker)
            for row in candidate_evidence
            if isinstance(row, dict)
            for marker in row.get("high_specificity_markers") or []
        }
    )
    return {
        "state": "rejected",
        "score": 0.0,
        "reason_codes": ["symmetric_discipline_conflict"],
        "conflicting_markers": high_specificity,
        "project_disciplines": sorted(project),
        "candidate_disciplines": sorted(candidate),
        "cross_discipline_role": None,
    }


def ontology_snapshot() -> dict[str, Any]:
    return {
        "schema_version": "dpl.literature_discipline_ontology.v1",
        "unknown_state": DISCIPLINE_UNKNOWN,
        "disciplines": DISCIPLINE_ONTOLOGY,
        "cross_discipline_roles": sorted(_CROSS_DISCIPLINE_ROLES),
    }


def generated_conflict_terms(project_disciplines: Iterable[str], *, limit: int = 40) -> tuple[list[str], list[dict[str, Any]]]:
    """Return explainable negative evidence without turning single terms into automatic rejection."""
    project_expanded = _expanded_disciplines(project_disciplines)
    terms: list[str] = []
    evidence: list[dict[str, Any]] = []
    for discipline, profile in DISCIPLINE_ONTOLOGY.items():
        candidate_expanded = _expanded_disciplines([discipline])
        if project_expanded & candidate_expanded:
            continue
        markers = [str(value) for value in profile.get("high_specificity_markers") or ()]
        if not markers:
            continue
        evidence.append(
            {
                "discipline": discipline,
                "severity": "discipline_conflict_evidence",
                "markers": markers,
                "policy": "marker_requires_candidate_discipline_assessment_not_single_term_rejection",
            }
        )
        terms.extend(markers)
    return list(dict.fromkeys(terms))[:limit], evidence
