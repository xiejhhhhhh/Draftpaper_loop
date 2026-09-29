from __future__ import annotations

from pathlib import Path

from draftpaper_cli.checkpoint_html import render_checkpoint_decision_html
from draftpaper_cli.checkpoint_readability import build_checkpoint_readability_report


def test_core_evidence_confirmation_summarizes_round_and_after_confirmation_work(tmp_path: Path) -> None:
    batch = {
        "batch_id": "batch-1",
        "summary_zh": "本轮完成核验结果和样本边界。",
        "summary_en": "This round completed Validate result and Check sample boundary.",
        "tasks": [
            {
                "title_zh": "核验结果",
                "title_en": "Validate result",
                "evidence_refs": ["results/metrics.json"],
                "expected_artifacts": ["results/validated_metrics.json"],
            },
            {
                "title_zh": "核对样本边界",
                "title_en": "Check sample boundary",
                "evidence_refs": ["data/sample_manifest.json"],
                "expected_artifacts": ["results/sample_flow.csv"],
            },
        ],
    }
    summary = {
        "schema_version": "dpl.checkpoint_summary.v6",
        "review_state": "confirmable",
        "checkpoint_title_zh": "核心证据确认",
        "stage_narrative_zh": "本阶段实际核验了核心指标并修订样本边界，产出更新后的指标和样本流程文件。",
        "core_evidence_batch": batch,
        "decision_brief": {
            "decision_question": {"text_zh": "请确认本轮核心证据。", "text_en": "Confirm this round's core evidence."},
            "semantic_delta": {"classification": "first_scientific_decision", "changes": []},
            "confirming": [],
            "facts": [],
            "key_findings": [],
            "figure_claims": [],
            "claim_boundaries": [],
            "not_confirming": [],
            "reopen_conditions": [],
            "latest_user_visible_deliverables": [],
            "downstream_effects": [],
        },
        "confirmation_contract": {"confirmation_command_allowed": False},
        "confirmation_meaning_zh": "确认后冻结本次候选。",
    }

    zh = render_checkpoint_decision_html(tmp_path, tmp_path, summary, {})
    en = render_checkpoint_decision_html(tmp_path, tmp_path, summary, {}, locale="en")

    assert "本阶段实际核验了核心指标并修订样本边界" in zh
    assert "核验结果" in zh and "核对样本边界" in zh
    assert "results/metrics.json" in zh and "results/sample_flow.csv" in zh
    assert "确认后会继续什么" in zh
    assert "正式安装" in zh and "排版" in zh and "PDF" in zh
    assert "不得改变本次确认的数据、方法、验证身份、指标、图表语义和论断边界" in zh
    assert "Round overview" in en
    assert "Validate result" in en and "Check sample boundary" in en
    assert "What happens after confirmation" in en
    assert "installation" in en and "typesetting" in en and "PDF" in en
    assert "must not change the confirmed dataset, method, validation identity, metrics, figure semantics, or claim boundaries" in en
    zh_report = build_checkpoint_readability_report(html=zh, brief=summary["decision_brief"])
    en_report = build_checkpoint_readability_report(html=en, brief=summary["decision_brief"], locale="en")
    assert zh_report["checks"]["core_evidence_round_overview_present"] is True
    assert zh_report["checks"]["core_evidence_follow_up_boundary_present"] is True
    assert en_report["checks"]["core_evidence_round_overview_present"] is True
    assert en_report["checks"]["core_evidence_follow_up_boundary_present"] is True


def test_core_evidence_batch_readability_gate_requires_round_summary_and_scientific_boundary() -> None:
    incomplete = '<html lang="zh-CN"><body><section data-batch-id="batch-1"><h2>本阶段工作概述</h2><p>只写了一个标题。</p></section></body></html>'

    report = build_checkpoint_readability_report(html=incomplete, brief={})

    assert report["checks"]["core_evidence_round_overview_present"] is False
    assert report["checks"]["core_evidence_follow_up_boundary_present"] is False


