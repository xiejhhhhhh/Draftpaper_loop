from __future__ import annotations

import json
import re
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

from draftpaper_cli.command_registry import COMMAND_SPECS
from tools import validate_capability_truth_matrix as validator


ROOT = Path(__file__).parents[1]
MATRIX_PATH = ROOT / "docs" / "capability_truth_matrix.json"
REQUIRED_CAPABILITY_IDS = {
    "scientific_gates_and_artifact_dag",
    "manuscript_completion_transaction",
    "command_schema_quality_contracts",
    "minimal_install_cost_risk_release",
    "completion_audit_and_readme_framework",
    "result_support_two_routes",
    "stable_locator",
}


def test_capability_truth_matrix_has_granular_evidence_backed_records() -> None:
    payload = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "dpl.capability_truth_matrix.v1"
    records = payload["capabilities"]
    assert REQUIRED_CAPABILITY_IDS <= {record["capability_id"] for record in records}
    assert len(records) > 5

    required = {
        "capability_id",
        "status",
        "since",
        "readme_anchor",
        "claim_zh",
        "claim_en",
        "commands",
        "source_files",
        "tests",
        "artifacts",
        "boundary_zh",
        "boundary_en",
    }
    for record in records:
        assert required <= set(record)
        assert record["status"] in {"implemented", "partial", "shadow", "planned"}
        assert re.fullmatch(r"\d+\.\d+", record["since"])
        assert record["readme_anchor"] == f"capability:{record['capability_id']}"
        assert record["claim_zh"].strip()
        assert record["claim_en"].strip()
        assert record["boundary_zh"].strip()
        assert record["boundary_en"].strip()
        assert record["source_files"]
        assert record["tests"]
        assert record["artifacts"]
        assert any(command in COMMAND_SPECS for command in record["commands"])

    artifacts = {artifact for record in records for artifact in record["artifacts"]}
    assert {
        "integrity_ledger.jsonl",
        "writing/manuscript_completion/packets/<packet_id>/preview.diff",
        "review/final_manuscript_confirmation.json",
        "quality_checks/blind_reviews/submission_bundle_manifest.json",
    } <= artifacts


def test_validator_requires_artifact_evidence_and_bilingual_partial_gaps() -> None:
    payload = validator.load_matrix()
    unsupported = deepcopy(payload)
    unsupported["capabilities"][0]["artifacts"] = ["unsupported/output.bin"]
    errors = validator.validate_matrix(unsupported)
    assert any("artifact" in error and "evidence" in error for error in errors)

    partial = deepcopy(payload)
    partial["capabilities"][0]["status"] = "partial"
    partial["capabilities"][0]["gap_zh"] = "仍需校准。"
    partial["capabilities"][0].pop("gap_en", None)
    errors = validator.validate_matrix(partial)
    assert any("gap_en" in error for error in errors)


def test_anchor_normalization_collapses_whitespace() -> None:
    assert validator.normalize_whitespace("  one\n\t two   three ") == "one two three"


def test_readme_binding_uses_stable_anchor_without_locking_prose_verbatim() -> None:
    record = validator.load_matrix()["capabilities"][0]
    anchor = record["readme_anchor"]
    text = f"<!-- {anchor} -->\nA clearer user-facing summary.\n<!-- /{anchor} -->"
    errors: list[str] = []

    validator._validate_readme_binding(record, text, "en", errors)

    assert errors == []


def test_shadow_status_is_supported_and_requires_bilingual_gaps() -> None:
    payload = validator.load_matrix()
    shadow = deepcopy(payload)
    shadow["capabilities"][0]["status"] = "shadow"
    shadow["capabilities"][0]["gap_zh"] = "等待分类校准。"
    shadow["capabilities"][0]["gap_en"] = "Classification calibration is pending."

    errors = validator.validate_matrix(shadow)

    assert not any("unsupported status" in error for error in errors)
    assert not any("need gap_" in error for error in errors)


def test_capability_truth_matrix_validator_accepts_current_checkout() -> None:
    completed = subprocess.run(
        [sys.executable, "tools/validate_capability_truth_matrix.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert "validated" in completed.stdout.lower()
