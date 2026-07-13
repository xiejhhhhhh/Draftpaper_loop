# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import re
from typing import Any


REQUIRED_STORYBOARD_FIELDS = [
    "research_question",
    "expected_finding",
    "required_data",
    "required_method",
    "supporting_literature_keys",
]


class ResearchBlueprintQualityError(RuntimeError):
    """Raised when the research blueprint is too incomplete to drive downstream stages."""


def _compact(text: str, limit: int = 220) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rsplit(" ", 1)[0] + "..."


def _tokens(text: str) -> set[str]:
    stopwords = {"the", "and", "for", "with", "using", "from", "this", "that", "study", "model", "data"}
    return {
        token
        for token in re.findall(r"[a-zA-Z][a-zA-Z0-9-]{2,}", (text or "").lower())
        if token not in stopwords
    }


def _top_literature_keys(literature_items: list[dict[str, Any]], limit: int = 4) -> list[str]:
    keys = []
    for item in sorted(literature_items, key=lambda value: int(value.get("citation_count") or 0), reverse=True):
        key = str(item.get("bibtex_key") or item.get("citation_key") or "")
        if key and key not in keys:
            keys.append(key)
    return keys[:limit] or ["literature_evidence_required"]


def _literature_synthesis(literature_items: list[dict[str, Any]], citation_rows: list[dict[str, str]]) -> dict[str, Any]:
    method_terms: list[str] = []
    data_terms: list[str] = []
    gap_terms: list[str] = []
    for item in literature_items:
        blob = " ".join([
            str(item.get("title") or ""),
            str(item.get("abstract") or ""),
            str((item.get("deep_summary") or {}).get("methods") or ""),
            str((item.get("deep_summary") or {}).get("data_used") or ""),
        ]).lower()
        for term in [
            "transformer",
            "baseline",
            "ablation",
            "multimodal",
            "time series",
            "light curve",
            "validation",
            "uncertainty",
            "classification",
            "spectral",
        ]:
            if term in blob and term not in method_terms:
                method_terms.append(term)
        for term in ["light curve", "spectral", "tabular", "event", "survey", "label", "class", "time"]:
            if term in blob and term not in data_terms:
                data_terms.append(term)
    for row in citation_rows:
        if (row.get("claim") or "") == "current gap":
            summary = _compact(row.get("evidence_summary") or "", 180)
            if summary and summary not in gap_terms:
                gap_terms.append(summary)
    return {
        "key_methods": method_terms[:8],
        "key_data_modalities": data_terms[:8],
        "gap_evidence": gap_terms[:5],
        "synthesis_summary": _compact(
            " ".join(str(item.get("abstract") or item.get("title") or "") for item in literature_items[:6]),
            700,
        ),
    }


def _context_flags(project_meta: dict[str, Any], literature_synthesis: dict[str, Any]) -> dict[str, bool]:
    text = " ".join([
        str(project_meta.get("title") or ""),
        str(project_meta.get("idea") or ""),
        str(project_meta.get("field") or ""),
        " ".join(literature_synthesis.get("key_methods") or []),
        " ".join(literature_synthesis.get("key_data_modalities") or []),
    ]).lower()
    return {
        "classification": any(term in text for term in ["classification", "classifier", "classify", "label", "source class"]),
        "time_series": any(term in text for term in ["time", "light curve", "sequence", "temporal", "irregular"]),
        "transformer": any(term in text for term in ["transformer", "attention", "token"]),
        "multimodal": any(term in text for term in ["multimodal", "spectral", "multiwavelength", "tabular", "fusion"]),
        "scientific_image": any(term in text for term in ["image", "imaging", "visual", "cutout", "morphology", "dinov2", "embedding"]),
        "group_validation": any(term in text for term in ["group-aware", "spatial grouping", "held-out", "group validation"]),
        "confounder_control": any(term in text for term in ["confound", "selection effect", "redshift", "luminosity", "leakage"]),
        "anomaly": any(term in text for term in ["anomaly", "outlier", "rare candidate"]),
        "astronomy": any(term in text for term in ["astronomy", "x-ray", "wxt", "flare", "transient", "source"]),
        "remote_sensing": any(term in text for term in ["ndvi", "remote sensing", "yield", "climate", "geography"]),
    }


