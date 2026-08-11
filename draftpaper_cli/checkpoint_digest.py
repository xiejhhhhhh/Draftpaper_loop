"""Deterministic content digests for human-review checkpoints.

The checkpoint ledger records a transaction boundary, while this module
describes the complete scientific deliverables that the boundary asks a user
to review.  It deliberately reads existing project evidence and never invents
scientific values from file names or free-form model output.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any, Iterable

from .stale_sync import detect_artifact_drift
from .evidence_identity import (
    build_count_identity_report,
    compare_evidence,
    normalize_count_evidence,
    normalize_metric_evidence,
)
from .code_ownership import assess_figure_code_trace
from .run_evidence_bundle import load_active_run_evidence_bundle


STAGE_SCOPE_PREFIXES: dict[str, tuple[str, ...]] = {
    "research_plan": ("research_plan/", "journal_profile/", "plugins/"),
    "research_plan_feasibility": ("research_plan/", "data/", "methods/", "review/"),
    "data": ("data/", "review/"),
    "method_plan": ("methods/", "research_plan/", "review/"),
    "methods": ("methods/", "code/", "results/", "review/"),
    "result_support": ("results/", "review/", "methods/", "data/"),
    "core_evidence": ("core_evidence/", "results/", "methods/", "data/", "review/"),
    "plugin": ("plugins/", "research_plan/", "review/"),
    "quality_checks": ("quality_checks/", "quality/", "integrity/", "citation_audit/", "review/", "latex/"),
    "writing": ("writing/", "latex/", "review/"),
    "results": ("results/", "review/", "methods/", "data/"),
    "introduction": ("introduction/", "writing/", "latex/", "references/", "review/"),
    "data_writing": ("data/", "data_writing/", "latex/", "review/"),
    "methods_writing": ("methods/", "methods_writing/", "latex/", "review/"),
    "discussion": ("discussion/", "writing/", "latex/", "results/", "references/"),
    "latex": ("latex/", "writing/", "references/", "review/"),
    "citation_audit": ("citation_audit/", "references/", "latex/", "review/"),
}

_DISCOVERY_EXCLUDED_PREFIXES = (
    ".draftpaper/",
    "review/checkpoints/",
    "review/independent_review/",
)


STAGE_PURPOSES = {
    "research_plan": "确认研究问题、研究蓝图、可行性边界和后续科学决策点。",
    "research_plan_feasibility": "确认研究蓝图与数据、方法和统计可行性是否匹配。",
    "data": "确认数据来源、样本边界、质量、缺失性和划分合同。",
    "method_plan": "确认方法、统计合同、输入输出和可复现执行计划。",
    "methods": "确认方法已经按项目合同执行，并形成可追溯的运行证据。",
    "result_support": "确认结果有效性、论断支撑和补充或收窄路线。",
    "core_evidence": "确认关键图表、核心结果、运行身份和论断边界。",
    "plugin": "确认科研插件来源、许可证、绑定状态、验证结果和晋升条件。",
    "quality_checks": "确认最终稿、引用、PDF、审查和发布证据是否完整。",
    "writing": "确认章节或作者补全内容、来源、变更范围和上游失效影响。",
    "results": "确认结果章节使用的图表、指标、证据来源和论断边界。",
    "introduction": "确认引言文字、研究动机、文献来源和论断范围。",
    "data_writing": "确认 Data 章节使用的数据来源、样本边界和数据质量证据。",
    "methods_writing": "确认 Methods 章节使用的方法、统计合同和运行证据。",
    "discussion": "确认 Discussion 章节的解释边界、局限性和证据对应关系。",
    "latex": "确认 LaTeX 组装、图表引用、参考文献和 PDF 输入完整。",
    "citation_audit": "确认参考文献元数据、正文引用和引用证据一致。",
}

_STAGE_ADAPTER_ALIASES = {
    "results": "writing",
    "introduction": "writing",
    "data_writing": "writing",
    "methods_writing": "writing",
    "discussion": "writing",
    "latex": "quality_checks",
    "citation_audit": "quality_checks",
}

_STAGE_BOUNDARIES = {
    "research_plan": "研究蓝图只冻结研究问题、数据角色、方法合同和论断边界，不等于结果已经成立。",
    "research_plan_feasibility": "可行性报告只说明当前数据和方法是否能支撑计划，不替代实际运行证据。",
    "data": "数据阶段只确认来源、样本、质量和划分合同，不把数据清单扩展为科学结果。",
    "method_plan": "方法计划只确认输入、输出、统计合同和执行路线，不等于方法已经产生有效结果。",
    "methods": "方法运行证据只绑定实际执行和输出身份，不替代结果有效性与论断支撑审查。",
    "core_evidence": "关键结果只能在当前 plan、run、cohort、验证设计和证据快照范围内解释。",
    "result_support": "结果支撑不足时，不得把当前指标扩展为已确认的研究结论。",
    "plugin": "插件候选、fixture 或元数据发现不能冒充真实论文证据；只有 project run 和匹配 hash 才能进入证据链。",
    "quality_checks": "质量检查通过不等于作者完成科学确认；发布状态仍受稿件、引用、PDF 和人工确认约束。",
    "writing": "文字或作者补全只在其声明的变更类别和上游证据范围内生效；科学内容变化必须重新打开受影响上游。",
    "results": "结果章节只能使用当前已确认的图表、指标和证据快照，不得新增未审查的科学结论。",
    "introduction": "引言只能使用已核验的文献和研究蓝图边界，不因文字润色扩大研究主张。",
    "data_writing": "Data 章节只能描述已绑定的数据来源、样本边界和质量证据。",
    "methods_writing": "Methods 章节只能描述已执行且可追溯的方法和统计合同。",
    "discussion": "Discussion 章节必须区分证据支持、条件解释和未来工作，不得把相关性写成因果性。",
    "latex": "LaTeX/PDF 组装只确认呈现和引用完整，不改变上游科学证据。",
    "citation_audit": "引用核查只确认引用、元数据和证据对应关系，不自动增加未经审阅的参考文献。",
}

_CORE_PATHS = (
    "core_evidence/core_evidence_report.json",
    "core_evidence/core_evidence_report.html",
    "results/result_validity_report.json",
    "results/result_support_checkpoint.json",
    "results/result_support_checkpoint.md",
    "results/result_support_checkpoint.html",
    "results/promoted_evidence_snapshot.json",
    "results/resolved_result_evidence.json",
    "results/result_manifest.yaml",
    "results/stage_manifest.json",
    "results/figure_metadata.json",
    "results/figure_code_trace.json",
    "results/figure_plan.json",
    "results/figure_contracts.json",
    "results/figure_quality_report.json",
    "results/scientific_figure_quality_report.json",
    "results/figure_semantic_validation_report.json",
    "results/figure_caption_validation_report.json",
    "results/confirmed_figure_alignment_report.json",
    "results/figure_execution_diagnosis.json",
    "results/formal_run_reuse_audit.json",
    "data/formal_data_run_binding.json",
    "methods/run_manifest.yaml",
    "methods/analysis_code_manifest.json",
    "methods/method_code_manifest.json",
    "methods/stage_manifest.json",
)

_CSV_PREVIEW_LIMIT = 5
_MAX_SUMMARY_ITEMS = 12


def _read_json(root: Path, relative: str) -> Any:
    path = root / relative
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def _first_scalar(value: Any, keys: set[str]) -> str | None:
    """Find the first scalar value for an explicitly named evidence field."""

    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in keys and isinstance(child, (str, int, float, bool)):
                text = str(child).strip()
                if text:
                    return text
        for child in value.values():
            found = _first_scalar(child, keys)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _first_scalar(child, keys)
            if found:
                return found
    return None


def _run_id_from_yaml(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            match = re.match(r"^\s*run_id\s*:\s*[\"']?([^\"'\s#]+)", line)
            if match:
                return match.group(1)
    except (OSError, UnicodeError):
        return None
    return None


def _generic_identity(root: Path, deliverables: list[dict[str, Any]], payload: dict[str, Any]) -> dict[str, str | None]:
    """Extract only named identity fields from stage-local structured evidence."""

    plan_hash = str(payload.get("confirmed_plan_hash") or payload.get("plan_hash") or "") or None
    run_id = str(payload.get("run_id") or "") or None
    cohort_id = str(payload.get("cohort_id") or payload.get("cohort") or "") or None
    sample_unit = str(payload.get("sample_unit") or "") or None
    validation_design = str(payload.get("validation_design") or payload.get("split") or "") or None
    evidence_snapshot_id = str(payload.get("evidence_snapshot_id") or "") or None

    candidates = sorted(
        {
            str(item.get("project_relative_path") or "")
            for item in deliverables
            if str(item.get("project_relative_path") or "").lower().endswith(".json")
        },
        key=lambda value: (
            0 if any(token in value.lower() for token in ("manifest", "plan", "binding", "snapshot", "report")) else 1,
            value,
        ),
    )
    for relative in candidates[:48]:
        data = _read_json(root, relative)
        if data is None:
            continue
        plan_hash = plan_hash or _first_scalar(data, {"confirmed_plan_hash", "plan_hash", "research_plan_hash"})
        run_id = run_id or _first_scalar(data, {"run_id", "resolved_run_id", "selected_run_id"})
        cohort_id = cohort_id or _first_scalar(data, {"cohort_id", "cohort", "cohort_label"})
        sample_unit = sample_unit or _first_scalar(data, {"sample_unit", "unit_of_analysis", "observation_unit"})
        validation_design = validation_design or _first_scalar(data, {"validation_design", "split", "split_strategy"})
        evidence_snapshot_id = evidence_snapshot_id or _first_scalar(data, {"evidence_snapshot_id", "promoted_evidence_snapshot_id", "snapshot_id"})

    if not run_id:
        for relative in ("methods/run_manifest.yaml", "methods/run_manifest.yml", "run_manifest.yaml"):
            run_id = _run_id_from_yaml(root / relative)
            if run_id:
                break
    return {
        "plan_hash": plan_hash,
        "run_id": run_id,
        "cohort_id": cohort_id,
        "sample_unit": sample_unit,
        "validation_design": validation_design,
        "evidence_snapshot_id": evidence_snapshot_id,
    }


def _generic_stage_digest(
    root: Path,
    stage: str,
    deliverables: list[dict[str, Any]],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Build a deterministic summary for non-result human checkpoints."""

    identity = _generic_identity(root, deliverables, payload)
    counts: dict[str, int] = {}
    for item in deliverables:
        group = str(item.get("deliverable_group") or "manifest")
        counts[group] = counts.get(group, 0) + 1
    changed = [item for item in deliverables if str(item.get("operation") or "") in {"generated", "modified", "deployed"}]
    action = "生成或更新并审阅" if changed else "汇总并审阅"
    group_text = "、".join(
        f"{count}{_group_title(group)}"
        for group, count in (
            ("figure", counts.get("figure", 0)),
            ("table", counts.get("table", 0)),
            ("prose", counts.get("prose", 0)),
            ("code", counts.get("code", 0)),
            ("run_evidence", counts.get("run_evidence", 0)),
            ("review_report", counts.get("review_report", 0)),
        )
        if count
    ) or "阶段产物"
    purpose = STAGE_PURPOSES.get(stage, f"{stage} 阶段人工确认")
    inventory = _deliverable_inventory_text(deliverables)
    narrative = f"本阶段围绕{purpose}{action}{group_text}，共纳入 {len(deliverables)} 项确认范围内成果。"
    if inventory:
        narrative += f"具体包括{inventory}。"
    if identity["run_id"]:
        narrative += f"当前绑定运行 {identity['run_id']}"
        if identity["validation_design"]:
            narrative += f"，验证设计为 {identity['validation_design']}"
        narrative += "。"
    if identity["plan_hash"]:
        narrative += "产物与当前研究蓝图 hash 绑定。"
    narrative += "页面只描述当前阶段产物、来源和验证状态，不把阶段准备工作扩展为论文科学结论。"

    key_findings: list[dict[str, Any]] = [
        {
            "summary_zh": f"确认范围包含 {len(deliverables)} 项产物：{group_text}。",
            "source_paths": [str(item.get("project_relative_path") or "") for item in deliverables[:8]],
        }
    ]
    if changed:
        key_findings.append(
            {
                "summary_zh": f"相对上一快照有 {len(changed)} 项新增、修改或部署产物；未变化但属于确认范围的成果仍完整展示。",
                "source_paths": [str(item.get("project_relative_path") or "") for item in changed[:8]],
            }
        )
    if identity["run_id"] or identity["plan_hash"]:
        identity_parts = []
        if identity["run_id"]:
            identity_parts.append(f"run={identity['run_id']}")
        if identity["plan_hash"]:
            identity_parts.append(f"plan_hash={identity['plan_hash']}")
        key_findings.append(
            {
                "summary_zh": "当前结构化身份为 " + "，".join(identity_parts) + "。",
                "source_paths": [str(item.get("project_relative_path") or "") for item in deliverables if item.get("deliverable_group") in {"run_evidence", "manifest", "review_report"}][:5],
            }
        )
    report_items = [
        item for item in deliverables
        if item.get("deliverable_group") in {"review_report", "run_evidence"}
        and str(item.get("project_relative_path") or "").lower().endswith(".json")
    ]
    report_states: list[str] = []
    for item in report_items[:24]:
        data = _read_json(root, str(item.get("project_relative_path") or ""))
        status = _first_scalar(data, {"decision", "status", "support_level", "review_state", "scientific_evidence_status"}) if data is not None else None
        if status:
            report_states.append(f"{Path(str(item.get('project_relative_path'))).name}={status}")
    if report_states:
        key_findings.append(
            {
                "summary_zh": "阶段报告登记状态：" + "；".join(report_states[:5]) + "。",
                "source_paths": [str(item.get("project_relative_path") or "") for item in report_items[:5]],
            }
        )

    validation = [
        {
            "name_zh": "阶段产物归纳",
            "status": "pass" if deliverables else "missing",
            "detail_zh": f"已归纳 {len(deliverables)} 项阶段产物并按成果类型分组。" if deliverables else "未发现阶段产物。",
            "evidence": str(deliverables[0].get("project_relative_path") or "") if deliverables else None,
            "blocking": not bool(deliverables),
        }
    ]
    if report_items:
        validation.append(
            {
                "name_zh": "阶段审查来源",
                "status": "pass",
                "detail_zh": f"已登记 {len(report_items)} 项报告或运行证据，页面显示其路径和状态。",
                "evidence": str(report_items[0].get("project_relative_path") or ""),
                "blocking": False,
            }
        )
    return {
        "figure_items": [],
        "stage_narrative_zh": narrative,
        "key_findings": key_findings[:_MAX_SUMMARY_ITEMS],
        "claim_boundaries": [{"summary_zh": _STAGE_BOUNDARIES.get(stage, _STAGE_BOUNDARIES["writing"])}],
        "validation_summary": validation,
        "consistency_checks": [],
        "unresolved": [],
        "decision_routes": [item for item in payload.get("route_options") or [] if isinstance(item, dict)],
        "decision_route_state": payload.get("decision_route_state") or {},
        "core_metrics": {
            "run_id": identity["run_id"] or "",
            "sample_unit": identity["sample_unit"] or "",
            "validation_design": identity["validation_design"] or "",
            "metric_source": "",
        },
        "identity": identity,
        "promoted_evidence_snapshot_id": identity["evidence_snapshot_id"],
    }


