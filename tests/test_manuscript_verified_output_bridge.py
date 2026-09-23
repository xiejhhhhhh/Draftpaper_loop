from __future__ import annotations

import hashlib
import json

import pytest

from draftpaper_cli.checkpoint_summary import _hash_payload
from draftpaper_cli.evidence_registry import (
    _confirmed_support_bindings, _metric_context, _records_from_bound_analysis_outputs,
    _records_from_count_identity_report, _verified_result_csv,
)
from draftpaper_cli.review_policy import _decision_hash
from draftpaper_cli.section_contracts import _scope_mentioned, validate_section_writing


def write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metric_record(value, unit="sample_record", cohort="cohort:registered", model="B0", variant="primary", confidence="verified_run_output"):
    return {"evidence_id": f"{unit}:{cohort}:{model}", "run_id": "run-a", "cohort_id": cohort,
            "sample_unit": unit, "split": "not_applicable", "model_id": model,
            "metric_dimension": "count", "value": value, "entity_role": "result_metric_retained_n",
            "analysis_variant": variant, "confidence": confidence, "target_sections": ["results"]}


def test_explicit_unit_precedes_generic_primary_default():
    count = metric_record(3000, variant="typed_count_identity")
    generic = metric_record(3000, unit="figure_evidence", model="not_applicable", confidence="figure_metadata_bound")
    report = validate_section_writing("results", "The registered cohort contained 3000 sample records.", {"records": [generic, count]})
    assert report["decision"] == "pass"
    assert report["numeric_claim_bindings"][0]["evidence_id"] == count["evidence_id"]


def test_wrong_explicit_unit_is_not_rescued_by_equal_value():
    wrong = metric_record(3000, unit="galaxy")
    known = metric_record(5, unit="sample_record")
    report = validate_section_writing("results", "The cohort contained 3000 sample records.", {"records": [wrong, known]})
    assert report["decision"] == "blocked"
    assert report["numeric_claim_bindings"][0]["status"] == "scope_mismatch"


def test_namespace_label_resolves_declared_cohort_without_merging_scopes():
    strict = metric_record(1824, cohort="cohort:complete_aaew_records", model="B4")
    parent = metric_record(1824, cohort="cohort:registered", model="B4")
    report = validate_section_writing("results", "Complete AAEW records comprised 1824 sample records.", {"records": [parent, strict]})
    assert report["decision"] == "pass"
    assert report["numeric_claim_bindings"][0]["binding"]["cohort_id"] == strict["cohort_id"]
    assert not _scope_mentioned("A broader dataset was used.", "cohort:a")
    assert not _scope_mentioned("Some records were retained.", "record")


def test_absent_number_remains_unsupported():
    report = validate_section_writing("results", "B0 retained 9999 sample records.", {"records": [metric_record(3000)]})
    assert report["numeric_claim_bindings"][0]["status"] == "unsupported"


def test_distance_is_not_evidence_for_an_injection_count():
    distance = metric_record(60, unit="reference_polygon", model="not_applicable")
    distance["metric_dimension"] = "metres"
    report = validate_section_writing("results", "The test used 60 injected instances.", {"records": [distance]})
    assert report["decision"] == "blocked"
    assert report["numeric_claim_bindings"][0]["status"] == "metric_dimension_mismatch"


def test_explicit_distance_requires_distance_units():
    count = metric_record(30)
    report = validate_section_writing("results", "The native resolution was 30 m.", {"records": [count]})
    assert report["decision"] == "blocked"


def test_empirical_interval_coverage_is_not_nominal_confidence():
    coverage = metric_record(0.95)
    coverage.update({"metric_dimension": "fraction", "entity_role": "result_metric_empirical_coverage"})
    confidence = metric_record(0.95, model="not_applicable")
    confidence.update({"metric_dimension": "fraction", "entity_role": "result_metric_confidence_interval_level"})
    report = validate_section_writing("results", "B0 had 95\\% of samples inside the interval.", {"records": [confidence, coverage]})
    assert report["decision"] == "pass", report["issues"]
    assert report["numeric_claim_bindings"][0]["evidence_id"] == coverage["evidence_id"]


def bind_run(root, relative, text):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    write(root / "methods/run_manifest.yaml", {"status": "success", "run_id": "run-a", "output_artifact_hashes": {relative: digest(path)}})
    return path


def test_direct_run_csv_requires_hash_and_run_identity(tmp_path):
    relative = "results/tables/metric_evidence.csv"
    path = bind_run(tmp_path, relative, "run_id,value\nrun-a,0.7\n")
    assert len(_verified_result_csv(tmp_path, relative)[0]) == 1
    path.write_text("run_id,value\nrun-a,0.9\n", encoding="utf-8")
    assert _verified_result_csv(tmp_path, relative)[0] == []
    write(tmp_path / "methods/run_manifest.yaml", {"status": "success", "run_id": "run-other", "output_artifact_hashes": {relative: digest(path)}})
    assert _verified_result_csv(tmp_path, relative)[0] == []


def test_unbound_and_outside_csv_are_not_promoted(tmp_path):
    bind_run(tmp_path, "results/tables/declared.csv", "value\n3\n")
    (tmp_path / "results/tables/other.csv").write_text("value\n9\n", encoding="utf-8")
    assert _verified_result_csv(tmp_path, "results/tables/other.csv")[0] == []
    assert _verified_result_csv(tmp_path, "../outside.csv")[0] == []


