"""Build the small, evidence-bound decision brief shown at human checkpoints.

The checkpoint package still retains complete technical evidence, but the page a
researcher is asked to approve must answer a different question: what scientific
decision is being made, what facts support it, and what remains outside scope.
This module deliberately consumes structured checkpoint facts rather than
directory listings or free-form Agent prose.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from typing import Any

from .artifact_identity import canonical_json


HUMAN_DECISION_BRIEF_SCHEMA = "dpl.human_decision_brief.v1"

_IDENTITY_LABELS = {
    "plan_hash": "研究蓝图身份",
    "run_id": "运行身份",
    "cohort_id": "队列身份",
    "cohort_label": "队列说明",
    "sample_unit": "样本单位",
    "evidence_snapshot_id": "证据快照",
}

_METRIC_LABELS = {
    "metric": "主指标定义",
    "metric_definition_id": "指标定义身份",
    "value": "主指标数值",
    "validation_design": "验证设计",
    "split_id": "划分身份",
    "model_id": "模型身份",
    "aggregation_id": "聚合口径",
    "uncertainty": "不确定性口径",
}


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _source_refs(item: Any, *, fallback: str | None = None) -> list[str]:
    """Return deterministic evidence refs without treating a path as a claim."""

    refs: list[str] = []
    if isinstance(item, dict):
        for key in ("source_paths", "evidence_refs", "sources"):
            values = item.get(key)
            if isinstance(values, str):
                values = [values]
            if isinstance(values, Iterable):
                refs.extend(f"artifact:{_text(value)}" for value in values if _text(value))
        for key in ("source", "evidence", "metric_source", "project_relative_path"):
            value = _text(item.get(key))
            if value:
                refs.append(f"artifact:{value}")
    if fallback:
        refs.append(f"artifact:{fallback}")
    return sorted(set(refs))


def _human_text(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return canonical_json(value)
    return _text(value)


def _statement(
    statement_id: str,
    text_zh: str,
    *,
    fact_refs: Iterable[str] = (),
    evidence_refs: Iterable[str] = (),
    claim_refs: Iterable[str] = (),
    semantic_key: Any | None = None,
    text_en: str | None = None,
) -> dict[str, Any]:
    fact_ids = sorted({_text(value) for value in fact_refs if _text(value)})
    evidence = sorted({_text(value) for value in evidence_refs if _text(value)})
    claims = sorted({_text(value) for value in claim_refs if _text(value)})
    return {
        "statement_id": statement_id,
        "text_zh": _text(text_zh),
        "text_en": _text(text_en) if text_en else None,
        "fact_refs": fact_ids,
        "evidence_refs": evidence,
        "claim_refs": claims,
        "semantic_key": semantic_key if semantic_key is not None else {"text_zh": _text(text_zh), "fact_refs": fact_ids, "evidence_refs": evidence, "claim_refs": claims},
    }


def _figure_rows(summary: dict[str, Any]) -> list[dict[str, Any]]:
    rows = summary.get("stage_deliverables") or []
    figures = [item for item in rows if isinstance(item, dict) and str(item.get("deliverable_group") or "") == "figure"]
    return sorted(figures, key=lambda item: _text(item.get("project_relative_path")))[:8]


def _value_sentence(label: str, value: Any) -> str:
    rendered = _human_text(value)
    return f"{label}：{rendered}。" if rendered else ""


def _semantic_identity(identity: dict[str, Any], metric: dict[str, Any]) -> dict[str, Any]:
    """Keep only scientific identity in the Brief's semantic subject.

    A checkpoint may be rebuilt on another machine or with a regenerated
    report.  Paths, report locators, and presentation text remain in the
    readable Brief, but cannot decide whether the author must reconfirm the
    science.
    """

    return {
        "plan_hash": identity.get("plan_hash"),
        "run_id": identity.get("run_id") or metric.get("run_id"),
        "cohort_id": identity.get("cohort_id") or metric.get("cohort_id"),
        "sample_unit": identity.get("sample_unit") or metric.get("sample_unit"),
        "validation_design": identity.get("cohort_label") or metric.get("validation_design"),
        "evidence_snapshot_id": identity.get("evidence_snapshot_id"),
        "metric": metric.get("metric"),
        "metric_definition_id": metric.get("metric_definition_id"),
        "value": metric.get("value"),
        "uncertainty": metric.get("uncertainty"),
        "split_id": metric.get("split_id"),
        "model_id": metric.get("model_id"),
        "aggregation_id": metric.get("aggregation_id"),
    }


def _semantic_sort(values: Iterable[Any]) -> list[Any]:
    """Canonicalize list order without changing the user-facing display order."""

    return sorted(values, key=canonical_json)


def build_human_decision_brief(summary: dict[str, Any], *, locale: str = "zh-CN") -> dict[str, Any]:
    """Create a bounded decision brief from an already-built checkpoint summary.

    The brief is intentionally conservative.  It only repeats structured facts
    already bound by the summary and labels unavailable facts as unavailable;
    it never fills scientific gaps from filenames or model-generated prose.
    """

    stage = _text(summary.get("checkpoint_type") or summary.get("completed_stage"))
    purpose = _text(summary.get("stage_purpose_zh")) or f"{stage} 阶段确认"
    facts: list[dict[str, Any]] = []
    used_ids: set[str] = set()

    def add_fact(kind: str, label_zh: str, value: Any, evidence_refs: Iterable[str], *, semantic_value: Any | None = None) -> str | None:
        if value in (None, "", [], {}):
            return None
        base = f"{kind}-{len(facts) + 1}"
        fact_id = base
        suffix = 2
        while fact_id in used_ids:
            fact_id = f"{base}-{suffix}"
            suffix += 1
        used_ids.add(fact_id)
        refs = sorted({_text(ref) for ref in evidence_refs if _text(ref)}) or [f"policy:checkpoint:{stage}"]
        facts.append(
            {
                "fact_id": fact_id,
                "fact_type": kind,
                "label_zh": label_zh,
                "value": value,
                "evidence_refs": refs,
                "semantic_value": value if semantic_value is None else semantic_value,
            }
        )
        return fact_id

    scope_fact = add_fact("scope", "本次决定范围", purpose, [f"policy:checkpoint:{stage}"])
    identity = summary.get("identity") if isinstance(summary.get("identity"), dict) else {}
    metric = summary.get("core_metrics") if isinstance(summary.get("core_metrics"), dict) else {}
    identity_facts: list[str] = []
    for key, label in _IDENTITY_LABELS.items():
        ref = metric.get("metric_source") or identity.get("evidence_snapshot_id") or f"policy:checkpoint:{stage}"
        fact_id = add_fact("identity", label, identity.get(key), [str(ref)])
        if fact_id:
            identity_facts.append(fact_id)
    metric_facts: list[str] = []
    for key, label in _METRIC_LABELS.items():
        value = metric.get(key)
        if value in (None, "") and key == "validation_design":
            value = identity.get("cohort_label")
        ref = metric.get("metric_source") or metric.get("metric_identity_report_path") or f"policy:checkpoint:{stage}"
        fact_id = add_fact("metric", label, value, [str(ref)])
        if fact_id:
            metric_facts.append(fact_id)

    count_facts: list[str] = []
    for index, row in enumerate(metric.get("sample_flow") or summary.get("sample_flow") or []):
        if not isinstance(row, dict):
            continue
        value = row.get("value")
        label = _text(row.get("count_definition_id") or row.get("label") or row.get("entity_type")) or f"样本流程节点 {index + 1}"
        fact_id = add_fact(
            "count",
            label,
            {
                "value": value,
                "entity_type": row.get("entity_type"),
                "count_mode": row.get("count_mode"),
                "cohort_id": row.get("cohort_id"),
                "filter_contract_id": row.get("filter_contract_id"),
            },
            _source_refs(row, fallback=metric.get("count_identity_report_path")),
        )
        if fact_id:
            count_facts.append(fact_id)

    findings: list[dict[str, Any]] = []
    finding_facts: list[str] = []
    for index, item in enumerate(summary.get("key_findings") or []):
        text = _text(item.get("summary_zh") if isinstance(item, dict) else item)
        if not text:
            continue
        fact_id = add_fact("finding", f"关键发现 {index + 1}", text, _source_refs(item, fallback=metric.get("metric_source")))
        if fact_id:
            finding_facts.append(fact_id)
            findings.append(
                _statement(
                    f"finding-{index + 1}",
                    text,
                    fact_refs=[fact_id],
                    evidence_refs=_source_refs(item),
                    semantic_key={"finding": text},
                    text_en=_text(item.get("summary_en")) if isinstance(item, dict) else None,
                )
            )

    boundary_facts: list[str] = []
    boundaries: list[dict[str, Any]] = []
    for index, item in enumerate(summary.get("claim_boundaries") or []):
        text = _text(item.get("summary_zh") if isinstance(item, dict) else item)
        if not text:
            continue
        fact_id = add_fact("claim_boundary", f"论断边界 {index + 1}", text, _source_refs(item, fallback="core_evidence/core_evidence_report.json" if stage == "core_evidence" else None))
        if fact_id:
            boundary_facts.append(fact_id)
            boundaries.append(
                _statement(
                    f"boundary-{index + 1}",
                    text,
                    fact_refs=[fact_id],
                    evidence_refs=_source_refs(item),
                    semantic_key={"claim_boundary": text},
                    text_en=_text(item.get("summary_en")) if isinstance(item, dict) else None,
                )
            )

    figure_claims: list[dict[str, Any]] = []
    figure_facts: list[str] = []
    for index, figure in enumerate(_figure_rows(summary)):
        path = _text(figure.get("project_relative_path"))
        text = _text(figure.get("interpretation_summary") or figure.get("caption") or figure.get("scientific_relevance_zh"))
        value = {
            "path": path,
            "figure_id": figure.get("title_zh") or figure.get("figure_id"),
            "semantic_sha256": figure.get("after_semantic_sha256") or figure.get("evidence_sha256"),
            "interpretation": text,
        }
        fact_id = add_fact(
            "figure",
            _text(value["figure_id"]) or f"图 {index + 1}",
            value,
            _source_refs(figure, fallback=path),
            semantic_value={
                "figure_id": _text(value["figure_id"]) or f"figure-{index + 1}",
                "semantic_sha256": value["semantic_sha256"],
            },
        )
        if fact_id:
            figure_facts.append(fact_id)
            statement_text = f"{_text(value['figure_id']) or f'图 {index + 1}'}：{text or '已登记为本次确认范围内的图表证据。'}"
            figure_claims.append(
                {
                    "figure_id": _text(value["figure_id"]) or f"figure-{index + 1}",
                    "project_relative_path": path,
                    "statement": _statement(
                        f"figure-{index + 1}",
                        statement_text,
                        fact_refs=[fact_id],
                        evidence_refs=_source_refs(figure, fallback=path),
                        semantic_key={
                            "figure_id": _text(value["figure_id"]) or f"figure-{index + 1}",
                            "semantic_sha256": value["semantic_sha256"],
                        },
                        text_en=_text(figure.get("interpretation_summary_en") or figure.get("caption_en")),
                    ),
                }
            )

    confirming: list[dict[str, Any]] = [
        _statement(
            "decision-scope",
            f"本次需要确认的是：{purpose}",
            fact_refs=[scope_fact] if scope_fact else [],
            evidence_refs=[f"policy:checkpoint:{stage}"],
            semantic_key={"stage": stage},
            text_en=f"This checkpoint confirms the scientific basis and claim boundary for {stage}.",
        )
    ]
    context_refs = [*identity_facts, *metric_facts, *count_facts]
    if context_refs:
        context_bits = []
        for key, label in ("sample_unit", "样本单位"), ("validation_design", "验证设计"), ("metric", "主指标"):
            value = metric.get(key) or identity.get(key)
            if value not in (None, ""):
                context_bits.append(_value_sentence(label, value).rstrip("。"))
        text = "；".join(context_bits) + "。" if context_bits else "本次确认依赖已登记的样本、验证与指标身份。"
        confirming.append(
            _statement(
                "scientific-context",
                text,
                fact_refs=context_refs,
                evidence_refs=[metric.get("metric_source") or f"policy:checkpoint:{stage}"],
                semantic_key=_semantic_identity(identity, metric),
                text_en="The registered sample, validation design, and primary metric define this decision.",
            )
        )
    confirming.extend(findings[:4])
    confirming.extend(item["statement"] for item in figure_claims[:6])

    not_confirming = [
        _statement(
            "not-confirming-derived-files",
            "本次不确认 HTML 排版、PDF 重编译、manifest 排序、绝对路径或其它派生产物的技术变化。",
            evidence_refs=["policy:checkpoint:presentation"],
            semantic_key="derived_and_presentation_changes_are_not_scientific_decisions",
            text_en="This decision does not approve HTML layout, PDF recompilation, manifest ordering, absolute paths, or other derived presentation changes.",
        ),
        _statement(
            "not-confirming-outside-boundary",
            "本次不把当前证据扩展为超出已登记样本、方法、验证设计和论断边界的结论。",
            fact_refs=boundary_facts or ([scope_fact] if scope_fact else []),
            evidence_refs=["policy:checkpoint:claim-boundary"],
            semantic_key={"stage": stage, "boundary_count": len(boundary_facts)},
            text_en="This decision does not extend the evidence beyond the registered sample, method, validation design, or claim boundary.",
        ),
    ]
    reopen_conditions = [
        _statement(
            "reopen-identity-or-metric",
            "数据集、队列、样本单位、划分、方法、主指标、不确定性或运行身份变化时，必须重新进行科学确认。",
            fact_refs=context_refs or ([scope_fact] if scope_fact else []),
            evidence_refs=["policy:checkpoint:scientific-change"],
            semantic_key="identity_metric_method_change_requires_reconfirmation",
            text_en="A change to the dataset, cohort, sample unit, split, method, primary metric, uncertainty, or run identity requires a new scientific confirmation.",
        ),
        _statement(
            "reopen-figure-or-claim",
            "主图的语义证据或论文论断边界变化时，必须重新进行科学确认。",
            fact_refs=[*figure_facts, *boundary_facts] or ([scope_fact] if scope_fact else []),
            evidence_refs=["policy:checkpoint:figure-claim-change"],
            semantic_key="figure_or_claim_boundary_change_requires_reconfirmation",
            text_en="A change to main-figure semantic evidence or a manuscript claim boundary requires a new scientific confirmation.",
        ),
    ]
    downstream_effects = [
        _statement(
            "downstream-effect",
            _text(summary.get("confirmation_meaning_zh")) or "确认后，工作流只会沿当前阶段允许的下游路线继续。",
            fact_refs=[scope_fact] if scope_fact else [],
            evidence_refs=[f"policy:checkpoint:{stage}"],
            semantic_key={"stage": stage},
            text_en="After confirmation, the workflow may continue only along the downstream route allowed by this stage.",
        )
    ]
    deliverables = [
        {
            "project_relative_path": _text(item.get("project_relative_path")),
            "title_zh": _text(item.get("title_zh")) or _text(item.get("project_relative_path")),
            "purpose_zh": _text(item.get("purpose_zh") or item.get("scientific_relevance_zh")),
            "deliverable_group": _text(item.get("deliverable_group")),
            "evidence_refs": _source_refs(item),
        }
        for item in (summary.get("inspection_targets") or [])[:8]
        if isinstance(item, dict) and _text(item.get("project_relative_path"))
    ]
    if not deliverables:
        deliverables = [
            {
                "project_relative_path": _text(item.get("project_relative_path")),
                "title_zh": _text(item.get("title_zh")) or _text(item.get("project_relative_path")),
                "purpose_zh": _text(item.get("purpose_zh") or item.get("scientific_relevance_zh")),
                "deliverable_group": _text(item.get("deliverable_group")),
                "evidence_refs": _source_refs(item),
            }
            for item in (summary.get("stage_deliverables") or [])[:8]
            if isinstance(item, dict) and _text(item.get("project_relative_path"))
        ]
    semantic_subject = {
        "checkpoint_type": stage,
        "facts": _semantic_sort([
            {
                "fact_id": item["fact_id"],
                "fact_type": item["fact_type"],
                "semantic_value": item["semantic_value"],
            }
            for item in facts
        ]),
        "confirming": _semantic_sort([item["semantic_key"] for item in confirming]),
        "not_confirming": _semantic_sort([item["semantic_key"] for item in not_confirming]),
        "claim_boundaries": _semantic_sort([item["semantic_key"] for item in boundaries]),
        "figure_claims": _semantic_sort([item["statement"]["semantic_key"] for item in figure_claims]),
        "reopen_conditions": _semantic_sort([item["semantic_key"] for item in reopen_conditions]),
    }
    brief = {
        "schema_version": HUMAN_DECISION_BRIEF_SCHEMA,
        "locale": locale,
        "checkpoint_type": stage,
        "decision_id": f"decision-{_hash(semantic_subject)[:20]}",
        "decision_question": _statement(
            "decision-question",
            f"本次需要作者确认的科学基础与论断边界是什么？（{purpose}）",
            fact_refs=[scope_fact] if scope_fact else [],
            evidence_refs=[f"policy:checkpoint:{stage}"],
            semantic_key={"stage": stage},
            text_en=f"What scientific basis and claim boundaries are being confirmed for {stage}?",
        ),
        "facts": facts,
        "confirming": confirming,
        "not_confirming": not_confirming,
        "scientific_context": {
            "identity_fact_refs": identity_facts,
            "metric_fact_refs": metric_facts,
            "count_fact_refs": count_facts,
        },
        "key_findings": findings,
        "coverage_and_missingness": [],
        "figure_claims": figure_claims,
        "claim_boundaries": boundaries,
        "semantic_delta": {"classification": "pending_comparison", "summary_zh": "等待与最近有效科学确认进行比较。"},
        "downstream_effects": downstream_effects,
        "reopen_conditions": reopen_conditions,
        "decision_options": list(summary.get("decision_routes") or []),
        "latest_user_visible_deliverables": deliverables,
        "semantic_subject": semantic_subject,
    }
    brief["brief_semantic_sha256"] = brief_semantic_sha256(brief)
    return brief


def brief_semantic_payload(brief: dict[str, Any]) -> dict[str, Any]:
    """Return the language-independent subject that a user actually approves."""

    return {
        "schema_version": HUMAN_DECISION_BRIEF_SCHEMA,
        "checkpoint_type": brief.get("checkpoint_type"),
        "semantic_subject": brief.get("semantic_subject") or {},
    }


def brief_semantic_sha256(brief: dict[str, Any]) -> str:
    return _hash(brief_semantic_payload(brief))


def validate_human_decision_brief(brief: Any) -> list[str]:
    """Return proof-oriented contract problems without attempting repair."""

    if not isinstance(brief, dict):
        return ["Human decision brief is not an object."]
    if brief.get("schema_version") != HUMAN_DECISION_BRIEF_SCHEMA:
        return ["Unsupported human decision brief schema."]
    issues: list[str] = []
    facts = brief.get("facts")
    if not isinstance(facts, list) or not facts:
        issues.append("Human decision brief has no evidence-bound facts.")
        facts = []
    fact_ids = {_text(item.get("fact_id")) for item in facts if isinstance(item, dict)}
    for fact in facts:
        if not isinstance(fact, dict):
            issues.append("Human decision brief contains a non-object fact.")
            continue
        if not _text(fact.get("fact_id")):
            issues.append("Human decision brief fact lacks fact_id.")
        if not fact.get("evidence_refs"):
            issues.append(f"Human decision brief fact lacks evidence refs: {_text(fact.get('fact_id')) or 'unknown'}.")
    for field in ("confirming", "not_confirming", "reopen_conditions"):
        values = brief.get(field)
        if not isinstance(values, list) or not values:
            issues.append(f"Human decision brief field is empty: {field}.")
            continue
        for item in values:
            if not isinstance(item, dict) or not _text(item.get("statement_id")) or not _text(item.get("text_zh")):
                issues.append(f"Human decision brief has malformed statement in {field}.")
                continue
            refs = set(item.get("fact_refs") or [])
            if refs and not refs <= fact_ids:
                issues.append(f"Human decision brief statement has unknown fact ref: {_text(item.get('statement_id'))}.")
            if not refs and not item.get("evidence_refs") and not item.get("claim_refs"):
                issues.append(f"Human decision brief statement is not evidence-bound: {_text(item.get('statement_id'))}.")
    expected = brief_semantic_sha256(brief)
    if _text(brief.get("brief_semantic_sha256")) != expected:
        issues.append("Human decision brief semantic hash does not match its statement/fact set.")
    return issues


__all__ = [
    "HUMAN_DECISION_BRIEF_SCHEMA",
    "brief_semantic_payload",
    "brief_semantic_sha256",
    "build_human_decision_brief",
    "validate_human_decision_brief",
]