def _claim_templates(project_meta: dict[str, Any], flags: dict[str, bool]) -> list[dict[str, str]]:
    idea = str(project_meta.get("idea") or project_meta.get("title") or "the proposed study")
    if flags["scientific_image"]:
        return [
            {
                "claim_id": "claim_1_data_support",
                "research_question": f"What cohort, image coverage, label provenance, and missingness support {idea}?",
                "expected_finding": "The sample flow should define distinct source, image-available, image-valid, and analysis cohorts before any representation claim is made.",
            },
            {
                "claim_id": "claim_2_representation_signal",
                "research_question": "Does the image representation contain structure associated with an independently defined scientific target rather than only identifiers or preprocessing artifacts?",
                "expected_finding": "Representation structure should be related to an independent target while remaining explicitly separated from exploratory visualization and label-defining variables.",
            },
            {
                "claim_id": "claim_3_generalization",
                "research_question": "Does representation-based prediction generalize under group-aware validation and class imbalance?",
                "expected_finding": "Held-out performance and uncertainty should be compared with transparent baselines on the same cohort, sample unit, and split.",
            },
            {
                "claim_id": "claim_4_incremental_value",
                "research_question": "What information does the image representation add beyond catalog, selection, or other confounding variables?",
                "expected_finding": "Ablation should distinguish incremental visual information from redshift, brightness, color, acquisition, or label leakage.",
            },
            {
                "claim_id": "claim_5_error_boundary",
                "research_question": "Which classes, sample regimes, image-quality conditions, or anomaly candidates remain uncertain?",
                "expected_finding": "Class-wise errors, stability, and candidate diagnostics should bound interpretation and identify cases requiring independent confirmation.",
            },
        ]
    if flags["classification"]:
        return [
            {
                "claim_id": "claim_1_data_support",
                "research_question": f"What data coverage and label support are available for {idea}?",
                "expected_finding": "The available samples, labels, and modalities should define which classification claims are scientifically supportable.",
            },
            {
                "claim_id": "claim_2_feature_signal",
                "research_question": "Do the available temporal, spectral, or tabular features contain separable structure before model training?",
                "expected_finding": "Feature-space diagnostics should show whether the data contain model-ready signal rather than only filename-level evidence.",
            },
            {
                "claim_id": "claim_3_model_gain",
                "research_question": "Does the proposed method improve over transparent baselines under a reproducible validation design?",
                "expected_finding": "The main model result should be judged by baseline comparison, ablation, and verified local metrics.",
            },
            {
                "claim_id": "claim_4_modality_value",
                "research_question": "Which data modality or method component contributes most to the result?",
                "expected_finding": "Ablation should show which declared feature groups or method components drive the result.",
            },
            {
                "claim_id": "claim_5_error_boundary",
                "research_question": "Which classes, samples, or regimes remain uncertain after the proposed method is applied?",
                "expected_finding": "Error analysis should constrain the final claim boundary and identify data or method limitations.",
            },
        ]
    if flags["remote_sensing"]:
        return [
            {
                "claim_id": "claim_1_data_support",
                "research_question": f"What spatial, temporal, and variable coverage supports {idea}?",
                "expected_finding": "The data support should define where the downstream suitability or environmental claim is reliable.",
            },
            {
                "claim_id": "claim_2_feature_distribution",
                "research_question": "How do the main environmental or remote-sensing variables vary across the study units?",
                "expected_finding": "Distribution and quality diagnostics should identify usable gradients and outlier-sensitive variables.",
            },
            {
                "claim_id": "claim_3_driver_response",
                "research_question": "Which driver has the clearest empirical relationship with the target response?",
                "expected_finding": "Driver-response evidence should be supported by effect size, uncertainty, and validation rather than visual trend alone.",
            },
            {
                "claim_id": "claim_4_validation",
                "research_question": "Does the model remain stable under spatial, temporal, or group-aware validation?",
                "expected_finding": "Validation diagnostics should show whether the result generalizes beyond random split artifacts.",
            },
            {
                "claim_id": "claim_5_synthesis",
                "research_question": "What final zoning, suitability, or response pattern is scientifically defensible?",
                "expected_finding": "The synthesis result should connect the validated model output to a bounded geographical interpretation.",
            },
        ]
    return [
        {
            "claim_id": "claim_1_data_support",
            "research_question": f"What empirical data support the proposed study: {idea}?",
            "expected_finding": "The data overview should establish the observation support and the limits of downstream claims.",
        },
        {
            "claim_id": "claim_2_main_relationship",
            "research_question": "What primary relationship or pattern should be tested first?",
            "expected_finding": "The first empirical result should reveal whether the core idea is supported by visible data structure.",
        },
        {
            "claim_id": "claim_3_method_comparison",
            "research_question": "Which baseline or alternative method is necessary for a credible comparison?",
            "expected_finding": "Method comparison should prevent the manuscript from relying on an unsupported proposed-method narrative.",
        },
        {
            "claim_id": "claim_4_robustness",
            "research_question": "How robust is the main result to validation, sensitivity, or quality-control choices?",
            "expected_finding": "Robustness evidence should determine whether the result can be written as a strong claim or a limited exploratory finding.",
        },
        {
            "claim_id": "claim_5_synthesis",
            "research_question": "What final evidence synthesis should be shown before writing Results and Discussion?",
            "expected_finding": "The synthesis figure should connect verified empirical outputs to the final claim boundary.",
        },
    ]