def seed_consumed_support(root):
    relative = "results/aaew/audit_metrics.csv"
    source = root / relative
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("run_id,variant,retained_n\nrun-a,B4,1824\n", encoding="utf-8")
    write(root / "methods/run_manifest.yaml", {"status": "success", "run_id": "run-a"})
    support_path = root / "results/result_support_checkpoint.json"
    write(support_path, {"decision": "pass", "input_bindings": {relative: digest(source)}})
    manifest = {"artifacts": [{"project_relative_path": "results/result_support_checkpoint.json", "after_byte_sha256": digest(support_path)}]}
    summary = {"artifact_manifest": manifest, "artifact_manifest_sha256": _hash_payload(manifest)}
    summary["stage_summary_sha256"] = _hash_payload(summary)
    package = root / "review/checkpoints/core-test"
    write(package / "stage_summary.json", summary)
    receipt = {"schema_version": "dpl.review_decision_receipt.v2", "checkpoint_hash": "cp-test", "receipt_id": "user-test", "decision_status": "user_confirmed", "summary_sha256": summary["stage_summary_sha256"]}
    receipt["receipt_sha256"] = _decision_hash(receipt)
    write(package / "review_decision_receipt.json", receipt)
    events = [
        {"kind": "checkpoint", "stage": "core_evidence", "hash": "cp-test", "confirmation_subject_id": "subject-test", "stage_summary_json": "review/checkpoints/core-test/stage_summary.json", "stage_summary_sha256": summary["stage_summary_sha256"]},
        {"kind": "resume", "consumes_hash": "cp-test", "decision_receipt_id": "user-test"},
    ]
    (root / "checkpoint_ledger.jsonl").write_text("\n".join(json.dumps(row) for row in events), encoding="utf-8")
    write(root / "core_evidence/core_evidence_report.json", {"human_confirmation_status": "approved", "human_confirmation_subject_id": "subject-test"})
    return relative, source, support_path, package


def test_consumed_package_support_is_accepted(tmp_path):
    relative, _, _, _ = seed_consumed_support(tmp_path)
    assert relative in _confirmed_support_bindings(tmp_path)
    assert _verified_result_csv(tmp_path, relative)[0][0]["retained_n"] == "1824"


@pytest.mark.parametrize("mutation", ["source", "support", "summary", "receipt", "unconsumed"])
def test_mutated_or_unconfirmed_support_is_rejected(tmp_path, mutation):
    relative, source, support, package = seed_consumed_support(tmp_path)
    if mutation == "source":
        source.write_text("run_id,variant,retained_n\nrun-a,B4,999\n", encoding="utf-8")
    elif mutation == "support":
        write(support, {"decision": "pass", "input_bindings": {relative: "forged"}})
    elif mutation == "summary":
        write(package / "stage_summary.json", {"artifact_manifest": {"artifacts": []}, "stage_summary_sha256": "forged"})
    elif mutation == "receipt":
        write(package / "review_decision_receipt.json", {"decision_status": "user_confirmed", "receipt_sha256": "forged"})
    else:
        lines = (tmp_path / "checkpoint_ledger.jsonl").read_text().splitlines()
        (tmp_path / "checkpoint_ledger.jsonl").write_text(lines[0], encoding="utf-8")
    assert _verified_result_csv(tmp_path, relative)[0] == []


def test_verified_intervals_are_bound_without_changing_point_estimates(tmp_path):
    relative = "results/tables/metric_evidence.csv"
    header = "run_id,metric,value,interval_low,interval_high,interval_level,cohort_id,cohort_view_id,estimand_id,analysis_spec_id,sample_unit,model_id,split_id,aggregation_id,uncertainty_definition_id\n"
    row = "run-a,dominant_delta,0.07,0.0565,0.0842,0.95,cohort:polygons,view:polygons,estimand:delta,analysis_spec:method_task_3:test,reference_polygon,inward_buffer_90m,not_applicable,paired_mean,block_bootstrap\n"
    path = bind_run(tmp_path, relative, header + row)
    before = path.read_bytes()
    records = _records_from_bound_analysis_outputs(tmp_path)
    assert {record["value"] for record in records} == {0.0565, 0.0842, 0.95}
    assert all(record["source_hash"] == digest(path) for record in records)
    assert all(record["cohort_id"] == "cohort:polygons" for record in records)
    assert path.read_bytes() == before
    report = validate_section_writing("results", "The interval was [0.0565, 0.0842] at 95\\% confidence.", {"records": records})
    assert report["decision"] == "pass", report["issues"]


def test_b4_reporting_count_uses_declared_reporting_view(tmp_path):
    write(tmp_path / "methods/run_manifest.yaml", {"status": "success", "run_id": "run-a"})
    write(tmp_path / "results/figure_metadata.json", {"figures": [{"cohort_id": "cohort:complete_aaew_records", "cohort_view_id": "view:units", "sample_unit": "reporting_unit"}]})
    write(tmp_path / "methods/executable_analysis_spec.json", {"analysis_specs": [{"cohort_view_id": "view:units", "sample_unit": "reporting_unit", "analysis_spec_id": "analysis_spec:method_task_6:test", "estimand_id": "estimand:units", "split_id": "not_applicable"}]})
    context = _metric_context(tmp_path, cohort_id="cohort:complete_aaew_records", sample_unit="reporting_unit", variant="B4")
    assert context["split_id"] == "not_applicable"
    path = tmp_path / "results/count_identity_report.json"
    write(path, {"status": "passed", "records": [{"count_record_id": "complete_units", "count_definition_id": "complete_aaew_reporting_unit_count", "filter_contract_id": "filter:B4_complete_aaew_v1", "cohort_id": "cohort:complete_aaew_records", "sample_unit": "reporting_unit", "value": 4, "count_mode": "distinct_reporting_unit_count"}]})
    records = _records_from_count_identity_report(path, tmp_path)
    assert len(records) == 1
    assert records[0]["value"] == 4
    assert records[0]["model_id"] == "B4"
    assert records[0]["cohort_view_id"] == "view:units"
