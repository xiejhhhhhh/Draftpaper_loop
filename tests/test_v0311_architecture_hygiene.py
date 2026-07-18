from __future__ import annotations

import json
from pathlib import Path

from draftpaper_cli.claim_contract import build_claim_contract_from_blueprint
from draftpaper_cli.evidence_registry import _records_from_payload
from draftpaper_cli.io_utils import read_json_object, write_json


def test_production_claim_and_evidence_fallbacks_use_dpl_stable_ids(tmp_path: Path) -> None:
    contract = build_claim_contract_from_blueprint(
        {
            "research_claims": [
                {
                    "research_question": "Does the verified signal generalize?",
                    "expected_finding": "The verified signal remains stable under held-out evaluation.",
                }
            ],
            "figure_storyboard": {"figures": []},
        }
    )
    assert contract["claims"][0]["claim_id"].startswith("clm_research_plan_0001_")

    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(
        json.dumps(
            {
                "evidence_records": [
                    {
                        "entity_role": "source_count",
                        "value": 12,
                        "unit": "count",
                        "cohort": "main",
                        "sample_unit": "source",
                        "split": "not_applicable",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    records = _records_from_payload(evidence_path, tmp_path)
    assert records[0]["evidence_id"].startswith("evd_structured_evidence_0001_")


def test_io_utils_write_json_is_utf8_atomic_and_object_typed(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "report.json"
    write_json(target, {"schema_version": "dpl.example.v1", "title": "中文"})
    assert read_json_object(target)["title"] == "中文"

    target.write_text("[]", encoding="utf-8")
    assert read_json_object(target, {"fallback": True}) == {"fallback": True}


def test_artifact_dag_has_no_unused_parallel_dependency_map() -> None:
    from draftpaper_cli import artifact_dag

    assert not hasattr(artifact_dag, "DEFAULT_DEPENDENCIES")
