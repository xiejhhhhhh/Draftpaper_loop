"""Wheel-installable held-out scientific release regressions for v0.30.0."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from .artifact_repository import ArtifactRepository
from .citation_audit import _semantic_support_checks, audit_citations
from .evidence_registry import build_scientific_evidence_registry
from .evidence_snapshot import create_evidence_snapshot
from .figure_plugin_trace import validate_figure_plugin_trace
from .orchestrator import status_project
from .paper_quality_parity import assess_paper_quality_parity
from .project_scaffold import create_project, utc_now
from .research_capabilities import assess_plugin_sufficiency
from .review_rule_runtime import assess_review_rules
from .scientific_figure_quality import assess_scientific_figure_quality
from .section_contracts import validate_section_writing
from .state_kernel import atomic_write_json
from .writing_coordinator import formal_writing_release_action


FIXTURE_ROOT = Path(__file__).resolve().parent / "release_fixtures"
FIXTURE_NAMES = ("scientific_image_ml", "geography_ml", "astronomy_ml", "bioinformatics_medicine", "physics_quantum")
FIGURE_IDS = ("fig_main", "fig_02", "fig_03", "fig_04", "fig_05", "fig_06")


class ReleaseRegressionError(RuntimeError):
    """Raised when a release fixture cannot prove its scientific contracts."""


def _load_fixture(name: str) -> dict[str, Any]:
    path = FIXTURE_ROOT / f"{name}.json"
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict) or payload.get("fixture_id") != name:
        raise ReleaseRegressionError(f"Invalid release fixture: {path}")
    return payload


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _project_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): _sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _draw_scientific_figure(path: Path, values: list[float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1400, 900), "white")
    draw = ImageDraw.Draw(image)
    draw.line((120, 70, 120, 780), fill="black", width=4)
    draw.line((120, 780, 1320, 780), fill="black", width=4)
    colors = ("#377eb8", "#4daf4a", "#e41a1c")
    for index, value in enumerate(values):
        x = 260 + index * 350
        y = 780 - int(max(0.0, min(1.0, value)) * 700)
        draw.rectangle((x, y, x + 160, 780), fill=colors[index], outline="black", width=2)
        draw.text((x, y - 30), f"{value:.3f}", fill="black")
    draw.text((500, 25), "Held-out scientific comparison", fill="black")
    draw.text((600, 840), "Analysis condition", fill="black")
    draw.text((20, 400), "Validated score", fill="black")
    for index in range(8):
        y = 780 - index * 90
        draw.line((110, y, 130, y), fill="black", width=2)
        draw.text((55, y - 8), f"{index / 8:.2f}", fill="black")
    image.save(path)


def _evidence_records(spec: dict[str, Any]) -> list[dict[str, Any]]:
    common = {
        "run_id": "run-main",
        "cohort_id": spec["cohort_id"],
        "cohort_view_id": f"cohort_view:{spec['cohort_id']}:heldout",
        "estimand_id": f"estimand:{spec['metric_name']}:heldout",
        "analysis_spec_id": f"analysis_spec:{spec['fixture_id']}:primary",
        "sample_unit": spec["sample_unit"],
        "split": spec["split"],
        "split_id": spec["split"],
        "metric_dimension": spec["metric_dimension"],
        "aggregation": "prespecified_primary",
        "target_sections": ["results", "discussion"],
    }
    metric = str(spec["metric_name"])
    return [
        {
            **common,
            "evidence_id": f"{spec['fixture_id']}:primary",
            "entity_role": f"result_metric_{metric}",
            "metric_name": metric,
            "value": spec["metric_value"],
            "unit": spec["metric_dimension"],
            "model_id": spec["model_id"],
        },
        {
            **common,
            "evidence_id": f"{spec['fixture_id']}:baseline",
            "entity_role": f"result_metric_baseline_{metric}",
            "metric_name": f"baseline_{metric}",
            "value": spec["baseline_value"],
            "unit": spec["metric_dimension"],
            "model_id": "baseline_model",
        },
        {
            **common,
            "evidence_id": f"{spec['fixture_id']}:ablation",
            "entity_role": f"result_metric_ablation_{metric}",
            "metric_name": f"ablation_{metric}",
            "value": spec["ablation_value"],
            "unit": spec["metric_dimension"],
            "model_id": "ablation_model",
        },
        {
            **common,
            "evidence_id": f"{spec['fixture_id']}:uncertainty",
            "entity_role": "confidence_interval_width",
            "metric_name": "confidence_interval_width",
            "value": spec["uncertainty_value"],
            "unit": spec["metric_dimension"],
            "model_id": spec["model_id"],
        },
    ]


def _write_citation_inputs(project: Path, spec: dict[str, Any]) -> None:
    key = str(spec["citation_key"])
    passage = str(spec["citation_passage"])
    title = str(spec["citation_title"])
    references = project / "references"
    (references / "library.bib").write_text(
        f"@article{{{key}, title={{{title}}}, author={{Release, Regression}}, year={{2025}}, journal={{Validation Journal}}}}\n",
        encoding="utf-8",
    )
    with (references / "citation_evidence.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["citation_key", "section", "claim", "evidence_summary", "source", "doi", "url"])
        for section in ("introduction", "data", "methods", "discussion"):
            writer.writerow([key, section, "held-out validation", passage, "curated_release_fixture", "10.0000/release", "https://example.org/release"])
    atomic_write_json(references / "literature_items.json", [{"bibtex_key": key, "title": title}])
    summaries = references / "literature_summaries"
    summaries.mkdir(parents=True, exist_ok=True)
    (summaries / f"{key.lower()}.html").write_text(f"<html><body>{key}: {passage}</body></html>", encoding="utf-8")
    (summaries / "index.html").write_text(f"<html><body>{key}</body></html>", encoding="utf-8")
    cited_sentence = f"{passage.rstrip('.')} \\citep{{{key}}}."
    for section in ("introduction", "data", "methods", "discussion"):
        target = project / section / f"{section}.tex"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"\\section{{{section.title()}}}\n{cited_sentence}\n", encoding="utf-8")
    (project / "results" / "results.tex").write_text(
        f"\\section{{Results}}\nAcross the {spec['cohort_id']} cohort, {spec['metric_label']} was {spec['metric_value']}. "
        "The baseline, ablation, and uncertainty evidence bound this comparison.\n",
        encoding="utf-8",
    )


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise ReleaseRegressionError(message)


def run_domain_regression(output_root: str | Path, fixture_name: str) -> dict[str, Any]:
    """Run one domain through the common scientific producer/consumer chain."""
    spec = _load_fixture(fixture_name)
    project = create_project(
        root=output_root,
        idea=str(spec["idea"]),
        field=str(spec["field"]),
        target_journal="Release Regression Journal",
    ).path
    repo = ArtifactRepository(project)
    modules = ["default", str(spec["primary_discipline"]), *[str(item) for item in spec["secondary_disciplines"]]]
    repo.write_json("research_plan/discipline_contract.json", {
        "primary_discipline": spec["primary_discipline"],
        "secondary_disciplines": spec["secondary_disciplines"],
        "discipline_modules": list(dict.fromkeys(modules)),
    })
    requirements = []
    for figure_id in FIGURE_IDS:
        requirements.extend([
            {"requirement_id": f"data:{figure_id}", "kind": "data", "figure_id": figure_id, "role": spec["data_plugin_id"], "discipline": spec["primary_discipline"], "core": True},
            {"requirement_id": f"method:{figure_id}", "kind": "method", "figure_id": figure_id, "method_family": spec["method_plugin_id"], "discipline": spec["secondary_disciplines"][0], "core": True},
            {"requirement_id": f"figure:{figure_id}", "kind": "figure", "figure_id": figure_id, "claim_ids": ["claim_main"], "core": True},
        ])
    repo.write_json("research_plan/research_capability_contract.json", {"requirements": requirements})
    table = repo.resolve("results/tables/metrics.csv")
    table.parent.mkdir(parents=True, exist_ok=True)
    table.write_text(
        "metric,value\n"
        f"{spec['metric_name']},{spec['metric_value']}\n"
        f"baseline_{spec['metric_name']},{spec['baseline_value']}\n"
        f"ablation_{spec['metric_name']},{spec['ablation_value']}\n"
        f"confidence_interval_width,{spec['uncertainty_value']}\n",
        encoding="utf-8",
    )
    table_hash = _sha256(table)
    output_hashes = {"results/tables/metrics.csv": table_hash}
    for figure_id in FIGURE_IDS:
        repo.append_event("data/plugin_execution_ledger.jsonl", {
            "event_id": f"{fixture_name}:data:{figure_id}", "figure_id": figure_id, "plugin_id": spec["data_plugin_id"],
            "status": "project_executed", "scientific_evidence_status": "project_result", "output_hashes": output_hashes,
        })
        repo.append_event("methods/plugin_execution_ledger.jsonl", {
            "event_id": f"{fixture_name}:method:{figure_id}", "figure_id": figure_id, "plugin_id": spec["method_plugin_id"],
            "status": "project_executed", "scientific_evidence_status": "project_result", "output_hashes": output_hashes,
        })
    records = _evidence_records(spec)
    repo.write_json("methods/run_manifest.yaml", {
        "status": "success", "run_id": "run-main", "cohort_id": spec["cohort_id"],
        "sample_unit": spec["sample_unit"], "evaluation_split": spec["split"], "model_id": spec["model_id"],
        "metrics": {item["metric_name"]: item["value"] for item in records},
        "output_files": ["results/tables/metrics.csv"],
    })
    repo.write_json("results/resolved_result_evidence.json", {"evidence_records": records})

    sufficiency = assess_plugin_sufficiency(project)
    _assert(sufficiency["decision"] == "pass", f"{fixture_name}: project-validated plugin sufficiency did not pass")
    binding_plan = repo.read_mapping("research_plan/plugin_binding_plan.json")
    for figure_id in FIGURE_IDS:
        binding_plan.setdefault("bindings", []).append({
            "requirement_id": f"review:{figure_id}", "figure_id": figure_id, "kind": "review",
            "plugin_id": spec["review_plugin_id"], "state": "covered",
        })
    repo.write_json("research_plan/plugin_binding_plan.json", binding_plan)

    figure_contracts = []
    figure_metadata = []
    result_figures = []
    for index, figure_id in enumerate(FIGURE_IDS, start=1):
        relative = f"results/figures/{figure_id}_comparison.png"
        figure = repo.resolve(relative)
        delta = (index - 1) * 0.005
        _draw_scientific_figure(figure, [
            max(0.0, float(spec["baseline_value"]) - delta),
            max(0.0, float(spec["ablation_value"]) - delta),
            max(0.0, float(spec["metric_value"]) - delta),
        ])
        figure_contracts.append({
            "figure_id": figure_id, "path": relative, "manuscript_role": "main",
            "scientific_question": f"Does held-out analysis panel {index} support the bounded primary comparison?",
            "required_data_roles": [spec["data_role"]], "required_method_outputs": [spec["metric_name"]],
        })
        figure_metadata.append({
            "figure_id": figure_id, "path": relative,
            "variable_roles": [spec["data_role"]], "method_outputs": [spec["metric_name"]],
            "statistics": {spec["metric_name"]: spec["metric_value"]},
            "interpretation_summary": "The held-out comparison is interpreted within the declared cohort and uncertainty boundary.",
            "source_tables": ["results/tables/metrics.csv"],
        })
        result_figures.append({
            "id": figure_id, "path": relative, "manuscript_role": "main",
            "evidence_ids": [records[0]["evidence_id"]], "run_id": "run-main",
        })
    repo.write_json("results/figure_contracts.json", {"main_contracts": figure_contracts})
    repo.write_json("results/figure_metadata.json", {"figures": figure_metadata})
    trace = validate_figure_plugin_trace(project)
    _assert(trace["decision"] == "pass", f"{fixture_name}: figure plugin trace did not pass")
    _assert(
        len(trace["figure_checks"]) == len(FIGURE_IDS),
        f"{fixture_name}: not every main figure group has a plugin trace",
    )
    figure_quality = assess_scientific_figure_quality(project)
    _assert(figure_quality["decision"] == "pass", f"{fixture_name}: rendered scientific figure did not pass")

    repo.write_json("results/result_manifest.yaml", {"figures": result_figures})
    registry = build_scientific_evidence_registry(project)
    _assert(registry["status"] == "ready" and registry["incomplete_binding_count"] == 0, f"{fixture_name}: evidence registry is incomplete")
    cohort_label = str(spec["cohort_id"]).replace("_", " ")
    result_sentence = f"Across the {cohort_label} cohort, {spec['metric_label']} was {spec['metric_value']}."
    section_validation = validate_section_writing("results", result_sentence, registry)
    _assert(section_validation["decision"] == "pass", f"{fixture_name}: Results evidence binding failed")

    for relative in (
        "research_plan/research_plan.md", "research_plan/method_plan.json", "research_plan/claim_contract.json",
        "data/data_feasibility_report.json", "data/data_inventory.json",
    ):
        target = repo.resolve(relative)
        if target.suffix == ".md":
            repo.write_text(relative, "# Release regression research plan\n")
        else:
            repo.write_json(relative, {"status": "verified"})
    blueprint = {
        "status": "written",
        "research_claims": [{"claim_id": "claim_main", "research_question": str(spec["idea"]), "expected_finding": "The held-out result should remain bounded by uncertainty."}],
        "figure_storyboard": {"status": "written", "figures": [
            {"figure_id": figure_id, "proposed_title": f"{spec['metric_label']} evidence group {index}", "research_question": str(spec["idea"]), "expected_finding": "The held-out result should remain bounded by uncertainty.", "required_data": [spec["data_role"]], "required_method": [spec["method_plugin_id"]], "supporting_literature_keys": [spec["citation_key"]], "validation_metric": spec["metric_name"]}
            for index, figure_id in enumerate(FIGURE_IDS, start=1)
        ]},
        "method_plan": {"status": "written", "method_tasks": []},
    }
    repo.write_json("research_plan/research_blueprint.json", blueprint)
    from .statistical_validation import assess_review_rule_coverage, build_statistical_validation_contract

    statistical = build_statistical_validation_contract(project, blueprint=blueprint)
    coverage = assess_review_rule_coverage(project)
    review = assess_review_rules(
        project,
        stage="post_results",
        evidence_context={
            "active_plugin_ids": [spec["data_plugin_id"], spec["method_plugin_id"], spec["review_plugin_id"]],
            "available_evidence_roles": [
                "baseline_metrics", "ablation_metrics", "assumptions_checked", "effect_size",
                "power_or_precision", "axis_units", "sample_size", "held_out_metrics", "uncertainty",
                "figure_metadata", "crs", "coordinate_transform_provenance", "biological_replicates",
                "sample_unit", "multiple_testing_method", "adjusted_p_values", "subject_level_split",
                "leakage_check", "variable_units", "dimension_check", "coordinate_definition",
                "partition_unit", "cutout_or_image_support", "exact_source_overlap_count",
                "angular_overlap_audit", "shared_acquisition_group_count", "unit_consistency",
                "overlap_audit",
            ],
            "coordinate_definition": "declared project coordinate reference and angular units",
            "partition_unit": spec["sample_unit"],
            "cutout_support_arcsec": 1.0,
            "exact_source_overlap_count": 0,
            "minimum_cross_partition_separation_arcsec": 2.0,
            "shared_acquisition_group_count": 0,
            "tested_leakage_modes": ["exact_source_identity", "spatial_support", "acquisition_group"],
        },
        write_path=repo.resolve("review/release_review_rule_report.json"),
    )
    _assert(review["decision"] == "pass", f"{fixture_name}: review-rule engine did not pass the complete evidence bundle")

    repo.write_json("results/figure_plan.json", {"figure_groups": [{"id": figure_id} for figure_id in FIGURE_IDS]})
    repo.write_json("results/figure_semantic_validation_report.json", {"decision": "pass"})
    repo.write_json("results/result_validity_report.json", {"decision": "pass"})
    snapshot = create_evidence_snapshot(project)
    _write_citation_inputs(project, spec)
    citation = audit_citations(project, final=True)
    _assert(citation["status"] == "passed", f"{fixture_name}: real final citation producer failed")
    parity = assess_paper_quality_parity(project)
    _assert(parity["citation_audit_contract"]["audit_passed"], f"{fixture_name}: parity did not consume the real citation producer")
    _assert(parity["citation_audit_contract"]["coverage_preserved"], f"{fixture_name}: parity lost reference coverage")
    _assert(parity["decision"] != "pass", f"{fixture_name}: synthetic fixture incorrectly authorized a 95% manuscript claim")

    writing_action = formal_writing_release_action(project)
    _assert(
        writing_action is not None and writing_action.get("command") in {
            "inventory-results",
            "prepare-section-writing",
            "compose-section-with-agent",
        },
        f"{fixture_name}: formal writing route did not require the free-prose lifecycle",
    )
    before_status = _project_hashes(project)
    status_project(project)
    after_status = _project_hashes(project)
    _assert(before_status == after_status, f"{fixture_name}: status mutated project artifacts")

    return {
        "fixture_id": fixture_name,
        "status": "passed",
        "project_path": str(project),
        "evidence_snapshot_id": snapshot["snapshot_id"],
        "checks": {
            "plugin_sufficiency": sufficiency["decision"],
            "figure_plugin_trace": trace["decision"],
            "scientific_figure_quality": figure_quality["decision"],
            "evidence_registry": registry["status"],
            "results_binding": section_validation["decision"],
            "review_rules": review["decision"],
            "citation_audit": citation["status"],
            "citation_schema_consumed_by_parity": True,
            "formal_free_prose_required": True,
            "status_read_only": True,
            "synthetic_95_percent_claim_rejected": True,
            "task_aware_statistical_contract": statistical["validation_count"] >= 3,
            "review_rule_gaps_explicit": coverage["decision"] in {"pass", "advisory_and_rescue_required"},
            "six_main_figure_groups_traced": len(trace["figure_checks"]) == len(FIGURE_IDS),
        },
    }


def run_adversarial_regressions(output_root: str | Path, successful_project: str | Path) -> dict[str, Any]:
    """Prove the release gates reject known scientific false positives."""
    base_record = {
        "evidence_id": "metric-discovery", "entity_role": "result_metric_f1_macro", "metric_name": "f1_macro",
        "value": 0.82, "unit": "score", "metric_dimension": "score", "run_id": "run-a",
        "cohort_id": "discovery", "sample_unit": "source", "split": "source_held_out", "model_id": "model-a",
    }
    scope_registry = {"records": [
        base_record,
        {**base_record, "evidence_id": "metric-external", "value": 0.71, "cohort_id": "external"},
        {**base_record, "evidence_id": "metric-run-b", "value": 0.71, "run_id": "run-b"},
        {**base_record, "evidence_id": "metric-observation", "value": 0.71, "sample_unit": "observation"},
        {**base_record, "evidence_id": "metric-random-split", "value": 0.71, "split": "random_split"},
        {**base_record, "evidence_id": "metric-model-b", "value": 0.71, "model_id": "model-b"},
    ]}
    wrong_cohort = validate_section_writing("results", "The external cohort reached macro-F1=0.82.", scope_registry)
    wrong_run = validate_section_writing("results", "Under run-b, the discovery cohort reached macro-F1=0.82.", scope_registry)
    wrong_unit = validate_section_writing("results", "At observation level, the discovery cohort reached macro-F1=0.82.", scope_registry)
    wrong_split = validate_section_writing("results", "On the random split, the discovery cohort reached macro-F1=0.82.", scope_registry)
    wrong_model = validate_section_writing("results", "Model-b reached macro-F1=0.82 in the discovery cohort.", scope_registry)
    wrong_metric = validate_section_writing("results", "The discovery cohort reached ROC-AUC=0.82.", {"records": [base_record]})
    wrong_dimension = validate_section_writing(
        "results", "The discovery cohort reached macro-F1=0.82.",
        {"records": [{**base_record, "metric_dimension": "count", "unit": "count"}]},
    )

    blank_project = Path(output_root) / "adversarial_blank_figure"
    if blank_project.exists():
        shutil.rmtree(blank_project)
    shutil.copytree(Path(successful_project), blank_project)
    figure = blank_project / "results" / "figures" / "fig_main_comparison.png"
    Image.new("RGB", (1400, 900), "white").save(figure)
    blank_report = assess_scientific_figure_quality(blank_project)

    spec = _load_fixture("geography_ml")
    plan_only = create_project(
        root=output_root,
        idea="Contract-only plugin must not satisfy core evidence",
        field=str(spec["field"]),
        target_journal="Release Regression Journal",
    ).path
    plan_repo = ArtifactRepository(plan_only)
    plan_repo.write_json("research_plan/discipline_contract.json", {
        "primary_discipline": spec["primary_discipline"],
        "secondary_disciplines": spec["secondary_disciplines"],
        "discipline_modules": ["default", spec["primary_discipline"], *spec["secondary_disciplines"]],
    })
    plan_repo.write_json("research_plan/research_capability_contract.json", {"requirements": [
        {"requirement_id": "data:fig_main", "kind": "data", "figure_id": "fig_main", "role": spec["data_plugin_id"], "core": True},
        {"requirement_id": "method:fig_main", "kind": "method", "figure_id": "fig_main", "method_family": spec["method_plugin_id"], "core": True},
    ]})
    plan_only_report = assess_plugin_sufficiency(plan_only)

    negation = _semantic_support_checks(
        "The treatment did not improve survival.", "The treatment improved survival.", "claim_support", 0.9, 0.9,
    )
    numeric = _semantic_support_checks(
        "The model achieved accuracy 0.90.", "The model achieved accuracy 0.70.", "claim_support", 0.9, 0.9,
    )
    causal = _semantic_support_checks(
        "Exposure causes disease.", "Disease causes exposure.", "claim_support", 0.9, 0.9,
    )

    checks = {
        "wrong_cohort_rejected": any(item["kind"] == "numeric_claim_scope_mismatch" for item in wrong_cohort["issues"]),
        "wrong_run_rejected": any(item["kind"] == "numeric_claim_scope_mismatch" for item in wrong_run["issues"]),
        "wrong_unit_rejected": any(item["kind"] == "numeric_claim_scope_mismatch" for item in wrong_unit["issues"]),
        "wrong_split_rejected": any(item["kind"] == "numeric_claim_scope_mismatch" for item in wrong_split["issues"]),
        "wrong_model_rejected": any(item["kind"] == "numeric_claim_scope_mismatch" for item in wrong_model["issues"]),
        "wrong_metric_rejected": any(item["kind"] == "numeric_claim_metric_mismatch" for item in wrong_metric["issues"]),
        "wrong_dimension_rejected": any(item["kind"] == "numeric_claim_metric_dimension_mismatch" for item in wrong_dimension["issues"]),
        "forged_blank_figure_rejected": blank_report["decision"] != "pass" and any(item["kind"] == "invalid_missing_or_blank_png" for item in blank_report["issues"]),
        "contract_only_plugin_rejected": plan_only_report["decision"] != "pass",
        "citation_negation_rejected": negation["polarity_consistency"] == "possible_negation_mismatch",
        "citation_numeric_mismatch_rejected": numeric["numeric_consistency"] == "unsupported_or_mismatched",
        "citation_causal_reversal_rejected": causal["causal_direction_consistency"] == "reversed_direction",
    }
    _assert(all(checks.values()), "One or more v0.23.0 adversarial scientific regressions were not rejected")
    return {"status": "passed", "checks": checks, "plan_only_decision": plan_only_report["decision"]}


def run_release_regressions(output_root: str | Path) -> dict[str, Any]:
    root = Path(output_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    domains = [run_domain_regression(root, name) for name in FIXTURE_NAMES]
    adversarial = run_adversarial_regressions(root, domains[0]["project_path"])
    from .cohort_semantics import validate_cohort_registries
    from .executable_analysis import validate_analysis_spec, validate_run_selection_policy

    semantic_checks = {
        "cohort_view_count_mismatch_rejected": validate_cohort_registries(
            {"cohorts": [{"cohort_id": "all", "sample_unit": "subject", "count": 20}]},
            {"views": [{"cohort_view_id": "complete", "parent_cohort_id": "all", "sample_unit": "subject", "count": 19, "missingness_policy": "complete_case", "allowed_uses": ["regression"]}]},
            [{"artifact_id": "panel", "cohort_view_id": "complete", "sample_unit": "subject", "count": 20}],
        ).get("decision") == "blocked",
        "calibration_definition_drift_rejected": any(
            item.get("code") == "calibration_definition_implementation_mismatch"
            for item in validate_analysis_spec({
                "analysis_spec_id": "analysis:calibration", "estimand_id": "estimand:ece", "cohort_view_id": "view:test",
                "sample_unit": "observation", "split_id": "test", "implementation_entry_point": "methods/src/calibration.py",
                "calibration": {"definition": "event_probability_ece", "implementation_definition": "confidence_accuracy_ece"},
            })
        ),
        "unlocked_best_seed_rejected": any(
            item.get("code") == "post_hoc_best_seed_primary"
            for item in validate_run_selection_policy({"selection_role": "primary", "aggregation_policy": "best_seed", "test_access_policy": "single_access", "locked_before_test_access": False})
        ),
    }
    _assert(all(semantic_checks.values()), "One or more v0.30.0 scientific semantic regressions were not rejected")
    report = {
        "schema_version": "dpl.release_regression.v3",
        "generated_at": utc_now(),
        "status": "passed" if all(item["status"] == "passed" for item in domains) and adversarial["status"] == "passed" else "failed",
        "domain_regressions": domains,
        "adversarial_regressions": adversarial,
        "semantic_contract_regressions": semantic_checks,
        "quality_claim_policy": "Synthetic regressions prove scientific contracts, not manuscript quality. A 95% claim remains blocked until the blind complete-manuscript and real-figure evaluation contract is supplied.",
    }
    atomic_write_json(root / "v0260_release_regression_report.json", report)
    atomic_write_json(root / "v0280_release_regression_report.json", report)
    atomic_write_json(root / "v0300_release_regression_report.json", report)
    atomic_write_json(root / "v0250_release_regression_report.json", report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = run_release_regressions(args.output)
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