def _storyboard_figures(
    *,
    project_meta: dict[str, Any],
    claims: list[dict[str, str]],
    literature_keys: list[str],
    flags: dict[str, bool],
) -> list[dict[str, Any]]:
    method_prefix = ["data_alignment"]
    if flags["transformer"]:
        method_prefix.append("time_aware_transformer")
    if flags["multimodal"]:
        method_prefix.append("multimodal_fusion")
    if flags["classification"]:
        if flags["scientific_image"]:
            titles = [
                "Sample construction, image coverage, and missingness",
                "Image-representation structure against independent targets and confounders",
                "Group-aware representation prediction versus transparent baselines",
                "Incremental-value and confounder ablation",
                "Class-wise error, imbalance, and uncertainty structure",
                "Anomaly candidates and image-quality interpretation boundary",
            ]
            plot_types = ["data_overview", "embedding_diagnostic", "metric_summary", "metric_summary", "confusion_matrix", "image_gallery"]
            metrics = ["cohort_coverage", "target_and_confounder_association", "group_held_out_metric", "incremental_metric_delta", "classwise_uncertainty", "candidate_stability"]
            data = [
                ["source_catalog", "image_availability", "valid_image_cohort", "missingness_reason"],
                ["image_embedding", "independent_target", "confounder_variables"],
                ["image_embedding", "independent_target", "group_validation_split", "class_label"],
                ["image_embedding", "catalog_baseline_features", "confounder_variables", "class_label"],
                ["predicted_label", "class_label", "prediction_score", "class_support"],
                ["image_embedding", "image_cutout", "quality_flags", "candidate_score"],
            ]
            methods = [
                ["cohort_flow_audit", "missingness_analysis"],
                ["representation_projection", "target_confounder_diagnostic"],
                ["group_aware_validation", "transparent_baseline_comparison", "uncertainty_estimation"],
                ["feature_group_ablation", "confounder_control", "label_leakage_check"],
                ["confusion_or_error_analysis", "class_imbalance_analysis", "uncertainty_summary"],
                ["anomaly_stability_analysis", "image_quality_review", "candidate_interpretation_boundary"],
            ]
        else:
            temporal = flags["time_series"]
            titles = [
                "End-to-end temporal classification workflow" if temporal else "End-to-end classification workflow",
                "Class support and modality completeness for the sample",
                "Temporal and feature structure before model training" if temporal else "Feature structure before model training",
                "Baseline versus proposed-model performance",
                "Ablation of declared feature and method components",
                "Error structure and uncertainty across confused classes",
            ]
            plot_types = ["data_overview", "class_balance", "scatter_regression", "metric_summary", "metric_summary", "metric_summary"]
            metrics = ["pipeline_completeness", "imbalance_ratio", "class_separation_summary", "f1", "ablation_delta", "confusion_summary"]
            data = [
                ["source_catalog", "primary_observations", "declared_feature_groups"],
                ["class_label", "modality_availability"],
                ["features", "class_label"],
                ["features", "class_label", "validation_split"],
                ["declared_feature_groups", "class_label"],
                ["predicted_label", "class_label", "prediction_score"],
            ]
            primary_model = "time_aware_transformer" if flags["transformer"] and temporal else "proposed_model"
            methods = [
                method_prefix,
                ["class_balance_check", "missingness_check"],
                ["feature_space_diagnostic"],
                ["baseline_model", primary_model, "metric_evaluation"],
                ["ablation_study", "declared_component_comparison"],
                ["confusion_or_error_analysis", "uncertainty_summary"],
            ]
    else:
        titles = [
            "End-to-end research workflow",
            "Data support and quality-control overview",
            "Primary feature distribution and observation support",
            "Main empirical relationship or model response",
            "Validation, robustness, or ablation summary",
            "Final evidence synthesis and claim boundary",
        ]
        plot_types = ["data_overview", "data_overview", "histogram", "scatter_regression", "metric_summary", "metric_summary"]
        metrics = ["pipeline_completeness", "data_completeness", "distribution_summary", "r2_or_effect_size", "validation_metric", "claim_boundary"]
        data = [
            ["primary_dataset", "analysis_variables"],
            ["quality_flags", "required_variables"],
            ["main_predictor"],
            ["main_predictor", "target_or_response"],
            ["validation_split", "model_outputs"],
            ["verified_results", "figure_metadata"],
        ]
        methods = [
            ["data_alignment"],
            ["quality_control"],
            ["distribution_diagnostic"],
            ["model_or_statistical_association"],
            ["validation_or_ablation"],
            ["evidence_synthesis"],
        ]
    figures = []
    story_roles = [
        "study_boundary",
        "direct_scientific_signal",
        "direct_scientific_signal",
        "primary_comparison",
        "mechanism_or_ablation",
        "uncertainty_or_claim_boundary",
    ]
    for index, title in enumerate(titles, start=1):
        claim = claims[min(index - 1, len(claims) - 1)]
        figures.append({
            "figure_id": f"fig_{index}_{re.sub(r'[^a-z0-9]+', '_', title.lower()).strip('_')[:28]}",
            "proposed_title": title,
            "story_role": story_roles[index - 1],
            "research_question": claim["research_question"],
            "expected_finding": claim["expected_finding"],
            "scientific_claim_boundary": "Interpret this figure only within the verified data, method, and validation limits declared in the research blueprint.",
            "required_data": data[index - 1],
            "required_method": methods[index - 1],
            "suggested_plot_type": plot_types[index - 1],
            "validation_metric": metrics[index - 1],
            "supporting_literature_keys": literature_keys[:2],
            "downstream_stage_dependency": ["method_plan", "figure_plan", "code", "results"],
            "fallback_if_data_missing": "Downgrade the claim, report missing data explicitly, and request data acquisition or method revision before writing Results.",
        })
    return figures