def test_scientific_change_page_explains_fact_and_figure_deltas_without_hashes(tmp_path: Path) -> None:
    facts_before = [
        {
            "fact_type": "metric",
            "semantic_value": {"metric": "macro-F1", "cohort_id": "cohort-a", "value": 0.71},
        },
        {
            "fact_type": "count",
            "semantic_value": {
                "cohort_id": "cohort-a",
                "entity_type": "source",
                "count_mode": "unique",
                "value": 20,
            },
        },
    ]
    facts_after = [
        {
            "fact_type": "metric",
            "semantic_value": {"metric": "macro-F1", "cohort_id": "cohort-a", "value": 0.74},
        },
        {
            "fact_type": "count",
            "semantic_value": {
                "cohort_id": "cohort-a",
                "entity_type": "source",
                "count_mode": "unique",
                "value": 24,
            },
        },
        {
            "fact_type": "count",
            "semantic_value": {
                "cohort_id": "cohort:registered_2023_samples",
                "entity_type": "sample_record",
                "count_mode": "post_filter_row_count",
                "value": 1824,
            },
        },
    ]
    figure_before = {
        "claim_statement_id": "figure-2",
        "figure_id": "Figure 2: source-held-out evaluation",
        "expected_cohort_id": "cohort-a",
        "expected_split_id": "source-held-out",
        "plotted_series_ids": ["macro-F1"],
        "figure_semantic_sha256": "a" * 64,
    }
    figure_after = {
        **figure_before,
        "expected_split_id": "leave-one-source-out",
        "figure_semantic_sha256": "b" * 64,
    }
    figure_statement = {
        "statement_id": "figure-2",
        "text_zh": "Figure 2 shows source-held-out classification results.",
        "text_en": "Figure 2 shows source-held-out classification results.",
    }
    brief = {
        "decision_question": {"statement_id": "decision", "text_zh": "请核查本次核心证据变化。"},
        "semantic_delta": {
            "classification": "scientific_change",
            "summary_zh": "相对最近一次有效确认，以下科学决定字段发生变化：decision_brief.semantic_subject.facts、figure_claim_map；需要新的作者确认。",
            "changes": [
                {
                    "field": "decision_brief.semantic_subject.facts",
                    "before": facts_before,
                    "after": facts_after,
                },
                {"field": "figure_claim_map", "before": [figure_before], "after": [figure_after]},
            ],
        },
        "confirming": [],
        "facts": [
            {
                "fact_id": "count-1",
                "label_zh": "筛选后样本记录数",
                "label_en": "Post-filter sample records",
                "value": facts_after[2]["semantic_value"],
            }
        ],
        "scientific_context": {},
        "key_findings": [],
        "figure_claims": [
            {
                "figure_id": "Figure 2: source-held-out evaluation",
                "project_relative_path": "results/figures/figure-2.png",
                "statement": figure_statement,
            }
        ],
        "claim_boundaries": [],
        "not_confirming": [],
        "reopen_conditions": [],
        "latest_user_visible_deliverables": [],
        "downstream_effects": [],
    }
    summary = {
        "schema_version": "dpl.checkpoint_summary.v6",
        "review_state": "confirmable",
        "checkpoint_title_zh": "核心证据确认",
        "decision_brief": brief,
        "confirmation_continuity": {"eligible": False},
        "scientific_decision_fingerprint": {"scientific_decision_sha256": "decision-hash"},
        "confirmation_contract": {"confirmation_command_allowed": False},
    }

    html = render_checkpoint_decision_html(tmp_path, tmp_path, summary, {})
    delta_section = html.split('<h2>相对上次确认的变化</h2>', 1)[1].split("</section>", 1)[0]

    assert "核心证据事实" in delta_section
    assert "macro-F1" in delta_section
    assert "0.71" in delta_section and "0.74" in delta_section
    assert "样本组" in delta_section and "cohort-a" in delta_section and "source" in delta_section
    assert "20" in delta_section and "24" in delta_section
    assert "1,824" in delta_section or "1824" in delta_section
    assert "2023 年登记样本" in delta_section
    assert "筛选后保留" in delta_section
    assert "registered samples" not in delta_section
    assert "cohort:registered_2023_samples" not in delta_section
    assert "post_filter_row_count" not in delta_section
    assert "Figure 2: source-held-out evaluation" in delta_section
    assert "source-held-out" in delta_section and "leave-one-source-out" in delta_section
    assert "Figure 2 shows source-held-out classification results." in delta_section
    assert "本次确认记录未附上一版图像预览" in delta_section
    assert "查看当前图表" in delta_section
    assert 'href="#figure-evidence-figure-2"' in delta_section
    assert 'id="figure-evidence-figure-2"' in html
    assert "decision_brief.semantic_subject.facts" not in delta_section
    assert "figure_claim_map" not in delta_section
    assert "SHA-256" not in delta_section
    assert "a" * 32 not in delta_section
    assert "b" * 32 not in delta_section

    zh_readability = build_checkpoint_readability_report(html=html, brief=brief)
    assert zh_readability["checks"]["semantic_delta_present"] is True

    en_html = render_checkpoint_decision_html(tmp_path, tmp_path, summary, {}, locale="en")
    en_delta_section = en_html.split('<h2>What changed since the prior confirmation</h2>', 1)[1].split("</section>", 1)[0]
    assert "core evidence facts" in en_delta_section
    assert "macro-F1" in en_delta_section
    assert "0.71" in en_delta_section and "0.74" in en_delta_section
    assert "Figure 2: source-held-out evaluation" in en_delta_section
    assert "Figure 2 shows source-held-out classification results." in en_delta_section
    assert "does not include the prior image" in en_delta_section
    assert "SHA-256" not in en_delta_section
    en_readability = build_checkpoint_readability_report(html=en_html, brief=brief, locale="en")
    assert en_readability["checks"]["semantic_delta_present"] is True
