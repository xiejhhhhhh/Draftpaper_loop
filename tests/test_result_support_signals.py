from __future__ import annotations

import hashlib
import json

import pytest

from draftpaper_cli.project_scaffold import create_project


def _json(path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_fixed_signal_adapters_prefer_current_resolved_evidence_over_run_and_table(tmp_path) -> None:
    from draftpaper_cli.result_support_signals import SIGNAL_ADAPTERS, collect_result_support_signals

    project = create_project(root=tmp_path, idea="Signal priority", field="machine learning").path
    table = project / "results" / "tables" / "selected_metrics.csv"
    table.write_text(
        "run_id,model_id,metric,value\n"
        "run-current,logistic_baseline,f1_macro,0.61\n"
        "run-current,transformer_full,f1_macro,0.62\n"
        "run-old,transformer_full,f1_macro,0.99\n",
        encoding="utf-8",
    )
    _json(project / "methods" / "run_manifest.yaml", {
        "status": "success",
        "run_id": "run-current",
        "metrics": {"logistic_baseline_f1_macro": 0.71, "transformer_full_f1_macro": 0.72},
        "output_files": ["results/tables/selected_metrics.csv"],
    })
    _json(project / "results" / "resolved_result_evidence.json", {
        "status": "resolved",
        "run_id": "run-current",
        "metrics": [
            {"run_id": "run-current", "model": "logistic_baseline", "metric_name": "f1_macro", "value": 0.81},
            {"run_id": "run-current", "model": "transformer_full", "metric_name": "f1_macro", "value": 0.80},
        ],
    })

    result = collect_result_support_signals(project)

    assert SIGNAL_ADAPTERS == (
        "current_resolved_evidence_metrics",
        "selected_run_manifest_metrics",
        "run_bound_result_table_metrics",
        "current_bound_pending_tasks",
        "required_data_role_bindings",
        "required_evidence_role_bindings",
    )
    assert result["metrics"]["logistic_baseline_f1_macro"] == 0.81
    assert result["metrics"]["transformer_full_f1_macro"] == 0.80
    assert result["metric_sources"]["transformer_full_f1_macro"] == "current_resolved_evidence_metrics"
    assert result["selected_run_id"] == "run-current"


def test_stale_resolved_evidence_is_ignored_and_run_manifest_beats_bound_table(tmp_path) -> None:
    from draftpaper_cli.result_support_signals import collect_result_support_signals

    project = create_project(root=tmp_path, idea="Stale resolved metrics", field="machine learning").path
    table = project / "results" / "tables" / "selected_metrics.csv"
    table.write_text("run_id,metric,value\nrun-current,f1,0.44\nrun-old,f1,0.99\n", encoding="utf-8")
    _json(project / "methods" / "run_manifest.yaml", {
        "status": "success", "run_id": "run-current", "metrics": {"f1": 0.55},
        "tables_generated": ["results/tables/selected_metrics.csv"],
    })
    _json(project / "results" / "resolved_result_evidence.json", {
        "status": "resolved", "run_id": "run-old", "metrics": [{"metric_name": "f1", "value": 0.99}],
    })

    result = collect_result_support_signals(project)

    assert result["metrics"]["f1"] == 0.55
    assert result["metric_sources"]["f1"] == "selected_run_manifest_metrics"
    assert result["signals"]["current_resolved_evidence_metrics"]["current"] is False


def test_real_yaml_run_manifest_is_parsed(tmp_path) -> None:
    from draftpaper_cli.result_support_signals import collect_result_support_signals

    project = create_project(root=tmp_path, idea="YAML run manifest", field="machine learning").path
    (project / "methods" / "run_manifest.yaml").write_text(
        "status: success\nrun_id: run-yaml\nmetrics:\n  f1_macro: 0.73\n",
        encoding="utf-8",
    )

    result = collect_result_support_signals(project)

    assert result["selected_run_id"] == "run-yaml"
    assert result["metrics"]["f1_macro"] == 0.73
    assert result["metric_sources"]["f1_macro"] == "selected_run_manifest_metrics"


def test_success_manifest_without_run_id_is_blocking_and_contributes_no_metrics(tmp_path) -> None:
    from draftpaper_cli.result_support_signals import collect_result_support_signals

    project = create_project(root=tmp_path, idea="Runless scientific evidence", field="machine learning").path
    _json(project / "methods" / "run_manifest.yaml", {
        "status": "success",
        "metrics": {"baseline_f1": 0.70, "proposed_f1": 0.90},
    })

    result = collect_result_support_signals(project)

    assert result["selected_run_id"] == ""
    assert result["metrics"] == {}
    assert result["metric_records"] == []
    assert result["signals"]["selected_run_manifest_metrics"]["current"] is False
    assert any(
        item["code"] == "selected_run_id_missing"
        and item["source"] == "methods/run_manifest.yaml"
        for item in result["blocking_diagnostics"]
    )
    assert result["route_required"] is True


@pytest.mark.parametrize(
    "manifest_payload",
    [
        None,
        {},
        {"status": "failed", "run_id": "run-failed"},
        {"status": "pending", "run_id": "run-pending"},
    ],
)
def test_every_state_without_a_selected_run_is_blocking(tmp_path, manifest_payload) -> None:
    from draftpaper_cli.result_support_signals import collect_result_support_signals

    project = create_project(root=tmp_path, idea="Always require selected run", field="machine learning").path
    manifest = project / "methods" / "run_manifest.yaml"
    if manifest_payload is None:
        manifest.unlink(missing_ok=True)
    else:
        _json(manifest, manifest_payload)

    result = collect_result_support_signals(project)

    assert result["selected_run_id"] == ""
    assert any(
        item["code"] == "selected_run_id_missing"
        and item["source"] == "methods/run_manifest.yaml"
        for item in result["blocking_diagnostics"]
    )
    assert result["route_required"] is True


def test_result_support_mapping_reader_accepts_yaml_artifacts(tmp_path) -> None:
    from draftpaper_cli.result_support import _read_json

    path = tmp_path / "result_manifest.yaml"
    path.write_text("figures:\n  - id: fig_01\n    result_claim: bounded finding\n", encoding="utf-8")

    assert _read_json(path, {})["figures"][0]["id"] == "fig_01"


def test_pending_task_routes_only_when_current_input_binding_matches(tmp_path) -> None:
    from draftpaper_cli.result_support_signals import collect_result_support_signals

    project = create_project(root=tmp_path, idea="Task binding", field="machine learning").path
    run_manifest = project / "methods" / "run_manifest.yaml"
    _json(run_manifest, {"status": "success", "run_id": "run-current"})
    _json(project / "review" / "actionable_analysis_tasks.json", {
        "status": "analysis_revision_prepared",
        "tasks": [
            {
                "task_id": "T-current",
                "status": "pending",
                "current": True,
                "input_bindings": {"methods/run_manifest.yaml": _sha256(run_manifest)},
            },
            {
                "task_id": "T-stale",
                "status": "pending",
                "current": True,
                "input_bindings": {"methods/run_manifest.yaml": "0" * 64},
            },
            {
                "task_id": "T-unbound",
                "status": "pending",
                "current": True,
            },
        ],
    })

    result = collect_result_support_signals(project)

    assert [item["task_id"] for item in result["pending_tasks"]] == ["T-current"]
    assert result["route_required"] is True


def test_project_bound_pending_task_keeps_the_assessed_checkpoint_digest(tmp_path) -> None:
    from draftpaper_cli.result_support import assess_result_support
    from draftpaper_cli.result_support_signals import build_result_support_input_bindings

    project = create_project(root=tmp_path, idea="Stable pending-task binding", field="machine learning").path
    _json(project / "results" / "result_validity_report.json", {
        "decision": "pass",
        "evidence_strength": "meets_threshold",
    })
    _json(project / "research_plan" / "claim_contract.json", {
        "claims": [{"claim_id": "exploratory", "claim_text": "The current analysis is exploratory."}],
    })
    _json(project / "methods" / "run_manifest.yaml", {"status": "success", "run_id": "run-current"})
    project_digest = build_result_support_input_bindings(project)["project.json"]
    _json(project / "review" / "actionable_analysis_tasks.json", {
        "tasks": [{
            "task_id": "project-bound-task",
            "status": "pending",
            "current": True,
            "required": True,
            "input_bindings": {"project.json": project_digest},
        }],
    })

    assess_result_support(project)
    report = json.loads(
        (project / "results" / "result_support_checkpoint.json").read_text(encoding="utf-8")
    )

    assert any(
        item["claim_id"] == "project-bound-task"
        and item["failure_type"] == "current_bound_pending_task"
        for item in report["claim_assessments"]
    )
    assert report["input_bindings"]["project.json"] == project_digest


def test_missing_required_role_creates_unbound_required_data_task(tmp_path) -> None:
    from draftpaper_cli.result_support_signals import collect_result_support_signals

    project = create_project(root=tmp_path, idea="Missing role binding", field="machine learning").path
    _json(project / "methods" / "run_manifest.yaml", {"status": "success", "run_id": "run-current"})
    _json(project / "data" / "data_role_coverage_report.json", {
        "required_roles": ["external_validation"],
        "available_roles": [],
        "role_bindings": {},
    })

    result = collect_result_support_signals(project)

    assert result["route_required"] is True
    assert result["unbound_required_data_tasks"] == [{
        "task_id": "unbound_required_data_task:external_validation",
        "task_type": "unbound_required_data_task",
        "status": "pending",
        "required_role": "external_validation",
        "selected_route": "supplement_data_and_method",
    }]


@pytest.mark.parametrize(
    ("binding_state", "expected_code"),
    [
        (None, None),
        ("pending", "role_binding_state_not_covered"),
        ("stale", "role_binding_state_not_covered"),
    ],
)
def test_claim_contract_missing_pending_or_stale_required_evidence_role_gates_result_support(
    tmp_path, binding_state, expected_code
) -> None:
    from draftpaper_cli.result_support_signals import collect_result_support_signals

    project = create_project(root=tmp_path, idea="Required evidence role", field="machine learning").path
    evidence = project / "results" / "tables" / "performance.csv"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text("metric,value\nf1,0.8\n", encoding="utf-8")
    _json(project / "methods" / "run_manifest.yaml", {"status": "success", "run_id": "run-current"})
    _json(project / "research_plan" / "claim_contract.json", {
        "claims": [{
            "claim_id": "claim-performance",
            "claim_text": "The analysis is exploratory.",
            "required_evidence_roles": ["performance_metric"],
        }],
    })
    if binding_state is not None:
        _json(project / "data" / "data_role_coverage_report.json", {
            "role_bindings": {
                "performance_metric": {
                    "state": binding_state,
                    "evidence": {
                        "path": "results/tables/performance.csv",
                        "sha256": _sha256(evidence),
                        "run_id": "run-current",
                    },
                },
            },
        })

    result = collect_result_support_signals(project)

    assert result["route_required"] is True
    assert result["unbound_required_evidence_tasks"] == [{
        "task_id": "unbound_required_evidence_task:performance_metric",
        "task_type": "unbound_required_evidence_task",
        "status": "pending",
        "required_evidence_role": "performance_metric",
        "selected_route": "supplement_data_and_method",
    }]
    signal = result["signals"]["required_evidence_role_bindings"]
    assert signal["required_evidence_roles"] == ["performance_metric"]
    assert signal["unbound_required_evidence_roles"] == ["performance_metric"]
    if expected_code:
        assert any(item["code"] == expected_code for item in signal["binding_diagnostics"])


def test_claim_contract_covered_required_evidence_role_is_current_and_does_not_gate(tmp_path) -> None:
    from draftpaper_cli.result_support_signals import collect_result_support_signals

    project = create_project(root=tmp_path, idea="Covered evidence role", field="machine learning").path
    evidence = project / "results" / "tables" / "performance.csv"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text("metric,value\nf1,0.8\n", encoding="utf-8")
    _json(project / "methods" / "run_manifest.yaml", {"status": "success", "run_id": "run-current"})
    _json(project / "research_plan" / "claim_contract.json", {
        "claims": [{"claim_id": "claim-performance", "required_evidence_roles": ["performance_metric"]}],
    })
    _json(project / "data" / "data_role_coverage_report.json", {
        "role_bindings": {
            "performance_metric": {
                "state": "covered",
                "evidence": {
                    "path": "results/tables/performance.csv",
                    "sha256": _sha256(evidence),
                    "run_id": "run-current",
                },
            },
        },
    })

    result = collect_result_support_signals(project)

    assert result["unbound_required_evidence_tasks"] == []
    signal = result["signals"]["required_evidence_role_bindings"]
    assert signal["bound_evidence_roles"] == ["performance_metric"]
    assert signal["unbound_required_evidence_roles"] == []
    assert result["route_required"] is False


def test_required_role_binding_is_not_current_without_a_selected_run(tmp_path) -> None:
    from draftpaper_cli.result_support_signals import collect_result_support_signals

    project = create_project(root=tmp_path, idea="Runless role binding", field="machine learning").path
    evidence = project / "results" / "tables" / "performance.csv"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text("metric,value\nf1,0.8\n", encoding="utf-8")
    _json(project / "methods" / "run_manifest.yaml", {"status": "success"})
    _json(project / "research_plan" / "claim_contract.json", {
        "claims": [{"claim_id": "claim-performance", "required_evidence_roles": ["performance_metric"]}],
    })
    _json(project / "data" / "data_role_coverage_report.json", {
        "role_bindings": {
            "performance_metric": {
                "state": "covered",
                "evidence": {
                    "path": "results/tables/performance.csv",
                    "sha256": _sha256(evidence),
                    "run_id": "run-unselected",
                },
            },
        },
    })

    result = collect_result_support_signals(project)

    signal = result["signals"]["required_evidence_role_bindings"]
    assert signal["bound_evidence_roles"] == []
    assert signal["unbound_required_evidence_roles"] == ["performance_metric"]
    assert any(item["code"] == "role_binding_selected_run_missing" for item in signal["binding_diagnostics"])


@pytest.mark.parametrize(
    ("missing_field", "expected_code"),
    [
        ("cohort_id", "role_binding_cohort_unbound"),
        ("snapshot_id", "role_binding_snapshot_unbound"),
    ],
)
def test_required_role_binding_requires_declared_claim_evidence_context(
    tmp_path, missing_field, expected_code
) -> None:
    from draftpaper_cli.result_support_signals import collect_result_support_signals

    project = create_project(root=tmp_path, idea="Claim-bound role context", field="machine learning").path
    evidence = project / "results" / "tables" / "performance.csv"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text("metric,value\nf1,0.8\n", encoding="utf-8")
    _json(project / "methods" / "run_manifest.yaml", {"status": "success", "run_id": "run-current"})
    _json(project / "research_plan" / "claim_contract.json", {
        "claims": [{
            "claim_id": "claim-performance",
            "required_evidence_roles": ["performance_metric"],
            "evidence_context": {
                "cohort_id": "cohort-current",
                "snapshot_id": "snapshot-current",
            },
        }],
    })
    binding_context = {
        "cohort_id": "cohort-current",
        "snapshot_id": "snapshot-current",
    }
    binding_context.pop(missing_field)
    _json(project / "data" / "data_role_coverage_report.json", {
        "role_bindings": {
            "performance_metric": {
                "state": "covered",
                "evidence": {
                    "path": "results/tables/performance.csv",
                    "sha256": _sha256(evidence),
                    "run_id": "run-current",
                    **binding_context,
                },
            },
        },
    })

    result = collect_result_support_signals(project)

    signal = result["signals"]["required_evidence_role_bindings"]
    assert signal["bound_evidence_roles"] == []
    assert any(item["code"] == expected_code for item in signal["binding_diagnostics"])


@pytest.mark.parametrize(
    ("claim_context", "run_context", "promoted_context", "expected_code"),
    [
        (
            {"cohort_id": "cohort-declared"},
            {"cohort_id": "cohort-current"},
            {},
            "role_current_cohort_mismatch",
        ),
        (
            {"snapshot_id": "snapshot-declared"},
            {},
            {"snapshot_id": "snapshot-current"},
            "role_current_snapshot_mismatch",
        ),
    ],
)
def test_claim_declared_role_context_is_not_replaced_by_current_context(
    tmp_path, claim_context, run_context, promoted_context, expected_code
) -> None:
    from draftpaper_cli.result_support_signals import collect_result_support_signals

    project = create_project(root=tmp_path, idea="Preserve claim role context", field="machine learning").path
    evidence = project / "results" / "tables" / "performance.csv"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text("metric,value\nf1,0.8\n", encoding="utf-8")
    _json(project / "methods" / "run_manifest.yaml", {
        "status": "success",
        "run_id": "run-current",
        **run_context,
    })
    if promoted_context:
        _json(project / "results" / "promoted_evidence_snapshot.json", promoted_context)
    _json(project / "research_plan" / "claim_contract.json", {
        "claims": [{
            "claim_id": "claim-declared-context",
            "required_evidence_roles": ["performance_metric"],
            "evidence_context": claim_context,
        }],
    })
    _json(project / "data" / "data_role_coverage_report.json", {
        "role_bindings": {
            "performance_metric": {
                "state": "covered",
                "evidence": {
                    "path": "results/tables/performance.csv",
                    "sha256": _sha256(evidence),
                    "run_id": "run-current",
                    **run_context,
                    **promoted_context,
                },
            },
        },
    })

    result = collect_result_support_signals(project)

    signal = result["signals"]["required_evidence_role_bindings"]
    assert signal["bound_evidence_roles"] == []
    assert signal["unbound_required_evidence_roles"] == ["performance_metric"]
    assert any(item["code"] == expected_code for item in signal["binding_diagnostics"])


def test_conflicting_claim_contexts_create_separate_role_obligations(tmp_path) -> None:
    from draftpaper_cli.result_support_signals import collect_result_support_signals

    project = create_project(root=tmp_path, idea="Claim scoped role obligations", field="machine learning").path
    evidence = project / "results" / "tables" / "performance.csv"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text("metric,value\nf1,0.8\n", encoding="utf-8")
    _json(project / "methods" / "run_manifest.yaml", {
        "status": "success",
        "run_id": "run-current",
        "cohort_id": "cohort-a",
    })
    _json(project / "results" / "promoted_evidence_snapshot.json", {"snapshot_id": "snapshot-a"})
    _json(project / "research_plan" / "claim_contract.json", {
        "claims": [
            {
                "claim_id": "claim-a",
                "required_evidence_roles": ["performance_metric"],
                "evidence_context": {"cohort_id": "cohort-a", "snapshot_id": "snapshot-a"},
            },
            {
                "claim_id": "claim-b",
                "required_evidence_roles": ["performance_metric"],
                "evidence_context": {"cohort_id": "cohort-b", "snapshot_id": "snapshot-b"},
            },
        ],
    })
    _json(project / "data" / "data_role_coverage_report.json", {
        "role_bindings": {
            "performance_metric": {
                "state": "covered",
                "evidence": {
                    "path": "results/tables/performance.csv",
                    "sha256": _sha256(evidence),
                    "run_id": "run-current",
                    "cohort_id": "cohort-a",
                    "snapshot_id": "snapshot-a",
                },
            },
        },
    })

    result = collect_result_support_signals(project)

    signal = result["signals"]["required_evidence_role_bindings"]
    assert [item["claim_id"] for item in signal["required_obligations"]] == ["claim-a", "claim-b"]
    assert [item["claim_id"] for item in signal["bound_obligations"]] == ["claim-a"]
    assert [item["claim_id"] for item in signal["unbound_required_obligations"]] == ["claim-b"]
    assert len(result["unbound_required_evidence_tasks"]) == 1
    assert result["unbound_required_evidence_tasks"][0]["claim_id"] == "claim-b"
    assert result["route_required"] is True


def test_optional_missing_role_does_not_create_a_required_route(tmp_path) -> None:
    from draftpaper_cli.result_support_signals import collect_result_support_signals

    project = create_project(root=tmp_path, idea="Optional missing role", field="machine learning").path
    _json(project / "methods" / "run_manifest.yaml", {"status": "success", "run_id": "run-current"})
    _json(project / "data" / "data_role_coverage_report.json", {
        "required_roles": [],
        "missing_roles": ["optional_external_archive"],
        "role_bindings": {},
    })

    result = collect_result_support_signals(project)

    assert result["unbound_required_data_tasks"] == []
    assert result["route_required"] is False


def test_route_preflight_rejects_a_new_relevant_input_after_checkpoint(tmp_path) -> None:
    from draftpaper_cli.result_support import (
        ResultSupportError,
        result_route_preflight,
        result_support_checkpoint_sha256,
    )
    from draftpaper_cli.result_support_signals import build_result_support_input_bindings

    project = create_project(root=tmp_path, idea="New input invalidates route", field="machine learning").path
    _json(project / "methods" / "run_manifest.yaml", {"status": "success", "run_id": "run-current"})
    report = {
        "schema_version": "dpl.result_support_checkpoint.v3",
        "project_id": "project:test",
        "assessment_decision": "route_decision_required",
        "assessment_support_level": "partial",
        "metrics": {},
        "metric_sources": {},
        "claim_assessments": [],
        "failed_claims": [],
        "signals": {},
        "input_bindings": build_result_support_input_bindings(project),
        "selected_route": None,
        "route_receipt": None,
    }
    report["checkpoint_sha256"] = result_support_checkpoint_sha256(report)
    _json(project / "data" / "data_acquisition_tasks.json", {"tasks": []})

    with pytest.raises(ResultSupportError, match="inputs changed"):
        result_route_preflight(
            project,
            report,
            route="supplement_data_and_method",
            checkpoint_hash=report["checkpoint_sha256"],
        )


def test_route_commands_are_hash_bound_human_checkpoints_and_schema_registers_v3() -> None:
    from draftpaper_cli.cli import build_parser
    from draftpaper_cli.command_registry import COMMAND_SPECS

    parser = build_parser()
    downgrade = parser.parse_args([
        "apply-result-downgrade", "--project", "PROJECT", "--checkpoint-hash", "HASH",
    ])
    rescue = parser.parse_args([
        "prepare-result-rescue", "--project", "PROJECT", "--checkpoint-hash", "HASH",
    ])
    assert downgrade.checkpoint_hash == "HASH"
    assert rescue.checkpoint_hash == "HASH"
    for name in ("apply-result-downgrade", "prepare-result-rescue"):
        spec = COMMAND_SPECS[name]
        assert spec.protected_action is True
        assert spec.manual_only is True
        assert spec.confirmation_policy == "checkpoint_hash"
        assert spec.mcp_exposed is False

    registry = json.loads(
        open("draftpaper_cli/resources/schemas/schema_registry.json", encoding="utf-8").read()
    )
    assert registry["families"]["result_support_checkpoint"] == {
        "current": "dpl.result_support_checkpoint.v3",
        "accepted": ["dpl.result_support_checkpoint.v2"],
    }


def test_selected_run_rejects_unbound_and_mismatched_resolved_metrics_with_blocking_diagnostics(tmp_path) -> None:
    from draftpaper_cli.result_support_signals import collect_result_support_signals

    project = create_project(root=tmp_path, idea="Strict run binding", field="machine learning").path
    _json(project / "methods" / "run_manifest.yaml", {
        "status": "success",
        "run_id": "run-current",
        "metrics": {"f1": 0.55},
    })
    _json(project / "results" / "resolved_result_evidence.json", {
        "status": "resolved",
        "metrics": [
            {"metric_name": "f1", "value": 0.99},
            {"run_id": "run-old", "metric_name": "auc", "value": 0.98},
        ],
        "primary_metric": {"run_id": "run-current", "metric_name": "auc", "value": 0.97},
    })

    result = collect_result_support_signals(project)

    assert result["metrics"] == {"f1": 0.55}
    assert result["metric_sources"] == {"f1": "selected_run_manifest_metrics"}
    assert {item["code"] for item in result["blocking_diagnostics"]} == {
        "resolved_evidence_run_unbound",
        "resolved_metric_run_mismatch",
    }
    assert all(item["blocking"] is True for item in result["blocking_diagnostics"])


def test_selected_run_rejects_manifest_metric_declaring_another_run(tmp_path) -> None:
    from draftpaper_cli.result_support_signals import collect_result_support_signals

    project = create_project(root=tmp_path, idea="Manifest metric run mismatch", field="machine learning").path
    _json(project / "methods" / "run_manifest.yaml", {
        "status": "success",
        "run_id": "run-current",
        "split": "test",
        "metrics": {
            "f1": {"value": 0.99, "run_id": "run-old"},
            "auc": {"value": 0.72},
        },
    })

    result = collect_result_support_signals(project)

    assert result["metrics"] == {"auc": 0.72}
    assert result["metric_records"][0]["context"]["run_id"] == "run-current"
    assert any(
        item["code"] == "manifest_metric_run_mismatch"
        and item["observed_run_id"] == "run-old"
        for item in result["blocking_diagnostics"]
    )


def test_selected_run_rejects_unbound_csv_rows_and_binds_every_declared_csv_input(tmp_path) -> None:
    from draftpaper_cli.result_support_signals import collect_result_support_signals

    project = create_project(root=tmp_path, idea="CSV run binding", field="machine learning").path
    bound = project / "results" / "tables" / "bound.csv"
    unbound = project / "results" / "tables" / "unbound.csv"
    bound.parent.mkdir(parents=True, exist_ok=True)
    bound.write_text("run_id,metric,value\nrun-current,auc,0.72\n", encoding="utf-8")
    unbound.write_text("metric,value\nf1,0.99\n", encoding="utf-8")
    _json(project / "methods" / "run_manifest.yaml", {
        "status": "success",
        "run_id": "run-current",
        "tables_generated": [
            "results/tables/bound.csv",
            "results/tables/unbound.csv",
        ],
    })

    result = collect_result_support_signals(project)

    assert result["metrics"] == {"auc": 0.72}
    assert result["input_bindings"]["results/tables/bound.csv"] == _sha256(bound)
    assert result["input_bindings"]["results/tables/unbound.csv"] == _sha256(unbound)
    assert any(
        item["code"] == "table_metric_run_unbound"
        and item["source"] == "results/tables/unbound.csv"
        for item in result["blocking_diagnostics"]
    )


def test_checkpoint_input_bindings_include_post_results_review_and_reopen_request(tmp_path) -> None:
    from draftpaper_cli.result_support import RESULT_SUPPORT_INPUTS
    from draftpaper_cli.result_support_signals import build_result_support_input_bindings

    project = create_project(root=tmp_path, idea="Post Results inputs", field="machine learning").path
    paths = {
        "research_plan/pre_execution_rescue_tasks.json": {"tasks": []},
        "review/result_support_reopen_request.json": {"status": "requested"},
        "review/result_discipline_review_report.json": {"decision": "repair_required"},
    }
    for relative, payload in paths.items():
        _json(project / relative, payload)

    bindings = build_result_support_input_bindings(project)

    assert set(paths) <= set(RESULT_SUPPORT_INPUTS)
    assert set(paths) <= set(bindings)


def test_result_support_inputs_are_the_single_exact_fixed_consumed_input_source() -> None:
    from draftpaper_cli.result_support import RESULT_SUPPORT_INPUTS
    from draftpaper_cli.result_support_signals import RESULT_SUPPORT_INPUTS as SIGNAL_INPUTS

    expected = (
        "project.json",
        "results/result_validity_report.json",
        "research_plan/claim_contract.json",
        "research_plan/figure_storyboard.json",
        "results/result_manifest.yaml",
        "methods/run_manifest.yaml",
        "results/resolved_result_evidence.json",
        "data/data_role_coverage_report.json",
        "research_plan/plugin_binding_plan.json",
        "review/actionable_analysis_tasks.json",
        "data/data_acquisition_tasks.json",
        "research_plan/pre_execution_rescue_tasks.json",
        "review/result_support_reopen_request.json",
        "review/result_discipline_review_report.json",
        "results/results.tex",
        "results/promoted_evidence_snapshot.json",
        "results/figure_plugin_trace_report.json",
    )

    assert RESULT_SUPPORT_INPUTS is SIGNAL_INPUTS
    assert RESULT_SUPPORT_INPUTS == expected


def test_assessed_route_is_current_then_invalidates_when_results_stage_metadata_changes(tmp_path) -> None:
    from draftpaper_cli.project_state import update_stage_status
    from draftpaper_cli.result_support import ResultSupportError, assess_result_support, result_route_preflight
    from draftpaper_cli.result_support_signals import build_result_support_input_bindings

    project = create_project(root=tmp_path, idea="Results-stage route binding", field="machine learning").path
    _json(project / "results" / "result_validity_report.json", {
        "decision": "pass", "evidence_strength": "meets_threshold",
    })
    _json(project / "research_plan" / "claim_contract.json", {
        "claims": [{"claim_id": "improvement", "claim_text": "The proposed model improves over baseline."}],
    })
    _json(project / "methods" / "run_manifest.yaml", {
        "status": "success", "run_id": "run-current",
        "metrics": {"baseline_f1": 0.9, "proposed_f1": 0.8},
    })
    update_stage_status(project, "results", "draft")
    assessed = assess_result_support(project)
    report = json.loads((project / "results" / "result_support_checkpoint.json").read_text(encoding="utf-8"))

    assert "project.json" in report["input_bindings"]
    assert result_route_preflight(
        project,
        report,
        route="supplement_data_and_method",
        checkpoint_hash=assessed["checkpoint_sha256"],
    ) is None

    update_stage_status(project, "results", "approved")

    assert build_result_support_input_bindings(project)["project.json"] != report["input_bindings"]["project.json"]
    with pytest.raises(ResultSupportError, match="project.json"):
        result_route_preflight(
            project,
            report,
            route="supplement_data_and_method",
            checkpoint_hash=assessed["checkpoint_sha256"],
        )


def test_required_role_counts_only_with_current_covered_evidence_binding(tmp_path) -> None:
    from draftpaper_cli.result_support_signals import collect_result_support_signals

    project = create_project(root=tmp_path, idea="Current required role", field="machine learning").path
    evidence = project / "data" / "external_validation.csv"
    evidence.write_text("subject,label\n1,1\n", encoding="utf-8")
    _json(project / "methods" / "run_manifest.yaml", {
        "status": "success",
        "run_id": "run-current",
        "cohort_id": "cohort-current",
    })
    _json(project / "results" / "promoted_evidence_snapshot.json", {"snapshot_id": "snapshot-current"})
    _json(project / "data" / "data_role_coverage_report.json", {
        "required_roles": ["external_validation"],
        "role_bindings": {
            "external_validation": {
                "state": "covered_project_local",
                "evidence": {
                    "path": "data/external_validation.csv",
                    "sha256": _sha256(evidence),
                    "run_id": "run-current",
                    "cohort_id": "cohort-current",
                    "snapshot_id": "snapshot-current",
                },
            },
        },
    })

    result = collect_result_support_signals(project)

    role_signal = result["signals"]["required_data_role_bindings"]
    assert role_signal["bound_roles"] == ["external_validation"]
    assert role_signal["unbound_required_roles"] == []
    assert role_signal["binding_diagnostics"] == []
    assert result["input_bindings"]["data/external_validation.csv"] == _sha256(evidence)
    assert "results/promoted_evidence_snapshot.json" in result["input_bindings"]


@pytest.mark.parametrize(
    ("state", "overrides", "code"),
    [
        ("pending", {}, "role_binding_state_not_covered"),
        ("covered", {"sha256": "0" * 64}, "role_binding_hash_mismatch"),
        ("covered", {"run_id": "run-old"}, "role_binding_run_mismatch"),
        ("covered", {"cohort_id": "cohort-old"}, "role_binding_cohort_mismatch"),
        ("covered", {"snapshot_id": "snapshot-old"}, "role_binding_snapshot_mismatch"),
    ],
)
def test_required_role_rejects_pending_stale_or_context_mismatched_bindings(tmp_path, state, overrides, code) -> None:
    from draftpaper_cli.result_support_signals import collect_result_support_signals

    project = create_project(root=tmp_path, idea="Invalid required role", field="machine learning").path
    evidence = project / "data" / "external_validation.csv"
    evidence.write_text("subject,label\n1,1\n", encoding="utf-8")
    _json(project / "methods" / "run_manifest.yaml", {
        "status": "success",
        "run_id": "run-current",
        "cohort_id": "cohort-current",
    })
    _json(project / "results" / "promoted_evidence_snapshot.json", {"snapshot_id": "snapshot-current"})
    evidence_binding = {
        "path": "data/external_validation.csv",
        "sha256": _sha256(evidence),
        "run_id": "run-current",
        "cohort_id": "cohort-current",
        "snapshot_id": "snapshot-current",
        **overrides,
    }
    _json(project / "data" / "data_role_coverage_report.json", {
        "required_roles": ["external_validation"],
        "role_bindings": {
            "external_validation": {"state": state, "evidence": evidence_binding},
        },
    })

    result = collect_result_support_signals(project)

    role_signal = result["signals"]["required_data_role_bindings"]
    assert role_signal["bound_roles"] == []
    assert role_signal["unbound_required_roles"] == ["external_validation"]
    assert any(item["code"] == code for item in role_signal["binding_diagnostics"])


def test_legacy_flattened_covered_binding_has_explicit_deterministic_compatibility(tmp_path) -> None:
    from draftpaper_cli.result_support_signals import collect_result_support_signals

    project = create_project(root=tmp_path, idea="Legacy role compatibility", field="machine learning").path
    evidence = project / "data" / "legacy.csv"
    evidence.write_text("x\n1\n", encoding="utf-8")
    _json(project / "methods" / "run_manifest.yaml", {
        "status": "success",
        "run_id": "run-current",
        "cohort_id": "cohort-current",
    })
    _json(project / "results" / "promoted_evidence_snapshot.json", {"snapshot_id": "snapshot-current"})
    _json(project / "data" / "data_role_coverage_report.json", {"required_roles": ["external_validation"]})
    _json(project / "research_plan" / "plugin_binding_plan.json", {
        "bindings": [{
            "kind": "data",
            "requirement_id": "data:external_validation",
            "state": "covered",
            "evidence_path": "data/legacy.csv",
            "evidence_sha256": _sha256(evidence),
            "run_id": "run-current",
            "cohort_id": "cohort-current",
            "snapshot_id": "snapshot-current",
        }],
    })

    result = collect_result_support_signals(project)

    role_signal = result["signals"]["required_data_role_bindings"]
    assert role_signal["bound_roles"] == ["external_validation"]
    assert role_signal["accepted_bindings"][0]["compatibility_mode"] == "legacy_flattened_evidence_v1"


@pytest.mark.parametrize("binding_kind", ["data", "evidence"])
def test_plugin_binding_kind_cannot_satisfy_the_other_obligation_kind(tmp_path, binding_kind) -> None:
    from draftpaper_cli.result_support_signals import collect_result_support_signals

    project = create_project(root=tmp_path, idea="Kind-bound role", field="machine learning").path
    evidence = project / "results" / "tables" / "shared.csv"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text("metric,value\nf1,0.8\n", encoding="utf-8")
    _json(project / "methods" / "run_manifest.yaml", {
        "status": "success",
        "run_id": "run-current",
    })
    _json(project / "research_plan" / "claim_contract.json", {
        "claims": [{
            "claim_id": "claim-shared-role",
            "required_data_roles": ["shared_role"],
            "required_evidence_roles": ["shared_role"],
        }],
    })
    _json(project / "research_plan" / "plugin_binding_plan.json", {
        "bindings": [{
            "kind": binding_kind,
            "requirement_id": f"{binding_kind}:shared_role",
            "state": "covered",
            "evidence_path": "results/tables/shared.csv",
            "evidence_sha256": _sha256(evidence),
            "run_id": "run-current",
        }],
    })

    result = collect_result_support_signals(project)

    data_signal = result["signals"]["required_data_role_bindings"]
    evidence_signal = result["signals"]["required_evidence_role_bindings"]
    matching_signal = data_signal if binding_kind == "data" else evidence_signal
    other_signal = evidence_signal if binding_kind == "data" else data_signal
    assert matching_signal["bound_obligations"][0]["requirement_kind"] == binding_kind
    assert matching_signal["accepted_bindings"][0]["binding_kind"] == binding_kind
    assert other_signal["bound_obligations"] == []
    assert other_signal["unbound_required_obligations"][0]["requirement_kind"] != binding_kind
    assert any(
        item["code"] == "role_binding_kind_mismatch"
        for item in other_signal["binding_diagnostics"]
    )


def test_stale_unbound_and_optional_tasks_are_structured_skips_not_silently_dropped(tmp_path) -> None:
    from draftpaper_cli.result_support_signals import collect_result_support_signals

    project = create_project(root=tmp_path, idea="Skipped tasks", field="machine learning").path
    run_manifest = project / "methods" / "run_manifest.yaml"
    _json(run_manifest, {"status": "success", "run_id": "run-current"})
    _json(project / "review" / "actionable_analysis_tasks.json", {
        "tasks": [
            {
                "task_id": "active",
                "status": "pending",
                "current": True,
                "required": True,
                "input_bindings": {"methods/run_manifest.yaml": _sha256(run_manifest)},
            },
            {
                "task_id": "stale",
                "status": "pending",
                "current": True,
                "required": True,
                "input_bindings": {"methods/run_manifest.yaml": "0" * 64},
            },
            {"task_id": "unbound", "status": "pending", "current": True, "required": True},
            {
                "task_id": "optional",
                "status": "pending",
                "current": True,
                "required": False,
                "input_bindings": {"methods/run_manifest.yaml": _sha256(run_manifest)},
            },
            {"task_id": "stale-status", "status": "stale", "required": True},
            {
                "task_id": "unrelated",
                "status": "pending",
                "current": True,
                "required": True,
                "relevant": False,
                "input_bindings": {"methods/run_manifest.yaml": _sha256(run_manifest)},
            },
        ],
    })

    result = collect_result_support_signals(project)

    assert [item["task_id"] for item in result["pending_tasks"]] == ["active"]
    assert {item["task_id"]: item["skip_reason"] for item in result["skipped_tasks"]} == {
        "stale": "input_binding_mismatch",
        "unbound": "missing_input_binding",
        "optional": "optional_task",
        "stale-status": "stale_task",
        "unrelated": "unrelated_task",
    }
    assert {item["code"] for item in result["warnings"]} == {
        "task_input_binding_mismatch",
        "task_missing_input_binding",
        "optional_task_skipped",
        "stale_task_skipped",
        "unrelated_task_skipped",
    }


def test_route_preflight_invalidates_when_consumed_declared_csv_changes(tmp_path) -> None:
    from draftpaper_cli.result_support import ResultSupportError, result_route_preflight, result_support_checkpoint_sha256
    from draftpaper_cli.result_support_signals import build_result_support_input_bindings

    project = create_project(root=tmp_path, idea="Changed consumed CSV", field="machine learning").path
    table = project / "results" / "tables" / "metrics.csv"
    table.parent.mkdir(parents=True, exist_ok=True)
    table.write_text("run_id,metric,value\nrun-current,f1,0.7\n", encoding="utf-8")
    _json(project / "methods" / "run_manifest.yaml", {
        "status": "success",
        "run_id": "run-current",
        "tables_generated": ["results/tables/metrics.csv"],
    })
    report = {
        "schema_version": "dpl.result_support_checkpoint.v3",
        "project_id": "project:test",
        "assessment_decision": "route_decision_required",
        "assessment_support_level": "partial",
        "metrics": {},
        "metric_sources": {},
        "claim_assessments": [],
        "failed_claims": [],
        "signals": {},
        "input_bindings": build_result_support_input_bindings(project),
        "selected_route": None,
        "route_receipt": None,
    }
    report["checkpoint_sha256"] = result_support_checkpoint_sha256(report)
    table.write_text("run_id,metric,value\nrun-current,f1,0.9\n", encoding="utf-8")

    with pytest.raises(ResultSupportError, match="results/tables/metrics.csv"):
        result_route_preflight(
            project,
            report,
            route="supplement_data_and_method",
            checkpoint_hash=report["checkpoint_sha256"],
        )


def test_metric_adapters_preserve_dimension_and_context_records_from_each_source(tmp_path) -> None:
    from draftpaper_cli.result_support_signals import collect_result_support_signals

    project = create_project(root=tmp_path, idea="Structured metric contexts", field="machine learning").path
    table = project / "results" / "tables" / "metrics.csv"
    table.parent.mkdir(parents=True, exist_ok=True)
    table.write_text(
        "run_id,model,metric,value,metric_dimension,cohort,split,sample_unit\n"
        "run-current,table_baseline,table_score,0.70,f1,cohort-a,test,patient\n",
        encoding="utf-8",
    )
    _json(project / "methods" / "run_manifest.yaml", {
        "status": "success",
        "run_id": "run-current",
        "cohort": "cohort-a",
        "split": "test",
        "sample_unit": "patient",
        "metrics": {
            "manifest_score": {
                "value": 0.75,
                "model": "manifest_proposed",
                "metric_dimension": "f1",
            },
        },
        "tables_generated": ["results/tables/metrics.csv"],
    })
    _json(project / "results" / "resolved_result_evidence.json", {
        "status": "resolved",
        "run_id": "run-current",
        "metrics": [{
            "run_id": "run-current",
            "model": "resolved_proposed",
            "metric_name": "resolved_score",
            "metric_dimension": "f1",
            "value": 0.80,
            "cohort": "cohort-a",
            "split": "test",
            "sample_unit": "patient",
        }],
    })

    result = collect_result_support_signals(project)

    records = {item["adapter"]: item for item in result["metric_records"]}
    assert set(records) == {
        "run_bound_result_table_metrics",
        "selected_run_manifest_metrics",
        "current_resolved_evidence_metrics",
    }
    assert all(item["metric_dimension"] == "f1" for item in records.values())
    assert all(item["context"] == {
        "run_id": "run-current",
        "cohort": "cohort-a",
        "split": "test",
        "sample_unit": "patient",
    } for item in records.values())