def _storyboard_tables(literature_keys: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "table_id": "table_1_dataset_method_validation_summary",
            "proposed_title": "Dataset, method, validation, and citation-evidence summary",
            "required_data": ["data_inventory", "method_requirements", "validation_design"],
            "required_method": ["data_summary", "method_summary", "citation_traceability"],
            "supporting_literature_keys": literature_keys[:3],
        }
    ]


def _method_plan(figures: list[dict[str, Any]], claims: list[dict[str, str]]) -> dict[str, Any]:
    tasks = []
    for index, figure in enumerate(figures, start=1):
        methods = figure.get("required_method") or ["method_requires_user_confirmation"]
        tasks.append({
            "task_id": f"method_task_{index}",
            "figure_id": figure.get("figure_id"),
            "research_question": figure.get("research_question"),
            "method_family": methods[0],
            "method_components": methods,
            "required_data": figure.get("required_data") or [],
            "validation_metric": figure.get("validation_metric"),
            "expected_output": figure.get("proposed_title"),
            "claim_id": (claims[min(index - 1, len(claims) - 1)] or {}).get("claim_id") if claims else "",
        })
    return {
        "status": "written",
        "source": "research_blueprint",
        "method_tasks": tasks,
        "downstream_consumers": ["method_blueprint", "figure_plan", "analysis_code", "methods_writer", "results_writer"],
    }


def _quality_gate(figures: list[dict[str, Any]]) -> dict[str, Any]:
    incomplete = []
    for figure in figures:
        missing = [field for field in REQUIRED_STORYBOARD_FIELDS if not figure.get(field)]
        if missing:
            incomplete.append({"figure_id": figure.get("figure_id"), "missing_fields": missing})
    status = "passed" if len(incomplete) <= 2 else "failed"
    return {
        "status": status,
        "incomplete_figure_count": len(incomplete),
        "incomplete_figures": incomplete,
        "rule": "A research plan fails when more than two storyboard figures lack concrete data, method, expected finding, research question, or literature support.",
    }