def _relative_path(root: Path, value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = Path(value.strip().strip('"'))
    try:
        root_resolved = root.resolve()
        resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
        normalized = resolved.relative_to(root_resolved).as_posix()
    except (OSError, ValueError):
        return None
    return normalized if normalized and normalized != "." and (root_resolved / normalized).is_file() else None


def _iter_code_paths(value: Any, root: Path) -> Iterable[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in {"code_files", "script", "script_path", "source_code", "entrypoint"}:
                children = child if isinstance(child, list) else [child]
                for item in children:
                    relative = _relative_path(root, item)
                    if relative:
                        yield relative
            yield from _iter_code_paths(child, root)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_code_paths(child, root)


def discover_stage_paths(root: Path, stage: str) -> list[str]:
    """Return stage-owned evidence paths that sparse manifests do not expose.

    Stage manifests remain authoritative for large external products. This
    discovery pass adds small, reviewable stage-owned files so a checkpoint
    cannot silently omit a generated manuscript, report, script, table, or
    figure merely because a plugin forgot to repeat the path in its payload.
    """

    candidates: set[str] = set()
    discoverable_suffixes = {
        ".csv",
        ".html",
        ".ipynb",
        ".jl",
        ".json",
        ".md",
        ".pdf",
        ".png",
        ".jpg",
        ".jpeg",
        ".py",
        ".r",
        ".sh",
        ".tex",
        ".tsv",
        ".yaml",
        ".yml",
    }
    prefixes = STAGE_SCOPE_PREFIXES.get(stage, (f"{stage}/",))
    for prefix in prefixes:
        directory = root / prefix.rstrip("/")
        if not directory.is_dir():
            continue
        for path in directory.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in discoverable_suffixes:
                continue
            relative = path.relative_to(root).as_posix()
            if any(relative.startswith(excluded) for excluded in _DISCOVERY_EXCLUDED_PREFIXES):
                continue
            try:
                if path.stat().st_size <= 32 * 1024 * 1024:
                    candidates.add(relative)
            except OSError:
                continue
    if stage == "core_evidence":
        candidates.update(_CORE_PATHS)
        trace = _read_json(root, "results/figure_code_trace.json")
        candidates.update(_iter_code_paths(trace, root))
        candidates.update(
            path.relative_to(root).as_posix()
            for directory in (root / "results" / "figures", root / "results" / "tables")
            if directory.is_dir()
            for path in directory.rglob("*")
            if path.is_file() and path.suffix.lower() in {".png", ".pdf", ".csv", ".json"}
        )
        candidates.update(
            path.relative_to(root).as_posix()
            for directory in (
                root / "methods" / "scripts",
                root / "methods" / "plotting",
                root / "methods" / "src",
                root / "code" / "scripts",
                root / "code" / "src",
            )
            if directory.is_dir()
            for path in directory.rglob("*")
            if path.is_file() and path.suffix.lower() in {".py", ".r", ".jl", ".ipynb", ".sh", ".yaml", ".yml", ".json"}
        )
    return sorted(path for path in candidates if (root / path).is_file())


def _load_csv_preview(root: Path, relative: str) -> dict[str, Any] | None:
    path = root / relative
    if path.suffix.lower() != ".csv" or not path.is_file():
        return None
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = [str(item) for item in (reader.fieldnames or [])]
            rows = [{str(key): str(value) for key, value in row.items()} for row in reader][: _CSV_PREVIEW_LIMIT]
        return {"columns": columns, "rows": rows, "preview_truncated": True}
    except (OSError, UnicodeError, csv.Error):
        return {"columns": [], "rows": [], "preview_error": "无法按 UTF-8 CSV 读取"}


def _group_for_path(relative: str) -> str:
    normalized = relative.replace("\\", "/").lower()
    suffix = Path(normalized).suffix
    if "/figures/" in normalized or suffix in {".png", ".pdf", ".jpg", ".jpeg"}:
        return "figure"
    if "/tables/" in normalized or suffix in {".csv", ".tsv"}:
        return "table"
    if normalized.startswith(("methods/", "code/", "data/scripts/")) and suffix in {".py", ".r", ".jl", ".ipynb"}:
        return "code"
    if normalized.endswith((".html", ".md", ".tex")):
        return "prose"
    if "manifest" in normalized or "snapshot" in normalized or normalized.endswith((".yaml", ".yml")):
        return "run_evidence" if any(token in normalized for token in ("run", "result", "evidence", "snapshot")) else "manifest"
    if normalized.endswith(".json"):
        return "review_report"
    return "manifest"


def _group_title(group: str) -> str:
    return {
        "figure": "关键图表",
        "table": "结果表格",
        "prose": "文字与审查报告",
        "code": "分析与绘图代码",
        "run_evidence": "运行与证据身份",
        "review_report": "验证与审查报告",
        "manifest": "技术附件与清单",
    }.get(group, "其他产物")


def _deliverable_inventory_text(deliverables: list[dict[str, Any]], *, per_group: int = 3) -> str:
    """Describe concrete outputs without promoting any artifact to evidence."""

    order = ("figure", "table", "prose", "code", "run_evidence", "review_report", "manifest")
    fragments: list[str] = []
    for group in order:
        items = [
            item
            for item in deliverables
            if str(item.get("deliverable_group") or "manifest") == group
            and str(item.get("project_relative_path") or "")
        ]
        if not items:
            continue
        names = [str(item["project_relative_path"]) for item in items[:per_group]]
        if len(items) > per_group:
            names.append(f"等 {len(items)} 项")
        fragments.append(f"{_group_title(group)}：" + "、".join(names))
    return "；".join(fragments)


def _title_for_path(relative: str, group: str) -> str:
    name = Path(relative).name
    if group == "figure":
        return f"图表 {name}"
    if group == "table":
        return f"表格 {name}"
    if group == "code":
        return f"代码 {name}"
    return name


def _figure_context(root: Path, relative: str) -> dict[str, Any]:
    """Load deterministic figure metadata shared by every review stage."""

    metadata = _read_json(root, "results/figure_metadata.json") or {}
    trace = _read_json(root, "results/figure_code_trace.json") or {}
    core = _read_json(root, "core_evidence/core_evidence_report.json") or {}

    def normalized(value: Any) -> str:
        return str(value or "").replace("\\", "/")

    metadata_items = metadata.get("figures") if isinstance(metadata, dict) else []
    metadata_item = next(
        (item for item in metadata_items or [] if normalized(item.get("path")) == relative),
        {},
    )
    trace_items = trace.get("traces") if isinstance(trace, dict) else []
    trace_item = next(
        (item for item in trace_items or [] if normalized(item.get("figure_path")) == relative),
        {},
    )
    core_items = core.get("reviewable_figures") if isinstance(core, dict) else []
    core_item = next(
        (item for item in core_items or [] if normalized(item.get("path")) == relative),
        {},
    )
    code_files = [
        normalized(item)
        for item in trace_item.get("code_files") or []
        if _relative_path(root, item)
    ]
    statistics = trace_item.get("statistics") or metadata_item.get("statistics") or {}
    return {
        "title_zh": str(
            metadata_item.get("figure_id")
            or core_item.get("figure_id")
            or Path(relative).stem
        ),
        "caption": str(core_item.get("caption") or metadata_item.get("caption") or ""),
        "interpretation_summary": str(
            core_item.get("interpretation_summary")
            or metadata_item.get("interpretation_summary")
            or trace_item.get("interpretation_summary")
            or ""
        ),
        "code_files": code_files,
        "statistics": statistics if isinstance(statistics, dict) else {},
        "preview": {"image_path": relative},
    }


def _short_float(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{number:.3f}" if abs(number) < 1000 else f"{number:.1f}"


def _float_value(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _metric_values(rows: Iterable[dict[str, Any]]) -> dict[str, list[float]]:
    values: dict[str, list[float]] = {}
    for row in rows:
        name = str(row.get("metric") or row.get("metric_name") or "").strip().lower()
        value = _float_value(row.get("value"))
        if name and value is not None:
            values.setdefault(name, []).append(value)
    return values


def _unique(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _core_evidence_digest(root: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    core = _read_json(root, "core_evidence/core_evidence_report.json") or {}
    validity = _read_json(root, "results/result_validity_report.json") or {}
    support = _read_json(root, "results/result_support_checkpoint.json") or {}
    binding = _read_json(root, "data/formal_data_run_binding.json") or {}
    metadata = _read_json(root, "results/figure_metadata.json") or {}
    trace = _read_json(root, "results/figure_code_trace.json") or {}
    resolved_evidence = _read_json(root, "results/resolved_result_evidence.json") or {}
    metric_identity = _read_json(root, "results/metric_identity_report.json") or {}
    if not metric_identity and isinstance(resolved_evidence.get("metric_identity_report"), dict):
        metric_identity = resolved_evidence.get("metric_identity_report") or {}
    count_identity = _read_json(root, "results/count_identity_report.json") or {}
    trace_validation = assess_figure_code_trace(root) if trace else {"status": "missing", "checks": []}
    active_bundle = load_active_run_evidence_bundle(root) if (root / "results" / "active_run_evidence_bundle.json").is_file() else {"status": "not_registered"}
    metrics_path = "results/tables/metrics.csv"
    summary_path = "results/tables/analysis_summary.csv"
    metrics_preview = _load_csv_preview(root, metrics_path)
    summary_preview = _load_csv_preview(root, summary_path)
    run_id = str(validity.get("resolved_run_id") or "")
    metrics = []
    if metrics_preview:
        metrics = [row for row in metrics_preview.get("rows", []) if not run_id or row.get("run_id") == run_id]
    if not metrics:
        metrics = metrics_preview.get("rows", []) if metrics_preview else []
    analysis = []
    if summary_preview:
        analysis = [row for row in summary_preview.get("rows", []) if not run_id or row.get("run_id") == run_id]
    first_metric = metrics[0] if metrics else {}
    first_analysis = analysis[0] if analysis else {}
    support_records = [item for item in support.get("metric_records") or [] if isinstance(item, dict)]
    support_contexts = [item.get("context") for item in support_records if isinstance(item.get("context"), dict)]
    support_run_ids = [str(item.get("run_id") or "") for item in support_contexts if item.get("run_id")]
    binding_run_id = str(binding.get("run_id") or "")
    run_id = run_id or str(first_metric.get("run_id") or first_analysis.get("run_id") or (support_run_ids[0] if support_run_ids else ""))
    sample_unit = str(
        first_metric.get("sample_unit")
        or first_analysis.get("sample_unit")
        or (support_contexts[0].get("sample_unit") if support_contexts else "")
        or binding.get("sample_unit")
        or ""
    )
    validation_design = str(
        first_metric.get("validation_design")
        or first_analysis.get("validation_design")
        or (support_contexts[0].get("validation_design") if support_contexts else "")
        or binding.get("validation_design")
        or binding.get("split")
        or ""
    )
    figures = metadata.get("figures") if isinstance(metadata, dict) else []
    figure_by_path = {
        str(item.get("path")): item
        for item in figures or []
        if isinstance(item, dict) and item.get("path")
    }
    trace_by_figure = {
        str(item.get("figure_path")): item
        for item in (trace.get("traces") if isinstance(trace, dict) else []) or []
        if isinstance(item, dict) and item.get("figure_path")
    }
    core_figures = core.get("reviewable_figures") if isinstance(core, dict) else []
    core_by_path = {
        str(item.get("path")): item
        for item in core_figures or []
        if isinstance(item, dict) and item.get("path")
    }
    figure_items: list[dict[str, Any]] = []
    for row in rows:
        relative = str(row.get("project_relative_path") or "")
        if _group_for_path(relative) != "figure" or not relative.lower().endswith((".png", ".jpg", ".jpeg")):
            continue
        metadata_item = figure_by_path.get(relative, {})
        core_item = core_by_path.get(relative, {})
        trace_item = trace_by_figure.get(relative, {})
        figure_items.append(
            {
                **row,
                "title_zh": str(core_item.get("caption") or metadata_item.get("figure_id") or Path(relative).name),
                "purpose_zh": "主图证据，请结合图像、caption 和统计合同审阅。",
                "scientific_relevance_zh": str(
                    core_item.get("interpretation_summary")
                    or metadata_item.get("interpretation_summary")
                    or "未登记图表解释。"
                ),
                "caption": str(core_item.get("caption") or metadata_item.get("caption") or ""),
                "interpretation_summary": str(
                    core_item.get("interpretation_summary") or metadata_item.get("interpretation_summary") or ""
                ),
                "code_files": [str(item) for item in trace_item.get("code_files") or []],
                "statistics": trace_item.get("statistics") or {},
                "preview": {"image_path": relative},
            }
        )
    figure_items.sort(key=lambda item: str(item.get("project_relative_path") or ""))

    metric_status = str(metric_identity.get("status") or "")
    strict_primary_record = metric_identity.get("primary_metric", {}).get("record") if isinstance(metric_identity.get("primary_metric"), dict) else None
    strict_primary_record = strict_primary_record if isinstance(strict_primary_record, dict) else None
    strict_primary_ready = metric_status == "passed" and strict_primary_record is not None

    key_findings: list[dict[str, Any]] = []
    if run_id and sample_unit and validation_design:
        key_findings.append(
            {
                "summary_zh": f"选定运行 {run_id} 采用 {validation_design} 设计，样本单位为 {sample_unit}。",
                "source_paths": [metrics_path, summary_path],
            }
        )
    if strict_primary_ready:
        key_findings.append(
            {
                "summary_zh": (
                    f"主结果 {strict_primary_record.get('metric_definition_id')}="
                    f"{_short_float(strict_primary_record.get('value'))}，来自唯一通过 PrimaryMetricContract 的 MetricEvidence。"
                ),
                "source_paths": [
                    str(strict_primary_record.get("source_artifact") or metrics_path),
                    "results/metric_identity_report.json",
                ],
            }
        )
    elif first_metric:
        key_findings.append(
            {
                "summary_zh": "检测到兼容指标文件，但当前没有唯一通过 PrimaryMetricContract 的主结果；其中数值只作待核查记录，不进入确认摘要。",
                "source_paths": [metrics_path, "results/metric_identity_report.json"],
            }
        )
    support_level = str(support.get("support_level") or support.get("decision") or "未登记")
    validity_decision = str(validity.get("decision") or "未登记")
    consistency_checks: list[dict[str, Any]] = []
    raw_metric_values = _metric_values(metrics)
    support_metric_values = _metric_values(support_records)
    if metric_identity:
        strict_primary = metric_identity.get("primary_metric", {}).get("record") if isinstance(metric_identity.get("primary_metric"), dict) else None
        strict_primary = strict_primary if isinstance(strict_primary, dict) else None
        if strict_primary and support_records:
            support_typed = [
                normalize_metric_evidence(
                    item,
                    context=item.get("context") if isinstance(item.get("context"), dict) else {},
                    source_artifact="results/result_support_checkpoint.json",
                    row_index=index,
                )
                for index, item in enumerate(support_records, start=1)
            ]
            matched = [item for item in support_typed if item.get("metric_record_id") == strict_primary.get("metric_record_id")]
            if not matched:
                consistency_checks.append(
                    {
                        "name_zh": "结果支撑指标绑定",
                        "status": "missing_required_identity",
                        "detail_zh": "result_support_checkpoint 登记了指标，但没有绑定当前 PrimaryMetricContract 对应的 MetricEvidence record。",
                        "evidence": "results/result_support_checkpoint.json",
                        "blocking": True,
                    }
                )
            else:
                relation = compare_evidence(strict_primary, matched[0], kind="metric")
                if relation.get("status") == "same_identity_value_conflict":
                    consistency_checks.append(
                        {
                            "name_zh": "指标身份一致性",
                            "status": "fail",
                            "detail_zh": "canonical primary metric 与 result_support_checkpoint 在完整身份相同的情况下数值不同。",
                            "evidence": "results/result_support_checkpoint.json",
                            "blocking": True,
                        }
                    )
        elif strict_primary is None and metric_identity.get("status") == "passed":
            consistency_checks.append(
                {
                    "name_zh": "主指标解析",
                    "status": "missing_required_identity",
                    "detail_zh": "PrimaryMetricContract 没有提供可供 checkpoint 使用的唯一 canonical record。",
                    "evidence": "results/metric_identity_report.json",
                    "blocking": True,
                }
            )
    else:
        for metric_name in sorted(set(raw_metric_values) & set(support_metric_values)):
            raw_value = raw_metric_values[metric_name][0]
            support_value = support_metric_values[metric_name][0]
            if abs(raw_value - support_value) > 1e-9:
                consistency_checks.append(
                    {
                        "name_zh": "指标身份一致性",
                        "status": "fail",
                        "detail_zh": (
                            f"{metric_name} 在 metrics.csv 中为 {_short_float(raw_value)}，"
                            f"在 result_support_checkpoint 中为 {_short_float(support_value)}；"
                            "两者不能在同一主结果中混用。"
                        ),
                        "evidence": "results/tables/metrics.csv",
                        "blocking": True,
                    }
                )
    if binding_run_id and run_id and binding_run_id != run_id:
        consistency_checks.append(
            {
                "name_zh": "运行身份一致性",
                "status": "fail",
                "detail_zh": f"结果运行标识为 {run_id}，数据绑定运行标识为 {binding_run_id}，需要人工确认是否属于同一证据链。",
                "evidence": "data/formal_data_run_binding.json",
                "blocking": True,
            }
        )
    binding_counts = {
        key: _float_value(binding.get(key))
        for key in ("source_rows", "train_sources", "test_sources")
        if _float_value(binding.get(key)) is not None
    }
    count_records = [item for item in count_identity.get("records") or [] if isinstance(item, dict)]
    if not count_records:
        count_definition_map = {
            "source_rows": ("catalog_row_count", "row", "rows"),
            "train_sources": ("train_entity_count", "entity", "split_members"),
            "test_sources": ("test_entity_count", "entity", "split_members"),
        }
        for index, (key, value) in enumerate(binding_counts.items(), start=1):
            definition, entity_type, count_mode = count_definition_map.get(key, (key, "entity", "unknown"))
            count_records.append(
                normalize_count_evidence(
                    {
                        "count_definition_id": definition,
                        "entity_type": entity_type,
                        "count_mode": count_mode,
                        "cohort_id": binding.get("cohort_id") or binding.get("cohort") or "",
                        "filter_contract_id": binding.get("filter_contract_id") or "",
                        "sample_unit": binding.get("sample_unit") or "",
                        "value": value,
                        "evidence_role": "presentation_only",
                    },
                    source_artifact="data/formal_data_run_binding.json",
                    row_index=index,
                )
            )
    if count_records:
        derived_count_identity = build_count_identity_report(count_records)
        if not count_identity:
            count_identity = derived_count_identity
        core_count_status = str(count_identity.get("status") or "legacy_unqualified")
        if core_count_status in {"blocked", "legacy_unqualified"}:
            consistency_checks.append(
                {
                    "name_zh": "样本分母身份完整性",
                    "status": "fail",
                    "detail_zh": (
                        "关键样本数已被拆分为 typed CountEvidence，但当前至少有一个计数缺少完整的实体类型、"
                        "计数方式、cohort 或筛选合同；不能把不同分母写成同一个 source_rows。"
                    ),
                    "evidence": "results/count_identity_report.json" if (root / "results/count_identity_report.json").is_file() else "data/formal_data_run_binding.json",
                    "blocking": True,
                }
            )
    strict_primary_record = strict_primary_record or {}
    if metric_identity and metric_status in {"blocked", "legacy_unqualified"}:
        consistency_checks.append(
            {
                "name_zh": "指标证据身份完整性",
                "status": "fail",
                "detail_zh": (
                    "当前指标尚未由完整 MetricEvidence 和 PrimaryMetricContract 唯一确定；"
                    "兼容 metrics.csv 或未声明聚合只能作为展示，不得直接作为主结果。"
                ),
                "evidence": "results/metric_identity_report.json",
                "blocking": True,
            }
        )
    if trace and str(trace_validation.get("status") or "") != "current":
        consistency_checks.append(
            {
                "name_zh": "图表追踪新鲜度",
                "status": "fail",
                "detail_zh": "图表代码追踪缺少当前图像、metadata、代码、输入或运行事务的完整绑定；只能作为历史预览。",
                "evidence": "results/figure_code_trace.json",
                "blocking": True,
            }
        )
    if metric_identity and metric_status == "passed" and active_bundle.get("status") != "active":
        consistency_checks.append(
            {
                "name_zh": "运行证据包完整性",
                "status": "fail",
                "detail_zh": "指标身份已经通过，但当前没有可校验的 active RunEvidenceBundle；不能把分散文件拼成一次运行。",
                "evidence": "results/active_run_evidence_bundle.json",
                "blocking": True,
            }
        )
    seen_trace_conflicts: set[tuple[str, float, float]] = set()
    for trace_item in trace.get("traces") or [] if isinstance(trace, dict) else []:
        statistics = trace_item.get("statistics") if isinstance(trace_item, dict) else {}
        if not isinstance(statistics, dict):
            statistics = {}
        trace_schema = str(trace_item.get("schema_version") or trace.get("schema_version") or "")
        trace_status = str(trace_item.get("trace_status") or "")
        if trace_schema == "dpl.figure_code_trace.v2":
            if trace_status != "current":
                consistency_checks.append(
                    {
                        "name_zh": "图表追踪新鲜度",
                        "status": "fail",
                        "detail_zh": "FigureCodeTrace v2 未处于 current 状态，图像、代码、输入或运行事务已经过期。",
                        "evidence": "results/figure_code_trace.json",
                        "blocking": True,
                    }
                )
            if not trace_item.get("count_record_refs"):
                consistency_checks.append(
                    {
                        "name_zh": "图表分母绑定",
                        "status": "fail",
                        "detail_zh": "FigureCodeTrace v2 没有引用 CountEvidence，图表中的分母不能进入确认证据。",
                        "evidence": "results/figure_code_trace.json",
                        "blocking": True,
                    }
                )
        for key, binding_value in binding_counts.items():
            trace_value = _float_value(statistics.get(key))
            if trace_value is not None and trace_value != binding_value:
                conflict_key = (key, trace_value, binding_value)
                if conflict_key in seen_trace_conflicts:
                    continue
                seen_trace_conflicts.add(conflict_key)
                consistency_checks.append(
                    {
                        "name_zh": "图表统计身份一致性",
                        "status": "different_identity_non_comparable",
                        "detail_zh": (
                            f"图表追踪中的 {key}={_short_float(trace_value)} 与当前数据绑定的 {_short_float(binding_value)} "
                            "属于不同或未声明的分母口径，不能直接判定为同一计数；旧 trace 在完成 typed count 绑定前不能确认。"
                        ),
                        "evidence": "results/figure_code_trace.json",
                        "blocking": True,
                    }
                )
                break
    key_findings.append(
        {
            "summary_zh": f"结果有效性判定为 {validity_decision}，论断支撑判定为 {support_level}。",
            "source_paths": ["results/result_validity_report.json", "results/result_support_checkpoint.json"],
        }
    )
    boundaries = []
    for claim in support.get("claim_assessments") or []:
        if isinstance(claim, dict) and claim.get("claim_boundary"):
            boundaries.append(str(claim["claim_boundary"]))
    if not boundaries:
        boundaries.append("只能在已验证的数据、方法、验证设计、图表证据和样本单位范围内解释结果。")
    boundaries = _unique(boundaries)[:5]

    validation_summary = [
        {
            "name_zh": "核心证据报告",
            "status": str(core.get("decision") or core.get("status") or "unknown"),
            "detail_zh": "核心图表、结果有效性和结果支撑已登记。",
            "evidence": "core_evidence/core_evidence_report.json",
            "blocking": False,
        },
        {
            "name_zh": "结果有效性",
            "status": validity_decision,
            "detail_zh": str(validity.get("issues") or "未登记额外问题。"),
            "evidence": "results/result_validity_report.json",
            "blocking": validity_decision not in {"pass", "passed", "conditional_pass"},
        },
        {
            "name_zh": "论断支撑",
            "status": support_level,
            "detail_zh": "结果支撑状态来自项目的 result support checkpoint。",
            "evidence": "results/result_support_checkpoint.json",
            "blocking": support_level not in {"supported", "pass", "passed"},
        },
        {
            "name_zh": "图表与代码追踪",
            "status": "pass" if trace_by_figure else "missing",
            "detail_zh": f"已登记 {len(trace_by_figure)} 个图表的代码追踪记录。",
            "evidence": "results/figure_code_trace.json",
            "blocking": bool(figure_items) and not trace_by_figure,
        },
    ]
    if metric_identity:
        validation_summary.append(
            {
                "name_zh": "MetricEvidence 身份与主指标合同",
                "status": "pass" if metric_status == "passed" else "blocked",
                "detail_zh": "指标先经过身份和主指标合同解析，再进入结果摘要。" if metric_status == "passed" else "指标身份或主指标合同未达到严格确认条件。",
                "evidence": "results/metric_identity_report.json",
                "blocking": metric_status != "passed",
            }
        )
    if count_identity or count_records:
        count_status = str(count_identity.get("status") or "legacy_unqualified")
        validation_summary.append(
            {
                "name_zh": "CountEvidence 分母与 sample-flow",
                "status": "pass" if count_status == "passed" else "blocked",
                "detail_zh": "样本数带有实体、计数方式、cohort 和筛选合同。" if count_status == "passed" else "样本数仍存在未声明或不完整的分母身份。",
                "evidence": "results/count_identity_report.json" if (root / "results/count_identity_report.json").is_file() else "data/formal_data_run_binding.json",
                "blocking": count_status != "passed",
            }
        )
    return {
        "figure_items": figure_items,
        "key_findings": key_findings[:_MAX_SUMMARY_ITEMS],
        "claim_boundaries": [{"summary_zh": value} for value in boundaries],
        "validation_summary": validation_summary,
        "consistency_checks": consistency_checks,
        "core_metrics": {
            "run_id": run_id,
            "sample_unit": strict_primary_record.get("sample_unit") or sample_unit,
            "validation_design": strict_primary_record.get("validation_design_id") or validation_design,
            "metric": strict_primary_record.get("metric_definition_id"),
            "value": strict_primary_record.get("value"),
            "legacy_counts": {
                "source_rows": first_analysis.get("source_rows") or binding.get("source_rows"),
                "train_sources": first_analysis.get("train_sources") or binding.get("train_sources"),
                "test_sources": first_analysis.get("test_sources") or binding.get("test_sources"),
                "evidence_role": "presentation_only",
            },
            "metric_source": strict_primary_record.get("source_artifact") if strict_primary_ready else "",
            "consistency_issue_count": len(consistency_checks),
            "metric_identity_status": metric_status or None,
            "metric_identity_report_path": "results/metric_identity_report.json" if metric_identity else None,
            "metric_definition_id": strict_primary_record.get("metric_definition_id"),
            "task_id": strict_primary_record.get("task_id"),
            "cohort_id": strict_primary_record.get("cohort_id") or binding.get("cohort_id") or binding.get("cohort"),
            "model_id": strict_primary_record.get("model_id"),
            "split_id": strict_primary_record.get("split_id"),
            "aggregation_id": strict_primary_record.get("aggregation_id"),
            "count_identity_status": str(count_identity.get("status") or "") or None,
            "count_identity_report_path": "results/count_identity_report.json" if (root / "results/count_identity_report.json").is_file() else None,
            "count_evidence": count_records,
            "sample_flow": count_records,
            "active_run_evidence_bundle_status": active_bundle.get("status"),
            "active_run_evidence_bundle_path": active_bundle.get("bundle", {}).get("bundle_path") if isinstance(active_bundle.get("bundle"), dict) else None,
        },
        "promoted_evidence_snapshot_id": core.get("promoted_evidence_snapshot_id")
        or (_read_json(root, "results/promoted_evidence_snapshot.json") or {}).get("snapshot_id"),
    }


def _result_support_digest(root: Path) -> dict[str, Any]:
    """Summarize the route-selection checkpoint from its authoritative report."""

    report = _read_json(root, "results/result_support_checkpoint.json") or {}
    validity = _read_json(root, "results/result_validity_report.json") or {}
    decision = str(report.get("decision") or "未登记")
    support_level = str(report.get("support_level") or "未登记")
    selected_route = str(report.get("selected_route") or "")
    claims = [item for item in report.get("claim_assessments") or [] if isinstance(item, dict)]
    failed_claims = [item for item in report.get("failed_claims") or [] if isinstance(item, dict)]
    routes = [item for item in report.get("route_options") or [] if isinstance(item, dict)]
    route_pending = bool(routes) and not selected_route and bool(
        report.get("requires_user_decision") or decision == "route_decision_required"
    )
    rescue = _read_json(root, "review/result_rescue_plan.json") or {}
    rescue_commands = [str(item) for item in rescue.get("recommended_next_commands") or [] if item]
    contexts = [
        item.get("context")
        for item in report.get("metric_records") or []
        if isinstance(item, dict) and isinstance(item.get("context"), dict)
    ]
    context = next((item for item in contexts if item), {})
    metrics = report.get("metrics") if isinstance(report.get("metrics"), dict) else {}
    preferred_metrics = (
        ("primary_f1", "F1"),
        ("macro_f1_primary_model", "macro-F1"),
        ("balanced_accuracy_primary_model", "balanced accuracy"),
        ("roc_auc_primary_model", "ROC-AUC"),
    )
    metric_fragments = [
        f"{label}={_short_float(metrics[key])}"
        for key, label in preferred_metrics
        if metrics.get(key) is not None
    ]
    key_findings = [
        {
            "summary_zh": f"当前结果支撑判定为 {decision}，支撑级别为 {support_level}。",
            "source_paths": ["results/result_support_checkpoint.json"],
        },
        {
            "summary_zh": f"结构化论断评估共登记 {len(claims)} 条，其中 {len(failed_claims)} 条未完全获得当前证据支持。",
            "source_paths": ["results/result_support_checkpoint.json"],
        },
    ]
    if metric_fragments:
        key_findings.append(
            {
                "summary_zh": "当前结果报告登记的主要指标为 " + "、".join(metric_fragments) + "；这些数值仍受当前证据路线选择约束。",
                "source_paths": ["results/result_support_checkpoint.json"],
            }
        )
    if route_pending:
        key_findings.append(
            {
                "summary_zh": "需要用户在“收窄研究论断”和“补充数据/方法证据”两条原子路线中选择一条；当前版本不允许混合执行。",
                "source_paths": ["results/result_support_checkpoint.json"],
            }
        )
    elif selected_route:
        selected_label = next(
            (str(item.get("label") or item.get("route")) for item in routes if str(item.get("route") or "") == selected_route),
            selected_route,
        )
        key_findings.append(
            {
                "summary_zh": f"用户已选择“{selected_label}”；当前页面展示该路线的影响范围和待执行任务，不再要求重复选择。",
                "source_paths": ["results/result_support_checkpoint.json", "review/result_rescue_plan.json"],
            }
        )
    unresolved: list[dict[str, Any]] = []
    if route_pending:
        unresolved.append(
            {
                "summary_zh": "当前结果尚不能直接进入下游稿件流程，必须先完成结果路线选择。",
                "blocking": True,
                "source": "results/result_support_checkpoint.json",
            }
        )
    elif selected_route:
        unresolved.append(
            {
                "summary_zh": "结果路线已经选择，但补充路线的任务尚未完成；完成数据、方法和结果支撑重建前不能继续下游稿件流程。",
                "blocking": True,
                "source": "review/result_rescue_plan.json",
            }
        )
    consistency_checks = [
        {
            "name_zh": "结果支撑路线选择",
            "status": "fail" if route_pending else "pass",
            "detail_zh": (
                "当前结果支撑不足以自动保持原研究论断；请从下方两条路线中选择一条。"
                if route_pending
                else "路线已经选择，当前摘要仅展示该路线的待执行影响范围。"
                if selected_route
                else "结果支撑报告未要求额外路线选择。"
            ),
            "evidence": "results/result_support_checkpoint.json",
            "blocking": route_pending,
        },
    ]
    validation_summary = [
        {
            "name_zh": "结果有效性",
            "status": str(validity.get("decision") or "未登记"),
            "detail_zh": str(validity.get("issues") or "结果有效性报告已登记。"),
            "evidence": "results/result_validity_report.json",
            "blocking": str(validity.get("decision") or "") not in {"pass", "passed", "conditional_pass"},
        },
        {
            "name_zh": "论断支撑",
            "status": support_level,
            "detail_zh": f"当前结果支撑报告评估了 {len(claims)} 条结构化论断。",
            "evidence": "results/result_support_checkpoint.json",
            "blocking": support_level not in {"supported", "pass", "passed"},
        },
    ]
    narrative = (
        f"本阶段围绕结果支撑与论断路线选择，读取当前结果有效性报告和结果支撑报告，"
        f"审查了 {len(claims)} 条结构化论断及其指标证据；当前判定为 {decision}，"
        f"形成了 {len(routes)} 条可执行路线和对应的影响范围。"
    )
    if route_pending:
        narrative += "在用户选择路线前，本阶段不能冻结为可消费的科学证据，也不能继续下游稿件写作。"
    elif selected_route:
        narrative += "用户路线已经冻结为当前选项，但必须完成该路线的上游任务后才能继续下游稿件写作。"
    else:
        narrative += "当前报告未登记需要额外路线选择的阻断项。"
    boundary_text = (
        "在补充或收窄路线完成前，不将当前指标扩展为已确认的研究结论。"
        if selected_route
        else "在路线选择完成前，不将当前指标扩展为已确认的研究结论。"
    )
    return {
        "figure_items": [],
        "stage_narrative_zh": narrative,
        "key_findings": key_findings,
        "claim_boundaries": [
            {"summary_zh": boundary_text},
            {"summary_zh": "一次人工决策只选择一条路线；补充路线和收窄路线不能在同一 checkpoint 中混合执行。"},
        ],
        "validation_summary": validation_summary,
        "consistency_checks": consistency_checks,
        "unresolved": unresolved,
        "decision_routes": routes if route_pending else [],
        "decision_route_state": {
            "status": "required" if route_pending else "selected" if selected_route else "none",
            "selected_route": selected_route or None,
            "selected_label": next(
                (str(item.get("label") or item.get("route")) for item in routes if str(item.get("route") or "") == selected_route),
                selected_route or None,
            ),
            "next_commands": rescue_commands,
        },
        "core_metrics": {
            "run_id": str(context.get("run_id") or ""),
            "sample_unit": str(context.get("sample_unit") or ""),
            "validation_design": str(context.get("validation_design") or ""),
            "metric": "primary_f1" if metrics.get("primary_f1") is not None else "",
            "value": metrics.get("primary_f1"),
            "metric_source": "results/result_support_checkpoint.json" if metrics else "",
            "consistency_issue_count": len(consistency_checks),
        },
        "promoted_evidence_snapshot_id": str(report.get("evidence_snapshot_id") or "") or None,
        "requires_user_decision": bool(report.get("requires_user_decision")),
    }


def _enrich_artifact(root: Path, item: dict[str, Any], stage: str) -> dict[str, Any]:
    relative = str(item.get("project_relative_path") or item.get("path") or "").replace("\\", "/")
    group = _group_for_path(relative)
    preview = _load_csv_preview(root, relative)
    purpose_by_group = {
        "figure": "主图或图像证据，请结合预览、caption、解释和来源代码审阅。",
        "table": "结构化数据或结果表，页面仅显示受限预览；请打开原文件检查完整列和单位。",
        "prose": "本阶段文字或报告产物，请检查内容、来源和上游失效范围。",
        "code": "本阶段分析或绘图代码，请检查入口、输入输出和代码 hash。",
        "run_evidence": "运行或证据身份记录，请检查 run、cohort、plan hash 和执行状态。",
        "review_report": "结构化审查报告，请检查状态、阻断项和引用的证据路径。",
        "manifest": "技术清单或身份附件，请结合其来源和 hash 审阅。",
    }
    purpose = purpose_by_group.get(group, "本阶段确认范围内的产物。")
    enriched = {
        **item,
        "project_relative_path": relative,
        "artifact_role": item.get("artifact_role") or stage,
        "deliverable_group": group,
        "title_zh": _title_for_path(relative, group),
        "purpose_zh": purpose,
        "scientific_relevance_zh": purpose,
        "review_priority": "technical" if group in {"manifest", "run_evidence"} else "recommended",
        "preview": preview or {},
        "exists": bool(item.get("after_byte_sha256") or (root / relative).is_file()),
    }
    if group == "figure" and Path(relative).suffix.lower() in {".png", ".jpg", ".jpeg"}:
        context = _figure_context(root, relative)
        enriched.update(
            {
                "title_zh": context["title_zh"],
                "caption": context["caption"],
                "interpretation_summary": context["interpretation_summary"],
                "scientific_relevance_zh": context["interpretation_summary"] or enriched["scientific_relevance_zh"],
                "code_files": context["code_files"],
                "statistics": context["statistics"],
                "preview": context["preview"],
            }
        )
    return enriched


def _build_groups(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        grouped.setdefault(str(item.get("deliverable_group") or "manifest"), []).append(item)
    order = ("figure", "table", "prose", "code", "run_evidence", "review_report", "manifest")
    return [
        {
            "group_id": group,
            "title_zh": _group_title(group),
            "count": len(grouped.get(group, [])),
            "items": sorted(grouped.get(group, []), key=lambda item: str(item.get("project_relative_path") or "")),
        }
        for group in order
        if grouped.get(group)
    ]


def build_stage_digest(
    root: Path,
    *,
    stage: str,
    command: str,
    payload: dict[str, Any],
    artifact_manifest: dict[str, Any],
    checkpoint_hash: str | None = None,
    preview_only: bool = False,
) -> dict[str, Any]:
    """Build v2 content fields from canonical project-local evidence."""

    manifest_rows = [item for item in artifact_manifest.get("artifacts") or [] if isinstance(item, dict)]
    deliverables = [_enrich_artifact(root, item, stage) for item in manifest_rows]
    if stage == "core_evidence":
        core = _core_evidence_digest(root, deliverables)
    elif stage == "result_support":
        core = _result_support_digest(root)
    else:
        core = _generic_stage_digest(root, stage, deliverables, payload)
    figure_map = {str(item.get("project_relative_path")): item for item in core["figure_items"]}
    for item in deliverables:
        replacement = figure_map.get(str(item.get("project_relative_path")))
        if replacement:
            item.update(replacement)
        if item.get("deliverable_group") == "table" and not item.get("preview"):
            item["preview"] = _load_csv_preview(root, str(item.get("project_relative_path"))) or {}
    groups = _build_groups(deliverables)
    changes: dict[str, list[dict[str, Any]]] = {"generated": [], "modified": [], "deployed": [], "unchanged": [], "failed": []}
    for item in deliverables:
        operation = str(item.get("operation") or "unchanged")
        changes.setdefault(operation, []).append(item)

    drift = detect_artifact_drift(root)
    consistency: list[dict[str, Any]] = []
    consistency.extend(core.get("consistency_checks") or [])
    unresolved: list[dict[str, Any]] = [
        item for item in core.get("unresolved") or [] if isinstance(item, dict)
    ]
    missing_deliverables = [
        item for item in deliverables if not item.get("exists", True)
    ]
    if missing_deliverables:
        missing_paths = ", ".join(
            str(item.get("project_relative_path") or "")
            for item in missing_deliverables[:8]
        )
        if len(missing_deliverables) > 8:
            missing_paths += f" 等 {len(missing_deliverables)} 项"
        consistency.append(
            {
                "name_zh": "阶段产物完整性",
                "status": "fail",
                "detail_zh": f"阶段产物缺失或无法读取：{missing_paths}。",
                "evidence": missing_deliverables[0].get("project_relative_path"),
                "blocking": True,
            }
        )
    if drift.get("status") == "drift_detected":
        changed = drift.get("changed_artifacts") or []
        consistency.append(
            {
                "name_zh": "上游 artifact 漂移",
                "status": "fail",
                "detail_zh": f"检测到 {len(changed)} 个 artifact hash 变化，当前 checkpoint 不能用于确认。",
                "evidence": "project_passport.yaml",
                "blocking": True,
            }
        )
    else:
        consistency.append(
            {
                "name_zh": "上游 artifact 漂移",
                "status": "pass",
                "detail_zh": "当前项目 artifact 与 passport 快照一致。",
                "evidence": "project_passport.yaml",
                "blocking": False,
            }
        )
    for item in core.get("validation_summary") or []:
        if item.get("status") == "missing" or item.get("blocking"):
            consistency.append(
                {
                    "name_zh": f"验证来源：{item.get('name_zh')}",
                    "status": "fail",
                    "detail_zh": str(item.get("detail_zh") or "验证来源缺失。"),
                    "evidence": item.get("evidence"),
                    "blocking": True,
                }
            )

    blocking = [item for item in consistency if item.get("blocking")]
    status = str(payload.get("status") or payload.get("decision") or "completed").lower()
    if preview_only:
        review_state = "preview_only"
    elif blocking:
        review_state = "stale" if any(item.get("name_zh") == "上游 artifact 漂移" for item in blocking) else "blocked"
    elif status in {"error", "failed", "blocked", "failure"}:
        review_state = "blocked"
    else:
        review_state = "confirmable"

    metrics = core.get("core_metrics") or {}
    if stage == "core_evidence" and metrics.get("run_id"):
        inventory = _deliverable_inventory_text(deliverables)
        narrative = (
            f"本阶段围绕关键结果与论断支撑确认，基于运行 {metrics['run_id']} 的 "
            f"{metrics.get('validation_design') or '已登记验证设计'} 结果，整理了 "
            f"{len(core.get('figure_items') or [])} 组主图、{sum(1 for item in deliverables if item.get('deliverable_group') == 'table')} 项表格、"
            f"{sum(1 for item in deliverables if item.get('deliverable_group') == 'code')} 项分析或绘图代码和配套证据报告。"
        )
        if inventory:
            narrative += f"具体产物包括{inventory}。"
        metric_conflict = any(item.get("name_zh") == "指标身份一致性" for item in consistency)
        if metrics.get("metric") and metrics.get("value") is not None:
            if metric_conflict or metrics.get("metric_identity_status") not in {None, "", "passed"}:
                narrative += (
                    f"兼容结果文件当前登记 {metrics['metric']}={_short_float(metrics['value'])}，"
                    "但该数值缺少或未通过完整指标身份合同，因此仅作待核对记录，不作为已确认主结果。"
                )
            else:
                narrative += f"主指标 {metrics['metric']}={_short_float(metrics['value'])}，样本单位为 {metrics.get('sample_unit') or '未登记'}。"
        if metrics.get("sample_flow"):
            narrative += f"当前样本流程登记了 {len(metrics['sample_flow'])} 个 typed count 节点，页面按实体类型和计数方式分别展示。"
        elif metrics.get("legacy_counts"):
            narrative += "检测到旧版或兼容分母字段，但这些字段仅作 presentation_only 诊断，不作为样本流程或主论断分母。"
        narrative += "页面只支持在当前数据、方法、验证设计和证据边界内解释结果。"
        if review_state != "confirmable":
            narrative += "由于当前存在证据一致性问题，本页面暂不可用于哈希确认。"
    elif stage == "result_support" and core.get("stage_narrative_zh"):
        narrative = str(core["stage_narrative_zh"])
        if review_state != "confirmable" and "不能" not in narrative:
            narrative += "当前摘要存在阻断问题，不能直接确认。"
    elif core.get("stage_narrative_zh"):
        narrative = str(core["stage_narrative_zh"])
        if review_state != "confirmable" and "不能" not in narrative:
            narrative += "当前摘要存在阻断问题，不能直接确认。"
    else:
        purpose = STAGE_PURPOSES.get(stage, f"{stage} 阶段")
        narrative = f"本阶段围绕{purpose}形成了 {len(deliverables)} 项确认范围内成果，并记录了当前验证状态和后续路线。"
        if review_state != "confirmable":
            narrative += "当前摘要存在阻断问题，不能直接确认。"

    inspection_targets: list[dict[str, Any]] = []
    priority_order = ("figure", "table", "prose", "code", "run_evidence", "review_report")
    preferred = [item for group in priority_order for item in deliverables if item.get("deliverable_group") == group]
    for item in preferred:
        relative = str(item.get("project_relative_path") or "")
        if not relative or any(target.get("project_relative_path") == relative for target in inspection_targets):
            continue
        inspection_targets.append(
            {
                "project_relative_path": relative,
                "purpose_zh": str(item.get("purpose_zh") or item.get("scientific_relevance_zh") or "请优先检查。"),
                "review_priority": "required" if item.get("deliverable_group") in {"figure", "table", "prose"} else "recommended",
                "exists": str(bool(item.get("exists"))).lower(),
            }
        )
        if len(inspection_targets) >= 5:
            break
    if not inspection_targets:
        for item in deliverables:
            relative = str(item.get("project_relative_path") or "")
            if not relative:
                continue
            inspection_targets.append(
                {
                    "project_relative_path": relative,
                    "purpose_zh": str(item.get("purpose_zh") or "请优先检查。"),
                    "review_priority": "recommended",
                    "exists": str(bool(item.get("exists"))).lower(),
                }
            )
            if len(inspection_targets) >= 5:
                break

    for item in blocking:
        issue = {
            "summary_zh": str(item.get("detail_zh") or item.get("name_zh") or "存在阻断问题。"),
            "blocking": True,
            "source": item.get("evidence"),
        }
        if not any(existing.get("summary_zh") == issue["summary_zh"] for existing in unresolved):
            unresolved.append(issue)
    core_identity = core.get("identity") or {}
    identity = {
        "plan_hash": payload.get("confirmed_plan_hash")
        or core_identity.get("plan_hash")
        or (_read_json(root, "results/figure_plan.json") or {}).get("confirmed_plan_hash"),
        "run_id": metrics.get("run_id"),
        "cohort_id": metrics.get("cohort_id") or metrics.get("cohort") or core_identity.get("cohort_id"),
        "cohort_label": metrics.get("validation_design"),
        "sample_unit": metrics.get("sample_unit") or core_identity.get("sample_unit"),
        "evidence_snapshot_id": core.get("promoted_evidence_snapshot_id") or core_identity.get("evidence_snapshot_id"),
        "checkpoint_hash": checkpoint_hash,
    }
    return {
        "review_state": review_state,
        "stage_purpose_zh": STAGE_PURPOSES.get(stage, f"{stage} 阶段人工确认。"),
        "stage_narrative_zh": narrative,
        "key_findings": core.get("key_findings") or [],
        "claim_boundaries": core.get("claim_boundaries") or [],
        "stage_deliverables": deliverables,
        "transaction_changes": changes,
        "deliverable_groups": groups,
        "validation_summary": core.get("validation_summary") or [],
        "consistency_checks": consistency,
        "inspection_targets": inspection_targets,
        "identity": identity,
        "unresolved": unresolved,
        "decision_routes": core.get("decision_routes") or [],
        "decision_route_state": core.get("decision_route_state") or {},
        "core_metrics": metrics,
        "deliverable_counts": {group["group_id"]: group["count"] for group in groups},
    }
