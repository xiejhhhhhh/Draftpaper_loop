from __future__ import annotations

import json
from pathlib import Path

import pytest

from draftpaper_cli.discipline_modules import get_discipline_module
from draftpaper_cli.discipline_modules.registry import list_discipline_modules
from draftpaper_cli.plugin_catalog import build_plugin_catalog_snapshot, normalize_execution_contract, validate_execution_contract
from draftpaper_cli.scientific_plugin_runtime import execute_runnable_fixture, runnable_profiles
from tools.verify_wheel_install import EXPECTED_RELEASE_FIXTURE_IDS, _release_regressions_passed


def test_all_plugins_have_deterministic_valid_execution_contracts() -> None:
    first = build_plugin_catalog_snapshot()
    second = build_plugin_catalog_snapshot()
    assert first["status"] == "passed"
    assert first["plugin_count"] >= 209
    assert first["catalog_hash"] == second["catalog_hash"]
    assert not first["errors"]
    assert all(item["plugin_contract_hash"] for item in first["entries"])


def test_runnable_depth_is_explicit_and_does_not_promote_remote_contracts() -> None:
    profiles = runnable_profiles()
    scientific = [item for item in profiles.values() if item["kind"] in {"data", "method"}]
    reviews = [item for item in profiles.values() if item["kind"] == "review"]
    assert 20 <= len(scientific) <= 30
    assert 8 <= len(reviews) <= 12

    snapshot = build_plugin_catalog_snapshot()
    by_id = {item["plugin_id"]: item for item in snapshot["entries"]}
    assert by_id["exploratory_data_analysis"]["maturity"] == "runnable"
    assert by_id["photon_archive_api_contract"]["maturity"] != "runnable"
    assert by_id["photon_archive_api_contract"]["execution_contract"]["execution_mode"] == "mock_only"


def test_runnable_scientific_fixture_executes_algorithm_and_failure_fixture_fails(tmp_path: Path) -> None:
    ok = tmp_path / "ok.json"
    ok.write_text(json.dumps({"input": {"y_true": [0, 1, 1, 0], "y_pred": [0, 1, 0, 0]}}), encoding="utf-8")
    result = execute_runnable_fixture("scikit_learn_classical_model_selection", tmp_path / "out", fixture_path=ok)
    assert result["execution_status"] == "fixture_executed"
    assert result["output"]["result"]["accuracy"] == 0.75

    failure = tmp_path / "failure.json"
    failure.write_text(json.dumps({"roles": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="omits required scientific roles"):
        execute_runnable_fixture("scikit_learn_classical_model_selection", tmp_path / "failed", fixture_path=failure)


def test_runnable_review_profiles_enter_composite_runtime_with_threshold_sources() -> None:
    module = get_discipline_module("default")
    rules = {item["rule_id"]: item for item in module.spec.review_rule_dicts()}
    rule = rules["statistical_power_gate"]
    assert rule["maturity"] == "runnable"
    assert rule["deployment_state"] == "runtime_integrated"
    assert rule["threshold_source"]["citation_or_note"]
    runnable_rules = {
        rule["rule_id"]
        for module in list_discipline_modules()
        for rule in module.get("review_rule_groups") or []
        if rule.get("maturity") == "runnable"
    }
    assert 8 <= len(runnable_rules) <= 12


def test_wheel_verifier_requires_exact_v025_release_fixture_contract() -> None:
    report = {
        "release_regressions": {
            "status": "passed",
            "domain_fixture_ids": list(EXPECTED_RELEASE_FIXTURE_IDS),
            "adversarial_checks": {"wrong_run_rejected": True},
        }
    }
    assert _release_regressions_passed(report)

    report["release_regressions"]["domain_fixture_ids"] = list(EXPECTED_RELEASE_FIXTURE_IDS[:-1])
    assert not _release_regressions_passed(report)

    report["release_regressions"]["domain_fixture_ids"] = list(EXPECTED_RELEASE_FIXTURE_IDS)
    report["release_regressions"]["adversarial_checks"] = {}
    assert not _release_regressions_passed(report)