def build_research_blueprint(
    *,
    project_meta: dict[str, Any],
    literature_items: list[dict[str, Any]],
    citation_rows: list[dict[str, str]],
    discipline_profile: dict[str, Any],
    anchor_papers: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    synthesis = _literature_synthesis(literature_items, citation_rows)
    flags = _context_flags(project_meta, synthesis)
    keys = _top_literature_keys(literature_items)
    claims = _claim_templates(project_meta, flags)
    figures = _storyboard_figures(project_meta=project_meta, claims=claims, literature_keys=keys, flags=flags)
    tables = _storyboard_tables(keys)
    quality = _quality_gate(figures)
    if quality["status"] != "passed":
        raise ResearchBlueprintQualityError(
            "Research storyboard is too incomplete: "
            + ", ".join(str(item.get("figure_id")) for item in quality["incomplete_figures"])
        )
    method_plan = _method_plan(figures, claims)
    storyboard = {
        "status": "written",
        "source": "research_blueprint",
        "figures": figures,
        "tables": tables,
        "quality_gate": quality,
    }
    return {
        "status": "written",
        "project_id": project_meta.get("project_id"),
        "title": project_meta.get("title") or project_meta.get("idea"),
        "idea": project_meta.get("idea"),
        "field": project_meta.get("field"),
        "target_journal": project_meta.get("target_journal"),
        "discipline_profile": discipline_profile,
        "literature_synthesis": synthesis,
        "target_journal_anchor_papers": anchor_papers or [],
        "research_claims": claims,
        "figure_storyboard": storyboard,
        "method_plan": method_plan,
        "claim_evidence_links": [
            {
                "claim_id": claims[index % len(claims)]["claim_id"],
                "citation_key": row.get("citation_key"),
                "claim": row.get("claim"),
                "evidence_summary": row.get("evidence_summary"),
            }
            for index, row in enumerate(citation_rows[:24])
        ],
    }


def storyboard_to_figure_plan_items(
    storyboard: dict[str, Any],
    *,
    selected_data: str,
    available_columns: list[str],
    label_columns: list[str],
) -> list[dict[str, Any]]:
    figures: list[dict[str, Any]] = []
    lower_lookup = {column.lower(): column for column in available_columns + label_columns}

    def match_columns(required: list[str]) -> list[str]:
        matched = []
        for token in required:
            normalized = str(token).lower().replace("_", " ")
            for key, original in lower_lookup.items():
                if key in normalized or normalized in key.replace("_", " "):
                    if original not in matched:
                        matched.append(original)
        return matched

    for index, item in enumerate(storyboard.get("figures") or [], start=1):
        required_columns = match_columns(list(item.get("required_data") or []))
        x = required_columns[0] if required_columns else (available_columns[0] if available_columns else None)
        y = required_columns[1] if len(required_columns) > 1 else (available_columns[1] if len(available_columns) > 1 else None)
        group = next((column for column in required_columns if column in label_columns), label_columns[0] if label_columns else None)
        figure_type = str(item.get("suggested_plot_type") or "metric_summary")
        figures.append({
            "id": str(item.get("figure_id") or f"storyboard_figure_{index}"),
            "storyboard_id": str(item.get("figure_id") or f"storyboard_figure_{index}"),
            "title": str(item.get("proposed_title") or f"Storyboard figure {index}"),
            "path": f"results/figures/{str(item.get('figure_id') or f'storyboard_figure_{index}')}.png",
            "generation_mode": "generated_code",
            "source": "research_storyboard",
            "figure_role": "main_result",
            "contract_locked": True,
            "allowed_substitute": False,
            "counts_toward_main_figures": True,
            "figure_group": figure_type,
            "figure_type": figure_type,
            "visualization_type": figure_type,
            "required_inputs": [selected_data],
            "required_columns": required_columns,
            "required_data": list(item.get("required_data") or []),
            "required_method": list(item.get("required_method") or []),
            "expected_finding": item.get("expected_finding"),
            "validation_metric": item.get("validation_metric"),
            "supporting_literature_keys": list(item.get("supporting_literature_keys") or []),
            "x": x,
            "y": y,
            "group": group,
            "statistical_transform": [str(item.get("validation_metric") or "metric_summary")],
            "backend_preference": ["matplotlib_scienceplots", "matplotlib", "png_stdlib_fallback"],
            "no_flowchart_fallback": True,
            "scientific_question": item.get("research_question"),
            "caption_draft": f"{item.get('proposed_title')}.",
            "result_claim_template": item.get("scientific_claim_boundary") or item.get("expected_finding"),
            "storyboard_trace": item,
        })
    return figures
